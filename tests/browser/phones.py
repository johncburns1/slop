"""Players' phones: Playwright pages at phone size, driven the way a player taps them.

Everything goes through what's on screen, and Playwright's locators and `expect` wait
for it to appear, so there are no sleeps. Each phone has its own browser context, which
keeps its saved session (localStorage) to itself.
"""

import re

from playwright.async_api import Browser, BrowserContext, Page, expect

from tests.evidence import evidence_path

VIEWPORT = {"width": 390, "height": 844}
TIMEOUT_MS = 10_000
CONFIRM = re.compile("^Confirm ")


class Phone:
    def __init__(self, page: Page, name: str) -> None:
        self.page = page
        self.name = name
        self.errors: list[str] = []
        page.on("pageerror", lambda error: self.errors.append(str(error)))

    def tap(self, button: str | re.Pattern[str]):
        return self.page.get_by_role("button", name=button).click()

    async def see(self, text: str | re.Pattern[str]) -> None:
        await expect(self.page.get_by_text(text).first).to_be_visible()

    async def screenshot(self, name: str, *, full_page: bool = True) -> None:
        """Save the screen. Use `full_page=False` where a sticky bar would land mid-page."""
        await self.page.screenshot(path=evidence_path(name), full_page=full_page)

    # Home and lobby

    async def create_game(self, *, rounds_per_team: int) -> str:
        """Create a game from the home screen and return its room code."""
        await self.page.locator("#player-name").fill(self.name)
        await self.page.locator("label.segment", has_text=str(rounds_per_team)).click()
        await self.tap("Create game")
        code = self.page.get_by_label(re.compile("^Room code "))
        await expect(code).to_be_visible()
        label = await code.get_attribute("aria-label")
        assert label is not None
        return label.removeprefix("Room code ")

    async def join_game(self) -> None:
        """Join from the home screen of a room link."""
        await self.page.locator("#player-name").fill(self.name)
        await self.tap("Join game")
        await expect(self.page.get_by_label(re.compile("^Room code "))).to_be_visible()

    async def create_team(self, team: str) -> None:
        await self.page.locator("#team-name").fill(team)
        await self.tap("Create team")
        await expect(self._team(team).get_by_text(self.name)).to_be_visible()

    async def join_team(self, team: str) -> None:
        await self._team(team).get_by_role("button", name="join").click()
        await expect(self._team(team).get_by_text(self.name)).to_be_visible()

    def _team(self, team: str):
        return self.page.locator("li.team", has_text=team)

    # Playing

    async def choose_personality(self, personality_id: str) -> None:
        """Pick a personality on any screen that lists them, then confirm."""
        option = self.page.locator("label.option")
        await option.filter(has=self.page.locator(f'input[value="{personality_id}"]')).click()
        await self.tap(CONFIRM)

    async def write_prompt(self, prompt: str) -> None:
        await self.page.locator("#prompt").fill(prompt)
        await self.tap("Write our script")

    async def send_guess(self, guess: str) -> None:
        await self.page.locator("#guess").fill(guess)
        await self.tap("Send guess")
        await expect(self.page.locator("li.player", has_text=guess)).to_be_visible()

    async def pick_winner(self, label: str) -> None:
        """Pick a guess, or "Nobody got it", and confirm."""
        await self.page.locator("label.option", has_text=label).click()
        await self.tap(CONFIRM)


class Phones:
    """Every phone in a test, each open at the same server."""

    def __init__(self, browser: Browser, url: str) -> None:
        self._browser = browser
        self._url = url
        self._contexts: list[BrowserContext] = []
        self.all: list[Phone] = []

    async def open(self, name: str, *, room_code: str | None = None) -> Phone:
        context = await self._browser.new_context(viewport=VIEWPORT, is_mobile=True, has_touch=True)
        context.set_default_timeout(TIMEOUT_MS)
        self._contexts.append(context)
        page = await context.new_page()
        await page.goto(f"{self._url}/?room={room_code}" if room_code else self._url)
        phone = Phone(page, name)
        self.all.append(phone)
        return phone

    async def close(self) -> None:
        for context in self._contexts:
            await context.close()
