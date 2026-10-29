"""Scripted bot players.

A bot knows only what its client received. Each time it is asked, it folds its
inbox into a ``View`` and offers at most one action it could take now:

- an eager action, which it would take straight away (form a team, pick a
  personality, submit a prompt, guess, guess the personality), or
- a deferred action, which a real player takes only once everyone else is
  done (the host closing the lobby, the acting team judging the guesses).

``Table`` decides when each action runs. ``BotScript`` says what the bot does
whenever it has a choice; anything left out has a default.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum

from slop.domain.events import (
    GameCompleted,
    GameEvent,
    GuessAccepted,
    GuessSubmitted,
    NoGuessAccepted,
    PersonalityGuessSubmitted,
    PersonalityPicked,
    PersonalitySelectionStarted,
    PlayerJoined,
    PlayerJoinedTeam,
    PlayerLeft,
    PromptSubmitted,
    RoundStarted,
    ScriptReady,
    TeamDisbanded,
    TeamFormed,
)
from tests.sim.client import GameClient

TEAM_COLORS = ("#E53935", "#1E88E5", "#43A047", "#FDD835", "#8E24AA", "#FB8C00")

Action = Callable[[], Awaitable[None]]
AnswerKey = Callable[[int], str]  # round number -> the prompt the acting team submitted


class Answer(Enum):
    CORRECT = "correct"


CORRECT = Answer.CORRECT
"""Use as a scripted guess to guess the round's prompt exactly."""


@dataclass(frozen=True)
class BotScript:
    """What one bot does. Rounds are keyed by round number, starting at 0.

    - ``team``: the team to be on, created if nobody has created it yet.
    - ``pick``: the personality to give the next team, if this bot picks.
    - ``prompts``: what to submit in rounds this bot's team acts.
    - ``guesses``: one guess for each round listed; ``CORRECT`` guesses the
      prompt. Rounds not listed get no guess, so the default never guesses.
    - ``personality_guesses``: which personality to name when this bot's team
      acts.

    When a team must do something once (pick, submit, judge, guess the
    personality), its first bot in seat order does it. Judging is honest: the
    first guess equal to the prompt wins, otherwise nobody gets it.
    """

    name: str
    team: str
    pick: str = "noir"
    prompts: Mapping[int, str] = field(default_factory=dict)
    guesses: Mapping[int, str | Answer] = field(default_factory=dict)
    personality_guesses: Mapping[int, str] = field(default_factory=dict)

    def prompt_for(self, round_number: int) -> str:
        return self.prompts.get(round_number, f"Robots perform round {round_number} badly")

    def personality_guess_for(self, round_number: int) -> str:
        return self.personality_guesses.get(round_number, "noir")


@dataclass
class View:
    """What a player knows about the game, from the events they received."""

    player_id: str
    players: dict[str, str | None] = field(default_factory=dict)  # player_id -> team_id
    teams: dict[str, TeamFormed] = field(default_factory=dict)  # team_id -> how it formed
    selecting_personalities: bool = False
    picked_by: set[str] = field(default_factory=set)  # team ids
    acting_teams: dict[int, str] = field(default_factory=dict)  # round -> acting team id
    prompts: dict[int, str] = field(default_factory=dict)  # only rounds we acted in
    scripts_ready: set[int] = field(default_factory=set)
    guesses: dict[int, list[GuessSubmitted]] = field(default_factory=dict)
    judged: set[int] = field(default_factory=set)
    personality_guessed: set[int] = field(default_factory=set)
    completed: GameCompleted | None = None

    @property
    def team_id(self) -> str | None:
        return self.players.get(self.player_id)

    @property
    def current_round(self) -> int | None:
        return max(self.acting_teams, default=None)

    def apply(self, event: GameEvent) -> None:
        match event:
            case PlayerJoined(player_id=player_id):
                self.players[player_id] = None
            case PlayerLeft(player_id=player_id):
                self.players.pop(player_id, None)
            case TeamFormed(team_id=team_id):
                self.teams[team_id] = event
            case TeamDisbanded(team_id=team_id):
                self.teams.pop(team_id, None)
                for player_id, on in self.players.items():
                    if on == team_id:
                        self.players[player_id] = None
            case PlayerJoinedTeam(player_id=player_id, team_id=team_id):
                self.players[player_id] = team_id
            case PersonalitySelectionStarted():
                self.selecting_personalities = True
            case PersonalityPicked(picked_by_team_id=team_id):
                self.picked_by.add(team_id)
            case RoundStarted(round_number=n, acting_team_id=team_id):
                self.acting_teams[n] = team_id
            case PromptSubmitted(round_number=n, prompt=prompt):
                self.prompts[n] = prompt
            case ScriptReady(round_number=n):
                self.scripts_ready.add(n)
            case GuessSubmitted(round_number=n):
                self.guesses.setdefault(n, []).append(event)
            case GuessAccepted(round_number=n) | NoGuessAccepted(round_number=n):
                self.judged.add(n)
            case PersonalityGuessSubmitted(round_number=n):
                self.personality_guessed.add(n)
            case GameCompleted():
                self.completed = event


def view_of(player_id: str, inbox: list[GameEvent]) -> View:
    view = View(player_id=player_id)
    for event in inbox:
        view.apply(event)
    return view


class Bot:
    """A simulated player: a client, a script, and the decisions in between."""

    def __init__(self, client: GameClient, script: BotScript, *, is_host: bool = False) -> None:
        self.client = client
        self.script = script
        self.is_host = is_host
        self.player_id: str | None = None
        self._guessed_in: set[int] = set()

    @property
    def name(self) -> str:
        return self.script.name

    @property
    def socket_id(self) -> str:
        return self.client.socket_id

    @property
    def team_id(self) -> str | None:
        return self.view().team_id

    async def join(self, room_code: str) -> None:
        self.player_id = await self.client.join_game(room_code, self.script.name)

    def inbox(self) -> list[GameEvent]:
        return self.client.inbox()

    def view(self) -> View:
        if self.player_id is None:
            raise RuntimeError(f"{self.name} hasn't joined a game")
        return view_of(self.player_id, self.inbox())

    def eager_action(self, answers: AnswerKey) -> Action | None:
        """What this bot would do right now, if anything."""
        view = self.view()
        if view.completed is not None:
            return None
        if not view.selecting_personalities:
            return self._form_team(view)
        team_id = view.team_id
        current = view.current_round
        if current is None:
            if team_id is not None and team_id not in view.picked_by:
                return lambda: self.client.assign_personality(self.script.pick)
            return None
        if view.acting_teams[current] == team_id:
            if current not in view.prompts:
                return lambda: self.client.submit_prompt(self.script.prompt_for(current))
            if current in view.judged and current not in view.personality_guessed:
                guess = self.script.personality_guess_for(current)
                return lambda: self.client.guess_personality(guess)
            return None
        if current in view.scripts_ready and current not in view.judged:
            return self._guess(current, answers)
        return None

    def deferred_action(self) -> Action | None:
        """What this bot would do once nobody has anything else to do."""
        view = self.view()
        if view.completed is not None:
            return None
        if not view.selecting_personalities:
            if self.is_host and self._teams_ready(view):
                return self.client.start_personality_selection
            return None
        current = view.current_round
        if (
            current is not None
            and view.acting_teams[current] == view.team_id
            and current in view.prompts
            and current not in view.judged
        ):
            prompt = view.prompts[current].casefold()
            winner = next(
                (
                    i
                    for i, guess in enumerate(view.guesses.get(current, []))
                    if guess.guess.casefold() == prompt
                ),
                None,
            )
            return lambda: self.client.pick_winning_guess(winner)
        return None

    def _form_team(self, view: View) -> Action | None:
        wanted = next((t for t in view.teams.values() if t.team_name == self.script.team), None)
        if wanted is None:
            used = {t.color for t in view.teams.values()}
            color = next(c for c in TEAM_COLORS if c not in used)
            return lambda: self.client.create_team(self.script.team, color)
        if view.team_id != wanted.team_id:
            return lambda: self.client.join_team(wanted.team_id)
        return None

    def _guess(self, round_number: int, answers: AnswerKey) -> Action | None:
        scripted = self.script.guesses.get(round_number)
        if scripted is None or round_number in self._guessed_in:
            return None
        text = answers(round_number) if scripted is CORRECT else str(scripted)

        async def guess() -> None:
            await self.client.submit_guess(text)
            self._guessed_in.add(round_number)

        return guess

    @staticmethod
    def _teams_ready(view: View) -> bool:
        staffed = {team_id for team_id in view.players.values() if team_id is not None}
        return None not in view.players.values() and len(staffed) >= 2
