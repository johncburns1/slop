"""The scenario library. Rounds are numbered from 0, as in the game.

Scoring, from PRODUCT.md: when the acting team accepts a guess, the guessing
team and the acting team each get 1 point; naming its own personality gets the
acting team 1 more. Teams pick in a ring in the order they formed (Red picks
for Blue, Blue for Green, Green for Red), and act in the same order. Guesses
go in seat order, and the acting team accepts the first that matches.
"""

from tests.scenarios.scenario import Outcome, Scenario
from tests.sim.bot import CORRECT, BotScript

# Personalities each team performs with, given the picks below.
RED_GETS, BLUE_GETS, GREEN_GETS = "shakespearean", "melodrama", "absurdist"

FULL_GAME = Scenario(
    name="Full game",
    summary=(
        "Three teams of two play three rounds each, from the lobby to final scores, "
        "with guessed and unguessed prompts, two teams guessing right at once, and "
        "right and wrong personality guesses. Red wins outright."
    ),
    rounds_per_team=3,
    scripts=(
        BotScript(
            name="Ann",
            team="Red",
            pick=BLUE_GETS,
            prompts={
                0: "Penguins open a tiny bakery",
                3: "Wizard loses his only hat",
                6: "Grandma wins the space race",
            },
            guesses={2: CORRECT, 7: "Cats run for mayor"},
            personality_guesses={0: RED_GETS, 3: "noir", 6: RED_GETS},
        ),
        BotScript(
            name="Ben",
            team="Blue",
            pick=GREEN_GETS,
            prompts={
                1: "Robots argue about breakfast cereal",
                4: "Pirates hold a bake sale",
                7: "Dragon afraid of tiny mice",
            },
            guesses={0: CORRECT, 5: "Ghost haunts a laundromat"},
            personality_guesses={1: "noir", 4: BLUE_GETS, 7: "nature_documentary"},
        ),
        BotScript(
            name="Cat",
            team="Green",
            pick=RED_GETS,
            prompts={
                2: "Vampire becomes a dentist",
                5: "Snowman takes a beach vacation",
                8: "Knights joust on office chairs",
            },
            guesses={1: "Robots fight over toast"},
            personality_guesses={2: GREEN_GETS, 5: GREEN_GETS, 8: "noir"},
        ),
        BotScript(name="Dan", team="Red", guesses={1: "Machines eat cereal", 5: "Sun", 8: CORRECT}),
        BotScript(name="Eve", team="Blue", guesses={2: CORRECT, 6: CORRECT}),
        BotScript(name="Fay", team="Green", guesses={4: CORRECT}),
    ),
    # Round by round (Red, Blue, Green):
    # 0 Red acts: Blue guesses it, Red names its personality: 2, 1, 0
    # 1 Blue acts: two wrong guesses, Blue names the wrong one: 2, 1, 0
    # 2 Green acts: Red and Blue both guess it, Red first; Green names it: 3, 1, 2
    # 3 Red acts: no guesses, wrong personality: 3, 1, 2
    # 4 Blue acts: Green guesses it, Blue names it: 3, 3, 3
    # 5 Green acts: two wrong guesses, Green names it: 3, 3, 4
    # 6 Red acts: Blue guesses it, Red names it: 5, 4, 4
    # 7 Blue acts: one wrong guess, wrong personality: 5, 4, 4
    # 8 Green acts: Red guesses it, wrong personality: 6, 4, 5
    expected=Outcome(
        final_scores={"Red": 6, "Blue": 4, "Green": 5},
        winner="Red",
        acting_order=("Red", "Blue", "Green") * 3,
    ),
)


def _tied_after_regular_rounds(
    name: str,
    summary: str,
    *,
    red_names: dict[int, str],
    blue_names: dict[int, str],
    green_guesses_right_in: tuple[int, ...],
    expected: Outcome,
) -> Scenario:
    """Three teams of one, one round each, scripted so Red and Blue tie on 2.

    From round 3 on, ``red_names`` and ``blue_names`` are the personality
    each team names when it acts, and Green guesses the prompt right in
    ``green_guesses_right_in``.

    Regular rounds (Red, Blue, Green): 0 Red acts, Blue guesses it, Red names
    the wrong personality: 1, 1, 0. 1 Blue acts, nobody guesses, Blue names
    its personality: 1, 2, 0. 2 Green acts, Red guesses it, Green names the
    wrong personality: 2, 2, 1. Red and Blue then play tiebreakers from round 3,
    and Green, out of the running, can still guess.
    """
    return Scenario(
        name=name,
        summary=summary,
        rounds_per_team=1,
        scripts=(
            BotScript(
                name="Ann",
                team="Red",
                pick=BLUE_GETS,
                guesses={2: CORRECT},
                personality_guesses={0: "noir", **red_names},
            ),
            BotScript(
                name="Ben",
                team="Blue",
                pick=GREEN_GETS,
                guesses={0: CORRECT},
                personality_guesses={1: BLUE_GETS, **blue_names},
            ),
            BotScript(
                name="Cat",
                team="Green",
                pick=RED_GETS,
                guesses=dict.fromkeys(green_guesses_right_in, CORRECT),
                personality_guesses={2: "noir"},
            ),
        ),
        expected=expected,
    )


TIEBREAKER_WIN = _tied_after_regular_rounds(
    "Tiebreaker win",
    "Red and Blue tie for first after the regular rounds. In the tiebreaker Red "
    "names its personality and Blue doesn't, so Red wins. Green sits it out.",
    # 3 Red acts, names it: 3, 2, 1. 4 Blue acts, wrong personality: 3, 2, 1.
    red_names={3: RED_GETS},
    blue_names={4: "noir"},
    green_guesses_right_in=(),
    expected=Outcome(
        final_scores={"Red": 3, "Blue": 2, "Green": 1},
        winner="Red",
        acting_order=("Red", "Blue", "Green", "Red", "Blue"),
    ),
)

TIEBREAKER_DRAW = _tied_after_regular_rounds(
    "Tiebreaker draw",
    "Red and Blue tie for first and stay level through both tiebreaker cycles, "
    "the limit, so the game ends in a draw.",
    # Cycle 1: 3 Red names it: 3, 2, 1. 4 Blue names it: 3, 3, 1.
    # Cycle 2: 5 Green guesses Red's prompt: 4, 3, 2. 6 Green guesses Blue's: 4, 4, 3.
    red_names={3: RED_GETS, 5: "noir"},
    blue_names={4: BLUE_GETS, 6: "noir"},
    green_guesses_right_in=(5, 6),
    expected=Outcome(
        final_scores={"Red": 4, "Blue": 4, "Green": 3},
        winner=None,
        acting_order=("Red", "Blue", "Green", "Red", "Blue", "Red", "Blue"),
    ),
)

SCENARIOS = (FULL_GAME, TIEBREAKER_WIN, TIEBREAKER_DRAW)
