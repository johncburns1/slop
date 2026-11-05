"""A whole game played on four phones through the web client, with screenshots.

The test taps through the real client instead of seating Socket.IO bots and rejoining
at each moment, because the round result isn't in the player view: only a phone that
was in the game when the round ended ever shows it. Tapping through also exercises the
client's event handling, not just its first render of a rejoin.
"""

import asyncio
import re

import pytest
from playwright.async_api import expect

from tests.browser.phones import Phone, Phones
from tests.evidence import Screenshot, screenshots_markdown, write_evidence

pytestmark = [pytest.mark.browser, pytest.mark.asyncio(loop_scope="module")]

SCENARIO = "browser-game"
ACTING = Screenshot(
    f"{SCENARIO}/screens/1-acting-team-script.png",
    "Alice (Red, acting) reads the script, with the time left and the guess count",
)
GUESSING = Screenshot(
    f"{SCENARIO}/screens/2-guessing-team.png",
    "Carol (Blue, guessing) at the same moment, with the countdown and the team's guess",
)
RESULT = Screenshot(
    f"{SCENARIO}/screens/3-round-result.png",
    "Dave (Blue) sees the round's result: the prompt, the winning guess, and the scores",
)
FINAL_WINNER = Screenshot(
    f"{SCENARIO}/screens/4-final-winner.png", "Alice (Red, the host) on the final screen"
)
FINAL_LOSER = Screenshot(
    f"{SCENARIO}/screens/5-final-other-team.png", "Carol (Blue) on the final screen"
)
SCREENSHOTS = (ACTING, GUESSING, RESULT, FINAL_WINNER, FINAL_LOSER)

COUNTDOWN = re.compile(r"\d:\d\d")
PROMPT = "Penguins open a tiny bakery"
GUESS = "Birds bake bread"


async def seat_players(phones: Phones) -> list[Phone]:
    """Alice and Bob are Red, Carol and Dave are Blue. Alice hosts one round per team."""
    alice = await phones.open("Alice")
    room_code = await alice.create_game(rounds_per_team=1)
    bob = await phones.open("Bob", room_code=room_code)
    carol = await phones.open("Carol", room_code=room_code)
    dave = await phones.open("Dave", room_code=room_code)
    await asyncio.gather(bob.join_game(), carol.join_game(), dave.join_game())

    await alice.create_team("Red")
    await carol.create_team("Blue")
    await asyncio.gather(bob.join_team("Red"), dave.join_team("Blue"))
    await expect(alice.page.locator("li.team", has_text="Dave")).to_be_visible()
    return [alice, bob, carol, dave]


async def see_result(phones: list[Phone], winning: str) -> None:
    for phone in phones:
        await phone.see("the prompt was")
        await phone.see(winning)


async def test_a_full_game_from_each_players_phone(phones: Phones):
    alice, bob, carol, dave = everyone = await seat_players(phones)

    # Each team secretly picks who writes the other team's scripts.
    await alice.tap("Start personality selection")
    await alice.choose_personality("melodrama")
    await carol.choose_personality("noir")

    # Round 1: Red acts. Blue's guess wins, and Red spots the personality: Red 2, Blue 1.
    await alice.write_prompt(PROMPT)
    await alice.see(PROMPT)
    end_guessing = alice.page.get_by_role("button", name="We're done, judge now")
    await expect(end_guessing).to_be_visible()
    await expect(bob.page.get_by_role("button", name="We're done, judge now")).to_be_visible()

    await carol.send_guess(GUESS)
    await alice.see("1 guess so far")
    await expect(carol.page.get_by_role("timer")).to_contain_text(COUNTDOWN)
    await expect(alice.page.get_by_role("timer")).to_contain_text(COUNTDOWN)
    assert PROMPT not in await carol.page.content()  # only the acting team has it
    await asyncio.gather(
        alice.screenshot(ACTING.name, full_page=False), carol.screenshot(GUESSING.name)
    )

    await end_guessing.click()
    await alice.pick_winner(GUESS)
    await alice.choose_personality("noir")

    await see_result(everyone, PROMPT)
    await dave.see(GUESS)
    await dave.screenshot(RESULT.name)
    for phone in everyone:
        await phone.tap("Continue")

    # Round 2: Blue acts. Nobody guesses, and Blue names the wrong personality: no change.
    await carol.write_prompt("Robots argue about breakfast cereal")
    await carol.tap("We're done, judge now")
    await carol.pick_winner("Nobody got it")
    await carol.choose_personality("absurdist")

    await see_result(everyone, "Robots argue about breakfast cereal")
    for phone in everyone:
        await phone.tap("Continue")

    # Final: Red wins, 2 to 1.
    for phone in everyone:
        await phone.see("game over")
        await phone.see(re.compile("Red wins with 2 pts"))
    await alice.see("that's your team")
    await expect(alice.page.get_by_text("awards")).to_be_visible()
    await asyncio.gather(alice.screenshot(FINAL_WINNER.name), carol.screenshot(FINAL_LOSER.name))

    assert [phone.errors for phone in everyone] == [[], [], [], []]
    write_evidence(
        f"{SCENARIO}/README.md",
        "A one-round-per-team game played on four 390x844 phones through the web client "
        f"(`tests/browser/test_full_game.py`).\n\n{screenshots_markdown(SCREENSHOTS)}\n",
    )
