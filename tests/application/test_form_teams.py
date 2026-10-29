"""Tests for forming teams in the lobby."""

import pytest

from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.engine import GameDeps, load_game
from slop.application.form_teams import (
    MAX_TEAM_NAME_LENGTH,
    CreateTeam,
    JoinTeam,
    ShuffleTeams,
    StartPersonalitySelection,
    create_team,
    join_team,
    shuffle_teams,
    start_personality_selection,
)
from slop.domain import (
    Game,
    GameStatus,
    PersonalitySelectionStarted,
    PlayerJoinedTeam,
    TeamDisbanded,
    TeamFormed,
)
from slop.domain.errors import GameRuleError
from tests.builders import lobby_with_two_teams, lobby_without_teams
from tests.evidence import write_evidence


async def seat(storage: InMemoryStorage, realtime: RecordingRealtime, game: Game) -> Game:
    """Save the game and put every player's socket in its room."""
    await storage.save_snapshot(game)
    for player in game.players:
        await realtime.join_room(player.socket_id, game.room_code)
    return game


def assert_players_match_teams(game: Game) -> None:
    for team in game.teams:
        for player_id in team.player_ids:
            assert game.get_player(player_id).team_id == team.id
    listed = sorted(pid for team in game.teams for pid in team.player_ids)
    assert listed == sorted(p.id for p in game.players if p.team_id is not None)


# Creating a team


async def test_a_player_creates_a_team_and_is_put_on_it(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seat(storage, realtime, lobby_without_teams())

    created = await create_team(deps, CreateTeam(game.id, "player-2", "  Llamas ", "#00FF00"))

    team = created.game.get_team(created.team_id)
    assert (team.name, team.color, team.player_ids) == ("Llamas", "#00FF00", ["player-2"])
    assert team.max_players == game.settings.max_players_per_team
    assert created.game.get_player("player-2").team_id == team.id
    assert await load_game(deps, game.id) == created.game
    assert [type(e) for e in await storage.get_events(game.id)] == [TeamFormed, PlayerJoinedTeam]
    for player in game.players:
        assert [type(e) for e in realtime.received_by(player.socket_id)] == [
            TeamFormed,
            PlayerJoinedTeam,
        ]


async def test_creating_a_team_moves_the_player_off_their_old_one(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seat(storage, realtime, lobby_with_two_teams())

    created = await create_team(deps, CreateTeam(game.id, "player-1", "Llamas", "#00FF00"))

    assert created.game.get_team("team-1").player_ids == ["player-2"]
    assert created.game.get_team(created.team_id).player_ids == ["player-1"]
    assert_players_match_teams(created.game)


@pytest.mark.parametrize(
    ("name", "color", "error"),
    [
        ("", "#00FF00", "Team name can't be blank"),
        ("   ", "#00FF00", "Team name can't be blank"),
        ("x" * (MAX_TEAM_NAME_LENGTH + 1), "#00FF00", "at most"),
        ("red team", "#00FF00", "already taken"),
        ("Llamas", " ", "color can't be blank"),
        ("Llamas", "#ff0000", "already taken"),
    ],
)
async def test_bad_or_duplicate_team_names_and_colors_are_rejected(
    deps: GameDeps,
    storage: InMemoryStorage,
    realtime: RecordingRealtime,
    name: str,
    color: str,
    error: str,
):
    game = await seat(storage, realtime, lobby_with_two_teams())

    with pytest.raises(GameRuleError, match=error):
        await create_team(deps, CreateTeam(game.id, "player-1", name, color))

    assert await load_game(deps, game.id) == game
    assert await storage.get_events(game.id) == []
    assert realtime.received_by("socket-1") == []


# Joining and switching teams


async def test_a_player_without_a_team_joins_one(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = lobby_with_two_teams(players_per_team=1)
    game.add_player(lobby_without_teams(players=3).get_player("player-3"))
    await seat(storage, realtime, game)

    after = await join_team(deps, JoinTeam(game.id, "player-3", "team-2"))

    assert after.get_team("team-2").player_ids == ["player-2", "player-3"]
    assert after.get_player("player-3").team_id == "team-2"
    assert await load_game(deps, game.id) == after
    assert realtime.who_received(PlayerJoinedTeam) == {"socket-1", "socket-2", "socket-3"}


async def test_a_player_switches_teams(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seat(storage, realtime, lobby_with_two_teams())

    after = await join_team(deps, JoinTeam(game.id, "player-1", "team-2"))

    assert after.get_team("team-1").player_ids == ["player-2"]
    assert after.get_team("team-2").player_ids == ["player-3", "player-4", "player-1"]
    assert_players_match_teams(after)
    (event,) = await storage.get_events(game.id)
    assert isinstance(event, PlayerJoinedTeam)
    assert (event.player_id, event.team_id) == ("player-1", "team-2")


async def test_a_full_team_cannot_be_joined(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seat(storage, realtime, lobby_with_two_teams(players_per_team=3))

    with pytest.raises(GameRuleError, match="full"):
        await join_team(deps, JoinTeam(game.id, "player-1", "team-2"))

    assert await load_game(deps, game.id) == game
    assert realtime.received_by("socket-1") == []


async def test_joining_your_own_team_is_rejected(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seat(storage, realtime, lobby_with_two_teams())

    with pytest.raises(GameRuleError, match="already on"):
        await join_team(deps, JoinTeam(game.id, "player-1", "team-1"))


async def test_joining_an_unknown_team_is_rejected(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seat(storage, realtime, lobby_with_two_teams())

    with pytest.raises(GameRuleError, match="No such team"):
        await join_team(deps, JoinTeam(game.id, "player-1", "team-9"))


# Rules shared by every team command


async def test_players_not_in_the_game_cannot_form_teams(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seat(storage, realtime, lobby_with_two_teams())

    with pytest.raises(GameRuleError, match="not in this game"):
        await create_team(deps, CreateTeam(game.id, "stranger", "Llamas", "#00FF00"))
    with pytest.raises(GameRuleError, match="not in this game"):
        await join_team(deps, JoinTeam(game.id, "stranger", "team-1"))
    with pytest.raises(GameRuleError, match="not in this game"):
        await shuffle_teams(deps, ShuffleTeams(game.id, "stranger"))
    with pytest.raises(GameRuleError, match="not in this game"):
        await start_personality_selection(deps, StartPersonalitySelection(game.id, "stranger"))


async def test_teams_are_fixed_once_the_lobby_closes(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = lobby_with_two_teams()
    game.set_personality_selection_phase()
    await seat(storage, realtime, game)

    with pytest.raises(GameRuleError, match="lobby"):
        await create_team(deps, CreateTeam(game.id, "player-1", "Llamas", "#00FF00"))
    with pytest.raises(GameRuleError, match="lobby"):
        await join_team(deps, JoinTeam(game.id, "player-1", "team-2"))
    with pytest.raises(GameRuleError, match="lobby"):
        await shuffle_teams(deps, ShuffleTeams(game.id, "player-1"))
    with pytest.raises(GameRuleError, match="lobby"):
        await start_personality_selection(deps, StartPersonalitySelection(game.id, "player-1"))
    assert await storage.get_events(game.id) == []


# Shuffling


@pytest.mark.parametrize(
    ("players", "per_team", "sizes"),
    [
        (2, 3, [1, 1]),
        (4, 3, [2, 2]),
        (5, 3, [3, 2]),
        (7, 3, [3, 2, 2]),
        (9, 3, [3, 3, 3]),
        (10, 3, [3, 3, 2, 2]),
        (5, 2, [2, 2, 1]),
    ],
)
async def test_shuffling_makes_the_fewest_balanced_teams(
    deps: GameDeps,
    storage: InMemoryStorage,
    realtime: RecordingRealtime,
    players: int,
    per_team: int,
    sizes: list[int],
):
    game = lobby_without_teams(players=players)
    game.settings.max_players_per_team = per_team
    await seat(storage, realtime, game)

    after = await shuffle_teams(deps, ShuffleTeams(game.id, "player-1", seed=7))

    assert sorted((len(t.player_ids) for t in after.teams), reverse=True) == sizes
    assert all(t.max_players == per_team for t in after.teams)
    assert all(p.team_id is not None for p in after.players)
    assert_players_match_teams(after)
    assert len({t.name for t in after.teams}) == len({t.color for t in after.teams}) == len(sizes)


async def test_shuffling_with_a_seed_is_deterministic(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seat(storage, realtime, lobby_without_teams(players=9))

    first = await shuffle_teams(deps, ShuffleTeams(game.id, "player-1", seed=42))
    second = await shuffle_teams(deps, ShuffleTeams(game.id, "player-1", seed=42))
    other = await shuffle_teams(deps, ShuffleTeams(game.id, "player-1", seed=43))

    def line_up(game: Game) -> list[list[str]]:
        return [team.player_ids for team in game.teams]

    assert line_up(first) == line_up(second)
    assert line_up(other) != line_up(first)
    # A seed fixes the line-up, which is not just the join order.
    assert line_up(first) != [[f"player-{n}" for n in range(i, i + 3)] for i in (1, 4, 7)]


async def test_shuffling_replaces_the_existing_teams_and_everyone_hears(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = lobby_with_two_teams(players_per_team=1)
    game.add_player(lobby_without_teams(players=3).get_player("player-3"))
    await seat(storage, realtime, game)

    after = await shuffle_teams(deps, ShuffleTeams(game.id, "player-1", seed=1))

    assert not {"team-1", "team-2"} & {t.id for t in after.teams}
    assert sorted(len(t.player_ids) for t in after.teams) == [1, 2]
    assert await load_game(deps, game.id) == after
    events = await storage.get_events(game.id)
    assert [type(e) for e in events] == [
        TeamDisbanded,
        TeamDisbanded,
        TeamFormed,
        TeamFormed,
        PlayerJoinedTeam,
        PlayerJoinedTeam,
        PlayerJoinedTeam,
    ]
    for player in game.players:
        assert [e.event_id for e in realtime.received_by(player.socket_id)] == [
            e.event_id for e in events
        ]
    log = "".join(e.model_dump_json() + "\n" for e in events)
    write_evidence("form-teams/shuffle-events.jsonl", log)


async def test_only_the_host_can_shuffle(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seat(storage, realtime, lobby_without_teams())

    with pytest.raises(GameRuleError, match="host"):
        await shuffle_teams(deps, ShuffleTeams(game.id, "player-2"))

    assert await storage.get_events(game.id) == []


async def test_shuffling_needs_enough_players_for_two_teams(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seat(storage, realtime, lobby_without_teams(players=1))

    with pytest.raises(GameRuleError, match="at least 2 players"):
        await shuffle_teams(deps, ShuffleTeams(game.id, "player-1"))


# Moving on to personality assignment


async def test_the_host_moves_on_when_teams_are_ready(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seat(storage, realtime, lobby_with_two_teams())

    after = await start_personality_selection(deps, StartPersonalitySelection(game.id, "player-1"))

    assert after.status == GameStatus.PERSONALITY_SELECTION
    assert await load_game(deps, game.id) == after
    assert realtime.who_received(PersonalitySelectionStarted) == {p.socket_id for p in game.players}


async def test_a_shuffled_lobby_is_ready_to_move_on(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seat(storage, realtime, lobby_without_teams(players=7))
    await shuffle_teams(deps, ShuffleTeams(game.id, "player-1", seed=3))

    after = await start_personality_selection(deps, StartPersonalitySelection(game.id, "player-1"))

    assert after.status == GameStatus.PERSONALITY_SELECTION


async def test_only_the_host_can_move_on(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seat(storage, realtime, lobby_with_two_teams())

    with pytest.raises(GameRuleError, match="host"):
        await start_personality_selection(deps, StartPersonalitySelection(game.id, "player-2"))


async def test_moving_on_needs_two_teams(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seat(storage, realtime, lobby_without_teams(players=2))
    await create_team(deps, CreateTeam(game.id, "player-1", "Llamas", "#00FF00"))
    await join_team(deps, JoinTeam(game.id, "player-2", "id-1"))

    with pytest.raises(GameRuleError, match="at least 2 teams"):
        await start_personality_selection(deps, StartPersonalitySelection(game.id, "player-1"))


async def test_moving_on_needs_everyone_on_a_team(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = lobby_with_two_teams(players_per_team=1)
    game.add_player(lobby_without_teams(players=3).get_player("player-3"))
    await seat(storage, realtime, game)

    with pytest.raises(GameRuleError, match="Not on a team yet: Player 3"):
        await start_personality_selection(deps, StartPersonalitySelection(game.id, "player-1"))


async def test_moving_on_needs_no_empty_teams(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seat(storage, realtime, lobby_with_two_teams())
    await create_team(deps, CreateTeam(game.id, "player-1", "Llamas", "#00FF00"))
    await join_team(deps, JoinTeam(game.id, "player-2", "id-1"))

    with pytest.raises(GameRuleError, match="Teams with no players: Red Team"):
        await start_personality_selection(deps, StartPersonalitySelection(game.id, "player-1"))

    assert (await load_game(deps, game.id)).status == GameStatus.LOBBY
