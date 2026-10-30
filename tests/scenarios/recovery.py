"""Recovery scenarios: games that survive a dropped connection and a server crash.

Each is a ``Scenario`` like those in ``library``, played with a failure partway
through. The ``play_*`` functions return the ``Played`` game, so ``outcome_of``
and ``report`` work as for any scenario, plus a ``Recovery``: when each player
came back, what the server showed them, and a log of what happened.
``recovery_report`` is the scenario's report with that log added.

Personalities and the pick ring are as in ``library``: Red picks for Blue and
Blue for Red. Red acts in round 0 and Blue in round 1.
"""

from dataclasses import dataclass, field
from pathlib import Path

from slop.api.schemas import PlayerViewReply
from slop.domain.events import GameEvent
from tests.scenarios.library import BLUE_GETS, RED_GETS
from tests.scenarios.scenario import Outcome, Played, Scenario, report
from tests.sim.bot import CORRECT, Bot, BotScript
from tests.sim.client import InProcessServer
from tests.sim.table import Table

DISCONNECT_AND_RECONNECT = Scenario(
    name="Disconnect and reconnect",
    summary=(
        "Cal loses his connection twice: in round 0 while acting, holding the script, "
        "and in round 1 while guessing. Each time the others play on without him, and "
        "he rejoins mid-round with `rejoin_game` to the view the server gives him: the "
        "prompt and script only while he is acting, and never a personality he "
        "shouldn't know. He then plays on to the end."
    ),
    rounds_per_team=1,
    scripts=(
        BotScript(
            name="Ann",
            team="Red",
            pick=BLUE_GETS,
            prompts={0: "Penguins open a tiny bakery"},
            guesses={1: "Machines eat cereal"},
            personality_guesses={0: RED_GETS},
        ),
        BotScript(
            name="Ben",
            team="Blue",
            pick=RED_GETS,
            prompts={1: "Robots argue about breakfast cereal"},
            guesses={0: "Birds bake bread"},
            personality_guesses={1: "noir"},
        ),
        BotScript(name="Cal", team="Red", guesses={1: CORRECT}),
        BotScript(name="Dan", team="Blue", guesses={0: CORRECT}),
    ),
    # 0 Red acts: Ben guesses wrong and Dan right while Cal is away, Cal rejoins
    #   and Ann judges; Red names its personality: Red 2, Blue 1.
    # 1 Blue acts: Ann guesses wrong while Cal is away, Cal rejoins and guesses
    #   it; Blue names the wrong personality: Red 3, Blue 2.
    expected=Outcome(
        final_scores={"Red": 3, "Blue": 2}, winner="Red", acting_order=("Red", "Blue")
    ),
)

SERVER_CRASH = Scenario(
    name="Server crash recovery",
    summary=(
        "The game is stored in SQLite. In round 1, with Blue's script out and one "
        "guess in, the server goes down and every connection with it. A new server "
        "starts on the same database file, every player rejoins with `rejoin_game`, "
        "and the round resumes where it stopped: same script, same guesses, same "
        "scores. The game then finishes as it would have without the crash."
    ),
    rounds_per_team=1,
    scripts=(
        BotScript(
            name="Ann",
            team="Red",
            pick=BLUE_GETS,
            prompts={0: "Wizard loses his only hat"},
            guesses={1: "Pirates sell cookies"},
            personality_guesses={0: "noir"},
        ),
        BotScript(
            name="Ben",
            team="Blue",
            pick=RED_GETS,
            prompts={1: "Pirates hold a bake sale"},
            guesses={0: CORRECT},
            personality_guesses={1: BLUE_GETS},
        ),
        BotScript(name="Cal", team="Red", guesses={1: CORRECT}),
        BotScript(name="Dan", team="Blue"),
    ),
    # 0 Red acts: Ben guesses it, Red names the wrong personality: Red 1, Blue 1.
    # 1 Blue acts: Ann guesses wrong, the server crashes and restarts, Cal
    #   guesses it, Blue names its personality: Red 2, Blue 3.
    expected=Outcome(
        final_scores={"Red": 2, "Blue": 3}, winner="Blue", acting_order=("Red", "Blue")
    ),
)


@dataclass(frozen=True)
class Rejoin:
    """A player coming back: when, whether their team was acting, and what they were shown."""

    player: str
    round_number: int
    acting: bool
    view: PlayerViewReply


@dataclass
class Recovery:
    rejoins: list[Rejoin] = field(default_factory=list)
    log: list[str] = field(default_factory=list)


async def play_disconnect_and_reconnect(scenario: Scenario) -> tuple[Played, Recovery]:
    """Drop Cal while he acts in round 0 and while he guesses in round 1."""
    server = InProcessServer.with_stand_ins()
    room_code = await server.create_game(rounds_per_team=scenario.rounds_per_team)
    table = await Table.seat(server, room_code, scenario.scripts)
    host, cal = table.bots[0], _bot(table, "Cal")
    recovery = Recovery()

    for round_number, role, guesses_meanwhile in ((0, "acting", 2), (1, "guessing", 1)):
        await table.step_until(lambda t, n=round_number: n in cal.view().scripts_ready)
        await cal.drop()
        heard = len(host.inbox())
        recovery.log.append(
            f"Round {round_number}: Cal ({role}) drops, holding "
            + ("the script." if role == "acting" else "no script.")
        )
        await table.step_until(
            lambda t, n=round_number, g=guesses_meanwhile: len(host.view().guesses.get(n, [])) == g
        )
        recovery.log.append(f"While Cal is away: {_events(host.inbox()[heard:])}.")
        view = await cal.rejoin()
        recovery.rejoins.append(Rejoin("Cal", round_number, role == "acting", view))
        recovery.log.append(f"Cal rejoins and is shown {_describe(view)}.")

    played = Played(table, await table.play())
    recovery.log.append("Everyone plays on to the end.")
    return played, recovery


async def play_server_crash(scenario: Scenario, database: Path) -> tuple[Played, Recovery]:
    """Restart the server on ``database`` once round 1 has its script and one guess."""
    server = InProcessServer.on_sqlite(database)
    room_code = await server.create_game(rounds_per_team=scenario.rounds_per_team)
    table = await Table.seat(server, room_code, scenario.scripts)
    host = table.bots[0]
    recovery = Recovery()

    await table.step_until(lambda t: len(host.view().guesses.get(1, [])) == 1)
    await server.restart()
    recovery.log.append(
        "Round 1, guessing, one guess in: the server restarts on the same SQLite file "
        "and every connection drops."
    )
    for bot in table.bots:
        view = await bot.rejoin()
        acting = view.current_round is not None and view.current_round.acting_team_id == (
            bot.team_id
        )
        recovery.rejoins.append(Rejoin(bot.name, 1, acting, view))
        recovery.log.append(f"{bot.name} rejoins and is shown {_describe(view)}.")

    played = Played(table, await table.play())
    recovery.log.append("Everyone plays on to the end.")
    return played, recovery


def recovery_report(scenario: Scenario, played: Played, recovery: Recovery) -> str:
    """The scenario's report, with what went wrong and how the game recovered."""
    steps = "\n".join(f"{i}. {line}" for i, line in enumerate(recovery.log, start=1))
    section = f"### What went wrong, and how it recovered\n\n{steps}\n\n"
    before, details, after = report(scenario, played).partition("<details>")
    return before + section + details + after


def _bot(table: Table, name: str) -> Bot:
    return next(bot for bot in table.bots if bot.name == name)


def _events(events: list[GameEvent]) -> str:
    shown = []
    for event in events:
        guess = getattr(event, "guess", None)
        shown.append(f'{event.event_type} "{guess}"' if guess else event.event_type)
    return ", ".join(shown) or "nothing"


def _describe(view: PlayerViewReply) -> str:
    current = view.current_round
    scores = ", ".join(f"{t.name} {t.score}" for t in view.teams)
    if current is None:
        return f"no round in progress (scores {scores})"
    script = f"the script with {len(current.script.roles)} roles" if current.script else "no script"
    prompt = f'the prompt "{current.prompt}"' if current.prompt else "no prompt"
    guesses = ", ".join(f'"{g.guess}"' for g in current.guesses) or "none"
    personalities = [t.personality_id for t in view.teams if t.personality_id]
    return (
        f"round {current.round_number} in phase `{current.phase}`, {prompt}, {script}, "
        f"guesses {guesses}, scores {scores}, "
        f"personalities shown: {', '.join(personalities) or 'none'}"
    )
