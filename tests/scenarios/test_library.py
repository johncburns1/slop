"""Play every scenario in the library and check it ends as expected."""

import pytest

from tests.evidence import write_evidence
from tests.scenarios.library import SCENARIOS
from tests.scenarios.scenario import Scenario, outcome_of, play, report


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.slug)
async def test_scenario_plays_out_as_expected(scenario: Scenario):
    played = await play(scenario)
    write_evidence(f"scenarios/{scenario.slug}.md", report(scenario, played))

    assert outcome_of(played) == scenario.expected


def test_scenario_names_are_unique():
    slugs = [scenario.slug for scenario in SCENARIOS]
    assert len(slugs) == len(set(slugs))
