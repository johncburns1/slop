"""Play the recovery scenarios and check each player was shown the right thing on rejoining."""

from pathlib import Path

from scripts.validate import MAX_EMBED_BYTES
from slop.domain.events import (
    GameCompleted,
    GuessSubmitted,
    PromptSubmitted,
    RoleAssigned,
    ScriptGenerated,
)
from tests.evidence import write_evidence
from tests.scenarios.library import BLUE_GETS, RED_GETS
from tests.scenarios.recovery import (
    DISCONNECT_AND_RECONNECT,
    SERVER_CRASH,
    play_disconnect_and_reconnect,
    play_server_crash,
    recovery_report,
)
from tests.scenarios.scenario import Played, outcome_of, play

SECRETS = (PromptSubmitted, ScriptGenerated, RoleAssigned)


def assert_everyone_finished(played: Played) -> None:
    for bot in played.table.bots:
        assert bot.connected, bot.name
        assert [e for e in bot.inbox() if isinstance(e, GameCompleted)] == [played.completed]


async def test_disconnect_and_reconnect():
    scenario = DISCONNECT_AND_RECONNECT
    played, recovery = await play_disconnect_and_reconnect(scenario)
    text = recovery_report(scenario, played, recovery)
    write_evidence(f"scenarios/{scenario.slug}.md", text)

    assert outcome_of(played) == scenario.expected
    assert outcome_of(await play(scenario)) == scenario.expected  # same as with no drops
    assert_everyone_finished(played)
    assert len(text.encode()) < MAX_EMBED_BYTES

    acting, guessing = recovery.rejoins
    # Acting in round 0: the prompt, the script, and the two guesses he missed,
    # but not Red's own personality, which Red has yet to name.
    assert (acting.round_number, acting.acting) == (0, True)
    current = acting.view.current_round
    assert current is not None and current.phase == "guessing"
    assert current.prompt == "Penguins open a tiny bakery"
    assert current.script is not None
    cal = next(bot for bot in played.table.bots if bot.name == "Cal")
    assert cal.player_id in {role.player_id for role in current.script.roles}
    assert [g.guess for g in current.guesses] == ["Birds bake bread", "Penguins open a tiny bakery"]
    assert all(t.personality_id is None for t in acting.view.teams)
    assert RED_GETS not in acting.view.model_dump_json()
    # Guessing in round 1: no prompt or script, the guess he missed, and the
    # personality Red picked for Blue only as Red's own pick.
    assert (guessing.round_number, guessing.acting) == (1, False)
    current = guessing.view.current_round
    assert current is not None and current.phase == "guessing"
    assert (current.prompt, current.script) == (None, None)
    assert [g.guess for g in current.guesses] == ["Machines eat cereal"]
    assert "Robots argue about breakfast cereal" not in guessing.view.model_dump_json()
    assert guessing.view.my_pick is not None
    assert guessing.view.my_pick.personality_id == BLUE_GETS
    assert [t.personality_id for t in guessing.view.teams] == [RED_GETS, None]  # Red's revealed

    # While away Cal heard nothing, and he never heard a secret of a round he didn't act in.
    missed = [e for e in cal.inbox() if isinstance(e, GuessSubmitted)]
    assert [e.guess for e in missed] == ["Robots argue about breakfast cereal"]  # only his own
    assert {e.round_number for e in cal.inbox() if isinstance(e, SECRETS)} == {0}


async def test_server_crash_recovery(tmp_path: Path):
    scenario = SERVER_CRASH
    played, recovery = await play_server_crash(scenario, tmp_path / "slop.sqlite3")
    text = recovery_report(scenario, played, recovery)
    write_evidence(f"scenarios/{scenario.slug}.md", text)

    assert outcome_of(played) == scenario.expected
    assert outcome_of(await play(scenario)) == scenario.expected  # same as with no crash
    assert_everyone_finished(played)
    assert len(text.encode()) < MAX_EMBED_BYTES

    # Every player rejoins round 1 where it stopped: guessing, Ann's guess in,
    # Red's personality revealed after round 0, and the scores from round 0.
    assert [r.player for r in recovery.rejoins] == ["Ann", "Ben", "Cal", "Dan"]
    for rejoin in recovery.rejoins:
        current = rejoin.view.current_round
        assert current is not None, rejoin.player
        assert (current.round_number, current.phase) == (1, "guessing"), rejoin.player
        assert [g.guess for g in current.guesses] == ["Pirates sell cookies"], rejoin.player
        assert [(t.name, t.score) for t in rejoin.view.teams] == [("Red", 1), ("Blue", 1)]
        assert [t.personality_id for t in rejoin.view.teams] == [RED_GETS, None]
        if rejoin.acting:
            assert current.prompt == "Pirates hold a bake sale"
            assert current.script is not None
        else:
            assert (current.prompt, current.script) == (None, None)
            assert "Pirates hold a bake sale" not in rejoin.view.model_dump_json()
    assert [r.player for r in recovery.rejoins if r.acting] == ["Ben", "Dan"]

    # The round resumed rather than restarting: Blue's script is the one it had before.
    for name in ("Ben", "Dan"):
        bot = next(b for b in played.table.bots if b.name == name)
        (generated,) = [
            e for e in bot.inbox() if isinstance(e, ScriptGenerated) and e.round_number == 1
        ]
        view = next(r.view for r in recovery.rejoins if r.player == name)
        assert view.current_round is not None and view.current_round.script is not None
        assert view.current_round.script.content == generated.script_content
