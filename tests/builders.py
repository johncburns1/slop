"""Named game states for tests and scenarios.

Each builder returns a fresh, valid ``Game`` in one well-known state, built
through the domain models' own methods. Ids are predictable: teams are
``team-1``, ``team-2`` (and ``team-3`` where a builder takes ``num_teams``), and
players are ``player-1`` upward, filling team 1 first.
"""

from collections.abc import Sequence

from slop.domain import Game, GameSettings, Guess, Player, Role, Round, Script, Team

TEAM_SPECS: tuple[tuple[str, str, str], ...] = (
    ("team-1", "Red Team", "#FF0000"),
    ("team-2", "Blue Team", "#0000FF"),
    ("team-3", "Green Team", "#00FF00"),
)
DEFAULT_PERSONALITIES = ("noir", "melodrama")
ALL_PERSONALITIES = (*DEFAULT_PERSONALITIES, "absurdist")
DEFAULT_PROMPT = "Superhero saves city from angry aliens"
DEFAULT_GUESSES = ("Aliens invade a city", "Hero fights space monsters")


def lobby_without_teams(*, room_code: str = "ABCD", players: int = 4) -> Game:
    """``players`` players in the lobby, none of them on a team yet.

    ``player-1`` created the game.
    """
    game = Game(id="game-1", room_code=room_code)
    for number in range(1, players + 1):
        game.add_player(
            Player(
                id=f"player-{number}",
                name=f"Player {number}",
                socket_id=f"socket-{number}",
                is_creator=number == 1,
            )
        )
    return game


def lobby_with_two_teams(*, room_code: str = "ABCD", players_per_team: int = 2) -> Game:
    """Two teams in the lobby, each with ``players_per_team`` players.

    ``player-1`` created the game. Nobody has a personality yet.
    """
    return _lobby(room_code=room_code, num_teams=2, players_per_team=players_per_team)


def selecting_personalities(*, num_teams: int = 2, players_per_team: int = 2) -> Game:
    """``num_teams`` teams (2 or 3) in personality selection, with no pick made yet."""
    game = _lobby(room_code="ABCD", num_teams=num_teams, players_per_team=players_per_team)
    game.set_personality_selection_phase()
    return game


def _lobby(*, room_code: str, num_teams: int, players_per_team: int) -> Game:
    game = Game(id="game-1", room_code=room_code)
    player_number = 1
    for team_id, name, color in TEAM_SPECS[:num_teams]:
        team = Team(
            id=team_id,
            name=name,
            color=color,
            max_players=game.settings.max_players_per_team,
        )
        game.add_team(team)
        for _ in range(players_per_team):
            player = Player(
                id=f"player-{player_number}",
                name=f"Player {player_number}",
                socket_id=f"socket-{player_number}",
                is_creator=player_number == 1,
            )
            team.add_player(player.id)
            player.assign_to_team(team.id)
            game.add_player(player)
            player_number += 1
    return game


def personalities_assigned(
    *, personalities: Sequence[str] = DEFAULT_PERSONALITIES, players_per_team: int = 2
) -> Game:
    """Two teams in personality selection, each given a personality by the other.

    ``personalities[i]`` is the personality team ``i`` will perform with.
    """
    game = lobby_with_two_teams(players_per_team=players_per_team)
    game.set_personality_selection_phase()
    _assign_personalities(game, personalities)
    return game


def waiting_for_prompt(*, players_per_team: int = 2) -> Game:
    """First round started: team 1 is acting and has not submitted a prompt yet.

    Team 1 performs with ``noir`` and team 2 with ``melodrama``.
    """
    game = lobby_with_two_teams(players_per_team=players_per_team)
    _assign_personalities(game, DEFAULT_PERSONALITIES)
    game.start()
    acting = game.get_acting_team()
    game.rounds.append(
        Round(
            id=f"round-{game.current_round}",
            round_number=game.current_round,
            acting_team_id=acting.id,
        )
    )
    return game


def in_guessing_phase(
    *,
    prompt: str = DEFAULT_PROMPT,
    guesses: Sequence[str] = DEFAULT_GUESSES,
    players_per_team: int = 2,
) -> Game:
    """First round in progress: team 1 is acting and team 2 has shouted ``guesses``.

    No guess is accepted, no personality is guessed, and nothing is scored.
    """
    game = lobby_with_two_teams(players_per_team=players_per_team)
    _assign_personalities(game, DEFAULT_PERSONALITIES)
    game.start()
    current = _play_round(game, prompt)
    guessing_team = game.teams[1]
    for index, text in enumerate(guesses):
        current.add_guess(Guess(team_id=guessing_team.id, guess=text, timestamp=float(index)))
    return game


def tied_after_last_round(*, rounds_per_team: int = 3, players_per_team: int = 2) -> Game:
    """Every round played, with the two teams level on points.

    In each round the other team guesses the prompt, so both teams score one
    point. The game is still ``PLAYING`` because a tiebreaker is due.
    """
    game = lobby_with_two_teams(players_per_team=players_per_team)
    game.settings = GameSettings(rounds_per_team=rounds_per_team)
    _assign_personalities(game, DEFAULT_PERSONALITIES)
    game.start()
    while not game.is_complete():
        _play_round_both_teams_score(game)
    return game


def in_last_round_guessing_phase(
    *, rounds_per_team: int = 1, guesses: Sequence[str] = DEFAULT_GUESSES
) -> Game:
    """The last regular round in progress: team 2 is acting and team 1 has shouted ``guesses``.

    Every earlier round played out as in ``tied_after_last_round``.
    """
    game = lobby_with_two_teams()
    game.settings = GameSettings(rounds_per_team=rounds_per_team)
    _assign_personalities(game, DEFAULT_PERSONALITIES)
    game.start()
    while game.current_round < game.get_total_rounds() - 1:
        _play_round_both_teams_score(game)
    current = _play_round(game, DEFAULT_PROMPT)
    for index, text in enumerate(guesses):
        current.add_guess(Guess(team_id=game.teams[0].id, guess=text, timestamp=float(index)))
    return game


def _play_round_both_teams_score(game: Game) -> None:
    """Play the current round: the other team guesses the prompt and both score a point."""
    acting = game.get_acting_team()
    guessing = next(team for team in game.teams if team.id != acting.id)
    current = _play_round(game, f"{DEFAULT_PROMPT} {game.current_round}")
    guess = Guess(team_id=guessing.id, guess=current.prompt, timestamp=0.0)
    guess.accept()
    current.add_guess(guess)
    current.set_prompt_winner(guessing.id)
    for team in (guessing, acting):
        current.add_score_to_team(team.id, 1)
        team.add_score(1)
    game.next_round()


def scored_after_last_round(
    *, scores: Sequence[int], rounds_per_team: int = 1, players_per_team: int = 2
) -> Game:
    """Every round played, with team ``i`` on ``scores[i]`` points (2 or 3 teams).

    Nobody guesses in the earlier rounds; every team's points come from the
    last round. The game is still ``PLAYING``: deciding what comes next is
    up to the game-end rules.
    """
    game = _lobby(room_code="ABCD", num_teams=len(scores), players_per_team=players_per_team)
    game.settings = GameSettings(rounds_per_team=rounds_per_team)
    _assign_personalities(game, ALL_PERSONALITIES[: len(scores)])
    game.start()
    while not game.is_complete():
        current = _play_round(game, f"{DEFAULT_PROMPT} {game.current_round}")
        game.next_round()
    for team, points in zip(game.teams, scores, strict=True):
        current.add_score_to_team(team.id, points)
        team.add_score(points)
    return game


def _assign_personalities(game: Game, personalities: Sequence[str]) -> None:
    """Give each team its personality, picked by the next team round the table."""
    for index, (team, personality) in enumerate(zip(game.teams, personalities, strict=True)):
        picker = game.teams[(index + 1) % len(game.teams)]
        team.assign_personality(personality, assigned_by=picker.id)


def _play_round(game: Game, prompt: str) -> Round:
    """Start the current round for the acting team, with one role per player."""
    acting = game.get_acting_team()
    assert acting.assigned_personality is not None
    roles = [
        Role(name=f"Character {i + 1}", description=f"Role {i + 1}")
        for i in range(len(acting.player_ids))
    ]
    current = Round(
        id=f"round-{game.current_round}",
        round_number=game.current_round,
        acting_team_id=acting.id,
        prompt=prompt,
        submitted_by=acting.player_ids[0],
        script=Script(
            content=f"A short scene about {prompt}.",
            roles=roles,
            personality=acting.assigned_personality,
        ),
        role_assignments={player_id: i for i, player_id in enumerate(acting.player_ids)},
    )
    game.rounds.append(current)
    return current
