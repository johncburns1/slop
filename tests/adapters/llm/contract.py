"""Reusable contract tests for LLMPort adapters.

Any LLM adapter, including real network-backed ones, plugs in by subclassing
LLMPortContract and overriding the ``adapter`` fixture:

    class TestMyAdapter(LLMPortContract):
        @pytest.fixture
        def adapter(self) -> LLMPort:
            return MyAdapter(...)

Every test here asserts only what the port promises, so it holds for any
correct implementation, deterministic or not.
"""

import pytest

from slop.domain import AIPersonality, Award, ContentTone, Script
from slop.ports import LLMPort
from slop.ports.llm import AWARD_COUNT, GameSummary, GuessSummary, RoundSummary, TeamSummary

PROMPT = "Detective solves mysterious art heist"

# The port targets ~150 words; allow generous slack for real models.
MIN_WORDS = 50
MAX_WORDS = 300


def make_personality(id: str = "noir") -> AIPersonality:
    """Build a personality for contract tests."""
    return AIPersonality(
        id=id,
        name=f"{id.title()} Director",
        description=f"Scripts in a {id} style",
        system_prompt=f"Write a short {id} script.",
    )


def make_summary(
    *, content_tone: ContentTone = ContentTone.FAMILY, winner: str | None = "Red"
) -> GameSummary:
    """Summarize a short two-team game for contract tests."""
    return GameSummary(
        content_tone=content_tone,
        teams=(
            TeamSummary(name="Red", players=("Ann", "Dan"), score=3, personality="Noir"),
            TeamSummary(name="Blue", players=("Ben", "Eve"), score=2, personality="Melodrama"),
        ),
        rounds=(
            RoundSummary(
                number=0,
                acting_team="Red",
                prompt="Penguins open a tiny bakery",
                guesses=(
                    GuessSummary(team="Blue", guess="Birds sell bread", correct=False),
                    GuessSummary(team="Blue", guess="Penguin bakery", correct=True),
                ),
                personality_guess="Noir",
                personality_correct=True,
            ),
            RoundSummary(
                number=1,
                acting_team="Blue",
                prompt="Robots argue about breakfast cereal",
                guesses=(GuessSummary(team="Red", guess="Toasters at war", correct=False),),
                personality_guess="Noir",
                personality_correct=False,
            ),
        ),
        winner=winner,
    )


class LLMPortContract:
    """Behavior every LLMPort implementation must satisfy."""

    @pytest.fixture
    def adapter(self) -> LLMPort:
        """Return the adapter under test. Subclasses must override this."""
        raise NotImplementedError("Override the adapter fixture in your subclass")

    async def test_returns_script(self, adapter: LLMPort) -> None:
        script = await adapter.generate_script(PROMPT, make_personality(), 2)

        assert isinstance(script, Script)

    @pytest.mark.parametrize("num_roles", [1, 2, 3, 4, 5, 6, 8])
    async def test_has_exactly_requested_roles(self, adapter: LLMPort, num_roles: int) -> None:
        script = await adapter.generate_script(PROMPT, make_personality(), num_roles)

        assert script.get_role_count() == num_roles

    async def test_roles_have_unique_names_and_descriptions(self, adapter: LLMPort) -> None:
        script = await adapter.generate_script(PROMPT, make_personality(), 6)

        names = [role.name for role in script.roles]
        assert all(name.strip() for name in names)
        assert len(set(names)) == len(names)
        assert all(role.description.strip() for role in script.roles)

    async def test_every_role_appears_in_content(self, adapter: LLMPort) -> None:
        script = await adapter.generate_script(PROMPT, make_personality(), 4)

        for role in script.roles:
            assert role.name in script.content

    @pytest.mark.parametrize("personality_id", ["noir", "melodrama", "absurdist", "custom"])
    async def test_uses_requested_personality(self, adapter: LLMPort, personality_id: str) -> None:
        script = await adapter.generate_script(PROMPT, make_personality(personality_id), 2)

        assert script.personality == personality_id

    async def test_length_is_performable(self, adapter: LLMPort) -> None:
        script = await adapter.generate_script(PROMPT, make_personality(), 3)

        assert MIN_WORDS <= script.word_count <= MAX_WORDS
        assert script.word_count == len(script.content.split())
        assert script.estimated_duration > 0

    async def test_awards_are_the_right_number_of_awards(self, adapter: LLMPort) -> None:
        awards = await adapter.generate_awards(make_summary())

        assert len(awards) == AWARD_COUNT
        assert all(isinstance(award, Award) for award in awards)

    @pytest.mark.parametrize("content_tone", list(ContentTone))
    @pytest.mark.parametrize("winner", ["Red", None])
    async def test_every_award_is_filled_in_and_names_someone_in_the_game(
        self, adapter: LLMPort, content_tone: ContentTone, winner: str | None
    ) -> None:
        summary = make_summary(content_tone=content_tone, winner=winner)

        awards = await adapter.generate_awards(summary)

        for award in awards:
            assert award.title.strip()
            assert award.reason.strip()
            assert award.recipient in summary.names()

    async def test_awards_for_a_game_with_no_guesses(self, adapter: LLMPort) -> None:
        summary = make_summary()
        quiet = GameSummary(
            content_tone=summary.content_tone,
            teams=summary.teams,
            rounds=tuple(
                RoundSummary(
                    number=r.number,
                    acting_team=r.acting_team,
                    prompt=r.prompt,
                    guesses=(),
                    personality_guess=None,
                    personality_correct=False,
                )
                for r in summary.rounds
            ),
            winner=None,
        )

        awards = await adapter.generate_awards(quiet)

        assert len(awards) == AWARD_COUNT
        assert all(award.recipient in quiet.names() for award in awards)
