"""Tests for playing a scenario and reporting how it went."""

from scripts.validate import MAX_EMBED_BYTES
from tests.scenarios.library import SCENARIOS
from tests.scenarios.scenario import Outcome, Scenario, outcome_of, play, report
from tests.sim.bot import CORRECT, BotScript

SMALL = Scenario(
    name="Small draw",
    summary="Two teams of one.",
    rounds_per_team=1,
    scripts=(
        BotScript(name="Ann", team="Red"),
        BotScript(name="Ben", team="Blue"),
        BotScript(name="Cal", team="Red"),
    ),
    expected=Outcome(final_scores={}, winner=None, acting_order=()),
)


def test_slug_is_the_name_in_kebab_case():
    assert SMALL.slug == "small-draw"


def test_setup_lists_each_team_and_its_players_in_the_order_they_formed():
    assert SMALL.teams == {"Red": ["Ann", "Cal"], "Blue": ["Ben"]}


async def test_outcome_names_teams_and_lists_who_acted_in_each_round():
    scenario = Scenario(
        name="Blue wins",
        summary="Blue guesses Red's prompt, then names its own personality.",
        rounds_per_team=1,
        scripts=(
            BotScript(name="Ann", team="Red", personality_guesses={0: "absurdist"}),
            BotScript(name="Ben", team="Blue", guesses={0: CORRECT}),
        ),
        expected=Outcome(final_scores={}, winner=None, acting_order=()),
    )

    played = await play(scenario)

    # Round 0: Blue +1 for guessing, Red +1 for being guessed, Red names the
    # wrong personality. Round 1: Blue names noir, which Red picked for it.
    assert outcome_of(played) == Outcome(
        final_scores={"Red": 1, "Blue": 2}, winner="Blue", acting_order=("Red", "Blue")
    )


async def test_report_has_the_result_a_row_per_round_and_collapsed_player_logs():
    scenario = Scenario(
        name="Tied",
        summary="Both teams name their personality only in tiebreakers, so it's a draw.",
        rounds_per_team=1,
        scripts=(
            BotScript(name="Ann", team="Red", personality_guesses={0: "absurdist"}),
            BotScript(name="Ben", team="Blue", personality_guesses={1: "absurdist"}),
        ),
        expected=Outcome(final_scores={}, winner=None, acting_order=()),
    )

    text = report(scenario, await play(scenario))

    assert text.startswith("## Tied\n\nBoth teams name")
    assert "**Setup:** 1 round per team. Red: Ann. Blue: Ben." in text
    assert "**Transport:** in-process" in text
    assert "**Result:** Draw, 2–2 (Red 2, Blue 2)." in text
    assert (
        "| 0 | Red | Robots perform round 0 badly | nobody | ❌ absurdist (noir) | 0 | 0 |" in text
    )
    assert (
        "| 2 (tiebreaker 1) | Red | Robots perform round 2 badly | nobody | ✅ noir | 1 (+1) | 0 |"
        in text
    )
    assert "| 5 (tiebreaker 2) | Blue |" in text
    assert "<details>\n<summary>What each player received</summary>" in text
    assert "### Ann (Red)" in text and "### Ben (Blue)" in text
    assert '- **Round 0:** RoundStarted, PromptSubmitted "Robots perform round 0 badly",' in text
    assert text.rstrip().endswith("</details>")


async def test_every_library_report_embeds_whole_in_the_validation_report():
    for scenario in SCENARIOS:
        text = report(scenario, await play(scenario))
        assert len(text.encode()) < MAX_EMBED_BYTES, scenario.name
