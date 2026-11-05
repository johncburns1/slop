"""Guesses racing each other, and the end of guessing, on a real server with SQLite."""

import asyncio
from pathlib import Path
from typing import Any

from slop.adapters.storage import SQLiteStorage
from slop.adapters.websocket import SocketIORealtime
from slop.api import create_app
from slop.api.rate_limit import RateLimit
from slop.domain.events import GuessingEnded, GuessSubmitted
from slop.domain.personalities import PERSONALITIES
from slop.domain.projection import replay
from tests.socketio_clients import Listener, serving

GUESSERS = 3
GUESSES_EACH = 15


async def test_every_acknowledged_guess_is_kept_when_they_race_the_end_of_guessing(
    tmp_path: Path,
) -> None:
    storage = SQLiteStorage(tmp_path / "slop.sqlite3")
    app = create_app(
        SocketIORealtime(), storage=storage, rate_limit=RateLimit(per_second=1000, burst=1000)
    )
    async with serving(app) as url:
        actor, *guessers = clients = [Listener() for _ in range(GUESSERS + 1)]
        for client in clients:
            await client.connect(url)
        try:
            game_id = await _play_up_to_guessing(actor, guessers)
            first_guess_kept = asyncio.Event()

            async def guess(client: Listener, text: str) -> tuple[str, Any]:
                reply = await client.client.call("submit_guess", {"guess": text}, timeout=30)
                if reply is None:
                    first_guess_kept.set()
                return text, reply

            async def end_guessing_midway() -> None:
                await first_guess_kept.wait()
                assert await actor.client.call("end_guessing", {}, timeout=30) is None

            ending = asyncio.create_task(end_guessing_midway())
            replies = await asyncio.gather(
                *(
                    guess(client, f"guess {seat} {n}")
                    for seat, client in enumerate(guessers)
                    for n in range(GUESSES_EACH)
                )
            )
            await ending
        finally:
            for client in clients:
                await client.client.disconnect()

    accepted = sorted(text for text, reply in replies if reply is None)
    assert accepted
    assert all(reply["code"] == "rule_broken" for _, reply in replies if reply is not None)

    snapshot = await storage.get_snapshot(game_id)
    assert snapshot is not None
    events = await storage.get_events(game_id)
    assert sorted(g.guess for g in snapshot.rounds[0].prompt_guesses) == accepted
    assert sorted(e.guess for e in events if isinstance(e, GuessSubmitted)) == accepted
    assert sum(isinstance(e, GuessingEnded) for e in events) == 1
    assert snapshot.rounds[0].guessing_ended
    assert replay(events) == snapshot


async def _play_up_to_guessing(actor: Listener, guessers: list[Listener]) -> str:
    """Put ``actor`` on the acting team and ``guessers`` on the other, and write the script."""
    created = await actor.client.call("create_game", {"content_tone": "family"})
    room_code = created["room_code"]
    joined = await actor.client.call("join_game", {"room_code": room_code, "player_name": "Ann"})
    await actor.client.call("create_team", {"team_name": "Reds", "color": "#f00"})
    for seat, client in enumerate(guessers):
        await client.client.call("join_game", {"room_code": room_code, "player_name": f"P{seat}"})
    team = await guessers[0].client.call("create_team", {"team_name": "Blues", "color": "#00f"})
    for client in guessers[1:]:
        await client.client.call("join_team", {"team_id": team["team_id"]})
    await actor.client.call("start_personality_selection", {})
    personality = next(iter(PERSONALITIES))
    await actor.client.call("assign_personality", {"personality_id": personality})
    await guessers[0].client.call("assign_personality", {"personality_id": personality})
    assert await actor.client.call("submit_prompt", {"prompt": "a very slow disk"}) is None
    game_id: str = joined["game_id"]
    return game_id
