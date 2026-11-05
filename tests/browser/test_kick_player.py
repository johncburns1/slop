"""The host removes players in the lobby and mid-round, on five phones, with screenshots."""

import asyncio
import re

import pytest
from playwright.async_api import expect

from tests.browser.phones import Phone, Phones
from tests.evidence import Screenshot, screenshots_markdown, write_evidence

pytestmark = [pytest.mark.browser, pytest.mark.asyncio(loop_scope="module")]

SCENARIO = "browser-kick-player"
LOBBY = Screenshot(
    f"{SCENARIO}/screens/1-host-lobby-remove.png",
    "Alice (the host) in the lobby: a remove button next to everyone else",
)
MID_ROUND = Screenshot(
    f"{SCENARIO}/screens/2-host-menu-mid-round.png",
    "Alice mid-round with the host menu open, after removing Bob: players and remove buttons",
)
REMOVED = Screenshot(
    f"{SCENARIO}/screens/3-removed-phone-home.png",
    "Bob's phone after the host removed him mid-round: back home with the message",
)
SCREENSHOTS = (LOBBY, MID_ROUND, REMOVED)

REMOVED_NOTICE = "the host removed you from the game."


def accept_next_confirm(phone: Phone) -> None:
    phone.page.once("dialog", lambda dialog: dialog.accept())


async def remove(host: Phone, name: str) -> None:
    accept_next_confirm(host)
    await host.tap(f"Remove {name}")


async def removed_and_home(phone: Phone) -> None:
    await phone.see(REMOVED_NOTICE)
    await expect(phone.page.locator("#player-name")).to_be_visible()
    assert await phone.page.evaluate("localStorage.getItem('slop.session')") is None


async def test_the_host_removes_players_in_the_lobby_and_mid_round(phones: Phones):
    alice = await phones.open("Alice")
    room_code = await alice.create_game(rounds_per_team=2)
    bob, carol, dave, erin = [
        await phones.open(name, room_code=room_code) for name in ("Bob", "Carol", "Dave", "Erin")
    ]
    await asyncio.gather(*(p.join_game() for p in (bob, carol, dave, erin)))
    await carol.create_team("Red")
    await alice.create_team("Blue")
    await asyncio.gather(dave.join_team("Red"), bob.join_team("Blue"))

    # In the lobby only the host gets remove buttons, and never for themself.
    await expect(alice.page.get_by_role("button", name="Remove Erin")).to_be_visible()
    await expect(alice.page.get_by_role("button", name="Remove Alice")).to_have_count(0)
    await expect(bob.page.get_by_role("button", name=re.compile("^Remove "))).to_have_count(0)
    await alice.screenshot(LOBBY.name, full_page=False)
    await remove(alice, "Erin")
    await removed_and_home(erin)
    await alice.see("the host removed Erin.")
    await expect(alice.page.locator("li.player", has_text="Erin")).to_have_count(0)

    await alice.tap("Start personality selection")
    await alice.choose_personality("melodrama")
    await carol.choose_personality("noir")
    await carol.write_prompt("Robots argue about breakfast cereal")
    await expect(carol.page.get_by_role("button", name="We're done, judge now")).to_be_visible()
    await bob.send_guess("Machines fight over toast")

    # Mid-round the host removes a guessing player from the host menu; the round goes on.
    await expect(bob.page.locator(".host-menu")).to_be_hidden()
    await alice.page.locator(".host-menu > summary").click()
    await remove(alice, "Bob")
    await removed_and_home(bob)
    for phone in (alice, carol, dave):
        await phone.see("the host removed Bob.")
    await expect(alice.page.get_by_role("button", name="Remove Bob")).to_have_count(0)
    await alice.screenshot(MID_ROUND.name, full_page=False)
    await bob.screenshot(REMOVED.name, full_page=False)

    # An acting player loses their role, and the other keeps theirs.
    await remove(alice, "Dave")
    await removed_and_home(dave)
    await expect(carol.page.get_by_text(re.compile(": nobody$"))).to_be_visible()
    await expect(carol.page.get_by_text("<you>").first).to_be_visible()

    # With Red emptied, fewer than two teams have players: the game ends, and Blue wins.
    await remove(alice, "Carol")
    await removed_and_home(carol)
    await alice.see("WINNER")
    await expect(alice.page.locator(".headline")).to_contain_text("Blue")

    assert [phone.errors for phone in (alice, bob, carol, dave, erin)] == [[], [], [], [], []]
    write_evidence(
        f"{SCENARIO}/README.md",
        "The host removes players in the lobby and mid-round, on five 390x844 phones "
        f"(`tests/browser/test_kick_player.py`).\n\n{screenshots_markdown(SCREENSHOTS)}\n",
    )
