"""Play every scenario in the library and check it ends as expected."""

import pytest

from slop.domain.events import AwardsGiven, GameCompleted
from tests.evidence import write_evidence
from tests.scenarios.library import SCENARIOS
from tests.scenarios.scenario import Scenario, awards_of, outcome_of, play, report


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.slug)
async def test_scenario_plays_out_as_expected(scenario: Scenario):
    played = await play(scenario)
    write_evidence(f"scenarios/{scenario.slug}.md", report(scenario, played))

    assert outcome_of(played) == scenario.expected
    # Right after the game ends, the room hears awards about it.
    room = [type(e) for e in played.table.bots[0].inbox()]
    assert room[-2:] == [GameCompleted, AwardsGiven]
    awarded = awards_of(played)
    assert awarded is not None
    names = {s.name for s in scenario.scripts} | set(scenario.teams)
    assert {award.recipient for award in awarded.awards} <= names


def test_scenario_names_are_unique():
    slugs = [scenario.slug for scenario in SCENARIOS]
    assert len(slugs) == len(set(slugs))
