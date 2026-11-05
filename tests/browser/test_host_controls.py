"""The host skips a stalled turn and then restarts mid-round, on four phones, with screenshots."""

import asyncio
import re

import pytest
from playwright.async_api import expect

from tests.browser.phones import Phone, Phones
from tests.evidence import Screenshot, screenshots_markdown, write_evidence

pytestmark = [pytest.mark.browser, pytest.mark.asyncio(loop_scope="module")]

SCENARIO = "browser-host-controls"
SKIP_OFFER = Screenshot(
    f"{SCENARIO}/screens/1-host-can-skip.png",
    "Alice (the host, Blue) while Red is stuck on its prompt: the skip action",
)
SKIPPED = Screenshot(
    f"{SCENARIO}/screens/2-turn-skipped.png",
    "Carol (Red) right after: the notice, and Blue acting with Red still on 0",
)
RESTARTED = Screenshot(
    f"{SCENARIO}/screens/3-restarted-to-lobby.png",
    "Dave (Red) after the host restarted mid-round: back in the lobby, same teams",
)
SCREENSHOTS = (SKIP_OFFER, SKIPPED, RESTARTED)

SKIPPED_NOTICE = re.compile("skipped Red's turn")
RESTARTED_NOTICE = re.compile("the host restarted the game")


async def seat_players(phones: Phones) -> list[Phone]:
    """Carol and Dave are Red, which acts first; Alice (the host) and Bob are Blue."""
    alice = await phones.open("Alice")
    room_code = await alice.create_game(rounds_per_team=2)
    bob = await phones.open("Bob", room_code=room_code)
    carol = await phones.open("Carol", room_code=room_code)
    dave = await phones.open("Dave", room_code=room_code)
    await asyncio.gather(bob.join_game(), carol.join_game(), dave.join_game())

    await carol.create_team("Red")
    await alice.create_team("Blue")
    await asyncio.gather(dave.join_team("Red"), bob.join_team("Blue"))
    await expect(alice.page.locator("li.team", has_text="Dave")).to_be_visible()
    return [alice, bob, carol, dave]


def accept_next_confirm(phone: Phone) -> None:
    phone.page.once("dialog", lambda dialog: dialog.accept())


async def test_the_host_skips_a_stalled_turn_then_restarts_mid_round(phones: Phones):
    alice, bob, carol, dave = everyone = await seat_players(phones)
    await alice.tap("Start personality selection")
    await alice.choose_personality("melodrama")
    await carol.choose_personality("noir")

    # Red is up and stalls. Only the host is offered the skip, and nobody has a host menu
    # but the host.
    await carol.see("you're up")
    skip = alice.page.get_by_role("button", name="Skip their turn")
    await expect(skip).to_be_visible()
    for phone in (bob, carol, dave):
        await expect(phone.page.get_by_role("button", name=re.compile("^Skip "))).to_have_count(0)
        await expect(phone.page.locator(".host-menu")).to_be_hidden()
    await alice.screenshot(SKIP_OFFER.name)

    accept_next_confirm(alice)
    await skip.click()

    # Everyone hears it, and Blue's turn starts with Red on no points.
    for phone in everyone:
        await phone.see(SKIPPED_NOTICE)
    await alice.see("you're up")
    await carol.see("now acting")
    await expect(carol.page.locator("li.score", has_text="Red")).to_contain_text("0")
    await carol.screenshot(SKIPPED.name, full_page=False)

    # Blue gets its script, so the skip is gone; guessing (and its timer) starts.
    await alice.write_prompt("Robots argue about breakfast cereal")
    await expect(alice.page.get_by_role("button", name="We're done, judge now")).to_be_visible()
    await expect(alice.page.get_by_role("button", name=re.compile("^Skip "))).to_have_count(0)
    await carol.send_guess("Machines fight over toast")
    await expect(carol.page.get_by_role("timer")).to_be_visible()

    # The host restarts mid-round from the host menu.
    await alice.page.locator(".host-menu > summary").click()
    accept_next_confirm(alice)
    await alice.tap("Restart game")

    for phone in everyone:
        await phone.see(RESTARTED_NOTICE)
        await expect(phone.page.get_by_label(re.compile("^Room code "))).to_be_visible()
        await expect(phone.page.locator("li.team", has_text="Carol")).to_contain_text("Dave")
        await expect(phone.page.locator("li.team", has_text="Alice")).to_contain_text("Bob")
    await expect(
        alice.page.get_by_role("button", name="Start personality selection")
    ).to_be_visible()
    await expect(alice.page.locator(".host-menu")).to_be_hidden()
    await dave.screenshot(RESTARTED.name, full_page=False)

    # Back in the lobby, teams can change.
    await bob.join_team("Red")

    assert [phone.errors for phone in everyone] == [[], [], [], []]
    write_evidence(
        f"{SCENARIO}/README.md",
        "The host skips a stalled turn and restarts mid-round, on four 390x844 phones "
        f"(`tests/browser/test_host_controls.py`).\n\n{screenshots_markdown(SCREENSHOTS)}\n",
    )
