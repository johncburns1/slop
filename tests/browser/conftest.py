"""Fixtures for browser tests: one real server and one Chromium per test module."""

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from playwright.async_api import Browser, Error, async_playwright

from tests.browser.phones import Phones
from tests.evidence import write_evidence
from tests.sim.socketio_client import SocketIOServer

INSTALL = "uv run playwright install --with-deps chromium"


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def server() -> AsyncIterator[SocketIOServer]:
    async with SocketIOServer.running() as running:
        yield running


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def browser() -> AsyncIterator[Browser]:
    """Chromium, or a skip if it can't start here. CI must have it, so there it's a failure."""
    async with async_playwright() as playwright:
        try:
            chromium = await playwright.chromium.launch()
        except Error as error:
            if os.environ.get("CI"):
                raise
            reason = f"Chromium isn't available, so no screenshots. Run `{INSTALL}`."
            write_evidence("browser/skipped.md", f"Browser tests skipped: {reason}\n")
            detail = str(error).splitlines()[0]
            pytest.skip(f"{reason} ({detail})")
        yield chromium
        await chromium.close()


@pytest_asyncio.fixture(loop_scope="module")
async def phones(server: SocketIOServer, browser: Browser) -> AsyncIterator[Phones]:
    """Opens phones for the test and closes them after, so the server can shut down."""
    opened = Phones(browser, server.url)
    yield opened
    await opened.close()
