"""Tests for the end-of-game awards: the game summary the LLM gets, and checking its awards."""

from dataclasses import dataclass, field, replace

import pytest

from slop.adapters.llm import StandInLLMAdapter
from slop.adapters.moderation import StandInModerationAdapter
from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.awards import give_awards, summarize
from slop.application.engine import GameDeps, commit
from slop.domain import (
    AIPersonality,
    Award,
    AwardsGiven,
    ContentTone,
    Game,
    GameCompleted,
    GameStatus,
    Guess,
    Script,
)
from slop.ports.llm import GameSummary, LLMError, RoundSummary
from tests.builders import DEFAULT_PROMPT, scored_after_last_round


@dataclass
class FakeLLM:
    """Returns ``awards`` (or raises if ``error``) and records each summary it gets."""

    awards: list[Award] = field(default_factory=list)
    error: bool = False
    summaries: list[GameSummary] = field(default_factory=list)

    async def generate_script(
        self, prompt: str, personality: AIPersonality, num_roles: int
    ) -> Script:
        return await StandInLLMAdapter().generate_script(prompt, personality, num_roles)

    async def generate_awards(self, summary: GameSummary) -> list[Award]:
        self.summaries.append(summary)
        if self.error:
            raise LLMError("provider unavailable")
        return self.awards


def won_by_red() -> Game:
    """Red Team beat Blue Team 4–2; in round 0, Blue shouted a wrong guess, then the right one."""
    game = scored_after_last_round(scores=(4, 2), rounds_per_team=1)
    first = game.rounds[0]
    first.add_guess(Guess(team_id="team-2", guess="Aliens eat a city", timestamp=0.0))
    right = Guess(team_id="team-2", guess="Hero versus aliens", timestamp=1.0)
    right.accept()
    first.add_guess(right)
    first.set_prompt_winner("team-2")
    first.set_personality_guess("noir")
    first.check_personality_guess()
    return game


async def finished(deps: GameDeps, realtime: RecordingRealtime, game: Game) -> Game:
    """Store the game, seat every player in its room, and complete it, as the game end will."""
    await deps.storage.save_snapshot(game)
    for player in game.players:
        await realtime.join_room(player.socket_id, game.room_code)
    winner = max(game.teams, key=lambda t: t.score)
    completed = GameCompleted(
        game_id=game.id,
        final_scores={t.id: t.score for t in game.teams},
        winner_team_id=winner.id,
    )
    async with deps.locks.hold(game.id):
        return await commit(deps, game, [completed])


def awards_to(*recipients: str) -> list[Award]:
    return [Award(title=f"Award {r}", recipient=r, reason=f"Because {r}.") for r in recipients]


def test_the_summary_names_teams_and_players_and_tells_what_happened():
    game = won_by_red()
    game.finish()

    summary = summarize(game)

    assert summary.content_tone == ContentTone.FAMILY
    assert summary.winner == "Red Team"
    assert [(t.name, t.players, t.score, t.personality) for t in summary.teams] == [
        ("Red Team", ("Player 1", "Player 2"), 4, "Noir"),
        ("Blue Team", ("Player 3", "Player 4"), 2, "Melodrama"),
    ]
    first = summary.rounds[0]
    assert (first.number, first.acting_team, first.prompt) == (0, "Red Team", f"{DEFAULT_PROMPT} 0")
    assert [(g.team, g.guess, g.correct) for g in first.guesses] == [
        ("Blue Team", "Aliens eat a city", False),
        ("Blue Team", "Hero versus aliens", True),
    ]
    assert (first.personality_guess, first.personality_correct) == ("Noir", True)
    assert summary.names() == {
        "Red Team",
        "Blue Team",
        "Player 1",
        "Player 2",
        "Player 3",
        "Player 4",
    }


def test_the_summary_follows_the_content_setting_and_a_draw_has_no_winner():
    game = scored_after_last_round(scores=(3, 3))
    game.settings.content_tone = ContentTone.ADULT
    game.finish()

    summary = summarize(game)

    assert (summary.content_tone, summary.winner) == (ContentTone.ADULT, None)
    assert summary.rounds[-1] == RoundSummary(
        number=1,
        acting_team="Blue Team",
        prompt=f"{DEFAULT_PROMPT} 1",
        guesses=(),
        personality_guess=None,
        personality_correct=False,
    )


async def test_awards_are_given_to_the_room_and_stored_on_the_game(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    llm = FakeLLM(awards=awards_to("Red Team", "Player 3", "Blue Team"))
    deps = replace(deps, llm=llm)
    game = await finished(deps, realtime, won_by_red())

    game = await give_awards(deps, game)

    assert llm.summaries == [summarize(game)]
    assert game.awards == llm.awards
    awarded = (await storage.get_events(game.id))[-1]
    assert isinstance(awarded, AwardsGiven)
    assert awarded.awards == llm.awards
    assert realtime.broadcasts_to(game.room_code)[-1] == awarded
    assert await storage.get_snapshot(game.id) == game


@pytest.mark.parametrize(
    "awards",
    [
        awards_to("Red Team", "Blue Team"),
        awards_to("Red Team", "Blue Team", "Player 1", "Player 2"),
        awards_to("Red Team", "Blue Team", "Somebody Else"),
        [*awards_to("Red Team", "Blue Team"), Award(title=" ", recipient="Player 1", reason="Hi.")],
        [*awards_to("Red Team", "Blue Team"), Award(title="Hi", recipient="Player 1", reason="")],
    ],
    ids=["too-few", "too-many", "unknown-recipient", "blank-title", "blank-reason"],
)
async def test_unusable_awards_are_dropped_and_nobody_is_told(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime, awards: list[Award]
):
    deps = replace(deps, llm=FakeLLM(awards=awards))
    game = await finished(deps, realtime, won_by_red())
    before = await storage.get_events(game.id)

    after = await give_awards(deps, game)

    assert after == game
    assert after.awards == []
    assert await storage.get_events(game.id) == before


async def test_a_failing_llm_gives_no_awards(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    deps = replace(deps, llm=FakeLLM(error=True))
    game = await finished(deps, realtime, won_by_red())
    before = await storage.get_events(game.id)

    after = await give_awards(deps, game)

    assert (after.status, after.awards) == (GameStatus.FINISHED, [])
    assert await storage.get_events(game.id) == before


async def test_awards_are_not_given_if_the_group_played_again_meanwhile(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await finished(deps, realtime, won_by_red())
    restarted = await storage.get_snapshot(game.id)
    assert restarted is not None
    restarted.set_personality_selection_phase()
    await storage.save_snapshot(restarted)
    before = await storage.get_events(game.id)

    after = await give_awards(deps, game)

    assert after.status == GameStatus.PERSONALITY_SELECTION
    assert await storage.get_events(game.id) == before


def moderated(deps: GameDeps, awards: list[Award]) -> GameDeps:
    """``deps`` giving ``awards``, moderated: "gloop" always blocked, "fizz" for families."""
    moderation = StandInModerationAdapter(blocked_always=["gloop"], blocked_for_family=["fizz"])
    return replace(deps, llm=FakeLLM(awards=awards), moderation=moderation)


async def test_awards_moderation_blocks_are_dropped_and_the_rest_are_given(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    clean = awards_to("Red Team", "Blue Team")
    flagged = Award(title="Gloop of the Night", recipient="Player 3", reason="For trying.")
    deps = moderated(deps, [clean[0], flagged, clean[1]])
    game = await finished(deps, realtime, won_by_red())

    game = await give_awards(deps, game)

    assert game.awards == clean
    awarded = (await storage.get_events(game.id))[-1]
    assert isinstance(awarded, AwardsGiven)
    assert awarded.awards == clean
    assert realtime.broadcasts_to(game.room_code)[-1] == awarded


async def test_when_every_award_is_blocked_the_game_just_ends(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    awards = [Award(title="Gloop", recipient=r, reason="Hi.") for r in ("Red Team", "Blue Team")]
    deps = moderated(deps, [*awards, Award(title="Hi", recipient="Player 1", reason="Gloop.")])
    game = await finished(deps, realtime, won_by_red())
    before = await storage.get_events(game.id)

    after = await give_awards(deps, game)

    assert (after.status, after.awards) == (GameStatus.FINISHED, [])
    assert await storage.get_events(game.id) == before
    assert AwardsGiven not in {type(e) for e in realtime.broadcasts_to(game.room_code)}


@pytest.mark.parametrize(("tone", "kept"), [(ContentTone.FAMILY, 2), (ContentTone.ADULT, 3)])
async def test_family_games_drop_awards_adult_games_keep(
    deps: GameDeps, realtime: RecordingRealtime, tone: ContentTone, kept: int
):
    awards = awards_to("Red Team", "Blue Team", "Player 1")
    awards[2] = Award(title="Fizz Champion", recipient="Player 1", reason="Fizz all night.")
    deps = moderated(deps, awards)
    game = won_by_red()
    game.settings.content_tone = tone
    game = await finished(deps, realtime, game)

    game = await give_awards(deps, game)

    assert len(game.awards) == kept
