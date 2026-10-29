"""Seat scripted bots at a game and play it out, one action at a time.

Each ``step`` runs one action: the first eager action any bot has, in seat
order, or, once nobody has one, the first deferred action. So everyone forms
their team before the host closes the lobby, and every scripted guess is in
before the acting team judges. ``play`` steps until every bot has seen the game
end. Call ``step`` directly to do something between actions, such as dropping
a bot's connection (SLOP-12).
"""

from collections.abc import Sequence

from slop.domain.events import GameCompleted, PromptSubmitted
from tests.sim.bot import Bot, BotScript
from tests.sim.client import InProcessServer

MAX_STEPS = 1000


class SimulationStalledError(Exception):
    """No bot can act, but the game hasn't ended."""


class Table:
    """The bots playing one game, in seat order. The first seat is the host."""

    def __init__(self, bots: Sequence[Bot]) -> None:
        self.bots = list(bots)

    @classmethod
    async def seat(
        cls, server: InProcessServer, room_code: str, scripts: Sequence[BotScript]
    ) -> "Table":
        """Connect a bot for each script and join them all to the game, in order.

        Everyone joins before anyone acts, because a player hears only what
        happens after they join.
        """
        bots = [
            Bot(server.connect(f"socket-{seat}"), script, is_host=seat == 1)
            for seat, script in enumerate(scripts, start=1)
        ]
        for bot in bots:
            await bot.join(room_code)
        return cls(bots)

    async def step(self) -> bool:
        """Run one action, and return False if no bot had one."""
        for bot in self.bots:
            action = bot.eager_action(self.answer)
            if action is not None:
                await action()
                return True
        for bot in self.bots:
            action = bot.deferred_action()
            if action is not None:
                await action()
                return True
        return False

    async def play(self, *, max_steps: int = MAX_STEPS) -> GameCompleted:
        """Step until every bot has received ``GameCompleted``, and return it.

        Raises:
            SimulationStalledError: If the bots run out of actions, or steps,
                before then
        """
        for _ in range(max_steps):
            if all(bot.view().completed is not None for bot in self.bots):
                break
            if not await self.step():
                raise SimulationStalledError(self._stalled_at())
        else:
            raise SimulationStalledError(f"Still playing after {max_steps} steps")
        completed = self.bots[0].view().completed
        assert completed is not None
        return completed

    def answer(self, round_number: int) -> str:
        """The prompt submitted in this round, as only the acting team saw it."""
        for bot in self.bots:
            for event in bot.inbox():
                if isinstance(event, PromptSubmitted) and event.round_number == round_number:
                    return event.prompt
        raise LookupError(f"No prompt submitted in round {round_number}")

    def team_id_named(self, name: str) -> str:
        for bot in self.bots:
            for team in bot.view().teams.values():
                if team.team_name == name:
                    return team.team_id
        raise LookupError(f"No team named {name}")

    def views_markdown(self) -> str:
        """Every bot's inbox as a Markdown section, event types in order."""
        sections = []
        for bot in self.bots:
            lines = [f"- {event.event_type}{_detail(event)}" for event in bot.inbox()]
            team = bot.view().teams.get(bot.team_id or "")
            heading = f"### {bot.name} ({team.team_name if team else 'no team'})"
            sections.append("\n".join([heading, "", *lines]))
        return "\n\n".join(sections) + "\n"

    def _stalled_at(self) -> str:
        return "No bot can act. Last events seen: " + ", ".join(
            f"{bot.name}: {bot.inbox()[-1].event_type if bot.inbox() else 'nothing'}"
            for bot in self.bots
        )


def _detail(event: object) -> str:
    """A few words on what the event carried, for the events whose content matters."""
    fields = ("round_number", "prompt", "guess", "role_name", "personality_id", "final_scores")
    shown = [f"{name}={getattr(event, name)!r}" for name in fields if hasattr(event, name)]
    return f" ({', '.join(shown)})" if shown else ""
