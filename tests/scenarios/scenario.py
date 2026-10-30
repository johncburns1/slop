"""A scenario: a named game, the bots that play it, and how it should end.

``play`` seats the bots and plays the game to the end, in-process or on any
other ``GameServer``, such as a real one over Socket.IO. ``outcome_of`` reduces
the result to what a scenario expects, with teams named rather than by id.
``report`` writes the evidence: the setup, the result, a round-by-round score
table, and what each player received, collapsed.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from slop.domain.events import (
    GameCompleted,
    GameEvent,
    GuessAccepted,
    GuessSubmitted,
    PersonalityAssigned,
    PersonalityGuessSubmitted,
    PersonalityRevealed,
    PromptSubmitted,
    RoleAssigned,
    RoundCompleted,
    RoundStarted,
    ScoresUpdated,
    TiebreakerStarted,
)
from tests.sim.bot import BotScript
from tests.sim.client import GameServer, InProcessServer
from tests.sim.table import Table


@dataclass(frozen=True)
class Outcome:
    """How a game ended, with teams by name.

    ``acting_order`` is the team that acted in each round, from round 0,
    tiebreaker rounds included. ``winner`` is None for a draw.
    """

    final_scores: Mapping[str, int]
    winner: str | None
    acting_order: tuple[str, ...]


@dataclass(frozen=True)
class Scenario:
    """A named game: its setup, each bot's script in seat order, and the outcome expected.

    The first script is the host. Teams form in the order their first player
    is seated, which sets both the turn order and the personality ring.
    """

    name: str
    summary: str
    rounds_per_team: int
    scripts: Sequence[BotScript]
    expected: Outcome

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")

    @property
    def teams(self) -> dict[str, list[str]]:
        """Each team's players, in the order the teams form."""
        teams: dict[str, list[str]] = {}
        for script in self.scripts:
            teams.setdefault(script.team, []).append(script.name)
        return teams


@dataclass(frozen=True)
class Played:
    table: Table
    completed: GameCompleted
    transport: str = InProcessServer.transport


async def play(scenario: Scenario, server: GameServer | None = None) -> Played:
    """Play the scenario from an empty lobby to the end of the game.

    Plays on a fresh in-process server unless given one.
    """
    server = server or InProcessServer.with_stand_ins()
    room_code = await server.create_game(rounds_per_team=scenario.rounds_per_team)
    table = await Table.seat(server, room_code, scenario.scripts)
    return Played(table, await table.play(), server.transport)


def outcome_of(played: Played) -> Outcome:
    names = _team_names(played.table)
    completed = played.completed
    acting = played.table.bots[0].view().acting_teams
    return Outcome(
        final_scores={names[team_id]: score for team_id, score in completed.final_scores.items()},
        winner=names[completed.winner_team_id] if completed.winner_team_id else None,
        acting_order=tuple(names[acting[n]] for n in sorted(acting)),
    )


def report(scenario: Scenario, played: Played) -> str:
    """The scenario's evidence, as Markdown short enough to read in a minute."""
    setup = " ".join(f"{team}: {', '.join(players)}." for team, players in scenario.teams.items())
    rounds = "round" if scenario.rounds_per_team == 1 else "rounds"
    return (
        "\n\n".join(
            [
                f"## {scenario.name}",
                scenario.summary,
                f"**Setup:** {scenario.rounds_per_team} {rounds} per team. {setup}",
                f"**Transport:** {played.transport}",
                f"**Result:** {_result(played)}",
                _score_table(played),
                "<details>\n<summary>What each player received</summary>",
                _player_logs(played.table),
                "</details>",
            ]
        )
        + "\n"
    )


def _result(played: Played) -> str:
    names = _team_names(played.table)
    scores = played.completed.final_scores
    ranked = sorted(scores.values(), reverse=True)
    by_team = ", ".join(f"{names[team_id]} {score}" for team_id, score in scores.items())
    winner = played.completed.winner_team_id
    headline = f"{names[winner]} wins" if winner else "Draw"
    return f"{headline}, {'–'.join(map(str, ranked))} ({by_team})."


def _score_table(played: Played) -> str:
    """A row per round: who acted, the prompt, who guessed it, the personality guess, totals."""
    table = played.table
    names = _team_names(table)
    events = _room_events(table)
    tiebreaker_cycle: dict[int, int] = {}
    guessed_by: dict[int, str] = {}
    personality_guess: dict[int, str] = {}
    personality: dict[int, str] = {}
    changes: dict[int, dict[str, int]] = {}
    totals: dict[int, dict[str, int]] = {}
    acting: dict[int, str] = {}
    cycle = 0
    for event in events:
        match event:
            case TiebreakerStarted(cycle=n):
                cycle = n
            case RoundStarted(round_number=n, acting_team_id=team_id):
                acting[n] = team_id
                if cycle:
                    tiebreaker_cycle[n] = cycle
            case GuessAccepted(round_number=n, team_id=team_id):
                guessed_by[n] = names[team_id]
            case PersonalityGuessSubmitted(round_number=n, personality_guess=guess):
                personality_guess[n] = guess
            case PersonalityRevealed(round_number=n, personality_id=actual):
                personality[n] = actual
            case ScoresUpdated(round_number=n, score_changes=change):
                changes[n] = change
            case RoundCompleted(round_number=n, final_scores=scores):
                totals[n] = scores

    team_ids = list(names)
    header = ["Round", "Acting", "Prompt", "Guessed by", "Personality guess", *names.values()]
    rows = [header, ["---"] * len(header)]
    for n in sorted(acting):
        label = f"{n} (tiebreaker {tiebreaker_cycle[n]})" if n in tiebreaker_cycle else str(n)
        guess, actual = personality_guess.get(n, ""), personality.get(n, "")
        named = f"✅ {guess}" if guess == actual else f"❌ {guess} ({actual})"
        scores = [
            _score(totals.get(n, {}).get(team_id, 0), changes.get(n, {}).get(team_id, 0))
            for team_id in team_ids
        ]
        prompt = table.answer(n)
        rows.append([label, names[acting[n]], prompt, guessed_by.get(n, "nobody"), named, *scores])
    return "\n".join(f"| {' | '.join(row)} |" for row in rows)


def _player_logs(table: Table) -> str:
    """Each player's inbox, a line per round, repeated events counted rather than listed."""
    names = _team_names(table)
    sections = []
    for bot in table.bots:
        lines: list[str] = []
        phase = "Lobby"
        tokens: list[str] = []
        for event in bot.inbox():
            if isinstance(event, RoundStarted):
                lines.append(_log_line(phase, tokens))
                phase, tokens = f"Round {event.round_number}", []
            tokens.append(event.event_type + _log_detail(event, names))
        lines.append(_log_line(phase, tokens))
        team = names.get(bot.team_id or "", "no team")
        sections.append("\n".join([f"### {bot.name} ({team})", "", *lines]))
    return "\n\n".join(sections)


def _log_line(phase: str, tokens: list[str]) -> str:
    counted: list[tuple[str, int]] = []
    for token in tokens:
        if counted and counted[-1][0] == token:
            counted[-1] = (token, counted[-1][1] + 1)
        else:
            counted.append((token, 1))
    shown = (token if count == 1 else f"{token} ×{count}" for token, count in counted)
    return f"- **{phase}:** {', '.join(shown)}"


def _log_detail(event: GameEvent, names: Mapping[str, str]) -> str:
    """The part of the event worth reading: prompts, guesses, roles, and who scored."""
    match event:
        case PromptSubmitted(prompt=text) | GuessSubmitted(guess=text):
            return f' "{text}"'
        case RoleAssigned(role_name=role):
            return f" ({role})"
        case (
            PersonalityAssigned(personality_id=text)
            | PersonalityGuessSubmitted(personality_guess=text)
            | PersonalityRevealed(personality_id=text)
        ):
            return f" ({text})"
        case ScoresUpdated(score_changes=changes) if changes:
            return " (" + ", ".join(f"{names.get(t, t)} +{p}" for t, p in changes.items()) + ")"
    return ""


def _score(total: int, change: int) -> str:
    return f"{total} (+{change})" if change else str(total)


def _room_events(table: Table) -> list[GameEvent]:
    """What the whole room heard: the host's inbox, which every player also received."""
    return table.bots[0].inbox()


def _team_names(table: Table) -> dict[str, str]:
    """Team id to name, in the order the teams formed."""
    teams = table.bots[0].view().teams
    return {team_id: formed.team_name for team_id, formed in teams.items()}
