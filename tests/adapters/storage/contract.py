"""Reusable contract tests for StoragePort adapters.

Every storage adapter must pass these tests. To check a new adapter, subclass
`StoragePortContract` in a `test_*.py` module and override the `storage`
fixture to yield a fresh, empty adapter:

    class TestSQLiteStorage(StoragePortContract):
        @pytest.fixture
        def storage(self, tmp_path):
            return SQLiteStorage(tmp_path / "slop.db")

This module is not named `test_*.py`, so pytest only collects the contract
through those subclasses.
"""

from copy import deepcopy

import pytest

from slop.domain import (
    Game,
    GameCreated,
    GameStatus,
    Player,
    PlayerJoined,
    Role,
    Round,
    Script,
    ScriptGenerated,
    Team,
)
from slop.ports import StoragePort


def make_game_created(game_id: str = "game-1", room_code: str = "ABCD") -> GameCreated:
    return GameCreated(
        game_id=game_id,
        room_code=room_code,
        content_tone="family",
        max_players=12,
        rounds_per_team=3,
    )


def make_player_joined(game_id: str = "game-1", player_id: str = "player-1") -> PlayerJoined:
    return PlayerJoined(
        game_id=game_id,
        player_id=player_id,
        player_name="Alice",
        socket_id="socket-123",
    )


def make_script_generated(game_id: str = "game-1") -> ScriptGenerated:
    return ScriptGenerated(
        game_id=game_id,
        round_number=1,
        script_content="To be or not to be.",
        personality_id="shakespeare",
        roles=[{"name": "Hamlet", "description": "A brooding prince"}],
        word_count=6,
        estimated_duration=3,
    )


def make_game(game_id: str = "game-1", room_code: str = "ABCD") -> Game:
    """Build a game with nested teams, players, and rounds."""
    game = Game(id=game_id, room_code=room_code)
    game.add_team(Team(id="team-1", name="Red", color="#ff0000", player_ids=["player-1"]))
    game.add_player(Player(id="player-1", name="Alice", socket_id="socket-1", team_id="team-1"))
    game.rounds.append(
        Round(
            id="round-1",
            round_number=1,
            acting_team_id="team-1",
            prompt="six words about a sad clown",
            submitted_by="player-1",
            script=Script(
                content="Honk honk.",
                roles=[Role(name="Clown", description="Sad", lines=["Honk."])],
                personality="noir",
            ),
            role_assignments={"player-1": 0},
        )
    )
    return game


class StoragePortContract:
    """Behavior every StoragePort adapter must provide."""

    @pytest.fixture
    def storage(self) -> StoragePort:
        """Return a fresh, empty adapter. Subclasses must override this."""
        raise NotImplementedError("Override the `storage` fixture in the adapter's test class")

    # Event log

    async def test_get_events_for_unknown_game_is_empty(self, storage: StoragePort) -> None:
        assert await storage.get_events("missing") == []

    async def test_saved_events_replay_in_order(self, storage: StoragePort) -> None:
        events = [make_game_created(), make_player_joined(), make_script_generated()]
        for event in events:
            await storage.save_event(event)

        assert await storage.get_events("game-1") == events

    async def test_replayed_events_keep_their_concrete_types(self, storage: StoragePort) -> None:
        await storage.save_event(make_game_created())
        await storage.save_event(make_player_joined())

        replayed = await storage.get_events("game-1")

        assert [type(e) for e in replayed] == [GameCreated, PlayerJoined]

    async def test_events_are_scoped_to_their_game(self, storage: StoragePort) -> None:
        first = make_game_created(game_id="game-1")
        second = make_game_created(game_id="game-2", room_code="WXYZ")
        await storage.save_event(first)
        await storage.save_event(second)

        assert await storage.get_events("game-1") == [first]
        assert await storage.get_events("game-2") == [second]

    async def test_mutating_replayed_events_does_not_change_the_log(
        self, storage: StoragePort
    ) -> None:
        event = make_script_generated()
        await storage.save_event(event)

        replayed = await storage.get_events("game-1")
        assert isinstance(replayed[0], ScriptGenerated)
        replayed[0].roles.append({"name": "Intruder", "description": "Should not persist"})

        replayed.clear()

        assert await storage.get_events("game-1") == [event]

    async def test_mutating_a_saved_event_does_not_change_the_log(
        self, storage: StoragePort
    ) -> None:
        event = make_script_generated()
        await storage.save_event(event)
        event.roles.append({"name": "Intruder", "description": "Should not persist"})

        replayed = await storage.get_events("game-1")

        assert isinstance(replayed[0], ScriptGenerated)
        assert len(replayed[0].roles) == 1

    # Snapshots

    async def test_get_snapshot_for_unknown_game_is_none(self, storage: StoragePort) -> None:
        assert await storage.get_snapshot("missing") is None

    async def test_saved_snapshot_loads_with_equal_state(self, storage: StoragePort) -> None:
        game = make_game()
        await storage.save_snapshot(game)

        assert await storage.get_snapshot("game-1") == game

    async def test_saving_a_snapshot_again_replaces_it(self, storage: StoragePort) -> None:
        game = make_game()
        await storage.save_snapshot(game)
        game.start()
        game.next_round()
        await storage.save_snapshot(game)

        loaded = await storage.get_snapshot("game-1")

        assert loaded is not None
        assert loaded.status == GameStatus.PLAYING
        assert loaded.current_round == 1

    async def test_mutating_a_loaded_snapshot_does_not_change_storage(
        self, storage: StoragePort
    ) -> None:
        game = make_game()
        expected = deepcopy(game)
        await storage.save_snapshot(game)

        loaded = await storage.get_snapshot("game-1")
        assert loaded is not None
        loaded.start()
        loaded.teams[0].add_score(10)
        loaded.players[0].update_socket_id("socket-hijacked")
        loaded.rounds[0].script.roles[0].lines.append("Extra line")

        assert await storage.get_snapshot("game-1") == expected

    async def test_mutating_a_game_after_saving_does_not_change_storage(
        self, storage: StoragePort
    ) -> None:
        game = make_game()
        await storage.save_snapshot(game)
        game.start()
        game.teams[0].add_score(10)
        game.rounds[0].role_assignments["player-2"] = 0

        loaded = await storage.get_snapshot("game-1")

        assert loaded is not None
        assert loaded.status == GameStatus.LOBBY
        assert loaded.teams[0].score == 0
        assert loaded.rounds[0].role_assignments == {"player-1": 0}

    async def test_each_load_returns_a_distinct_object(self, storage: StoragePort) -> None:
        await storage.save_snapshot(make_game())

        first = await storage.get_snapshot("game-1")
        second = await storage.get_snapshot("game-1")

        assert first is not None and second is not None
        assert first is not second
        assert first.teams[0] is not second.teams[0]

    # Room code lookup

    async def test_get_game_by_unknown_room_code_is_none(self, storage: StoragePort) -> None:
        assert await storage.get_game_by_room_code("NOPE") is None

    async def test_get_game_by_room_code_returns_the_snapshot(self, storage: StoragePort) -> None:
        game = make_game(room_code="WXYZ")
        await storage.save_snapshot(game)
        await storage.save_snapshot(make_game(game_id="game-2", room_code="QRST"))

        assert await storage.get_game_by_room_code("WXYZ") == game

    async def test_mutating_a_game_loaded_by_room_code_does_not_change_storage(
        self, storage: StoragePort
    ) -> None:
        await storage.save_snapshot(make_game(room_code="WXYZ"))

        loaded = await storage.get_game_by_room_code("WXYZ")
        assert loaded is not None
        loaded.teams[0].add_score(10)

        reloaded = await storage.get_game_by_room_code("WXYZ")
        assert reloaded is not None
        assert reloaded.teams[0].score == 0

    # Deletion

    async def test_delete_game_removes_events_snapshot_and_room_code(
        self, storage: StoragePort
    ) -> None:
        await storage.save_event(make_game_created(room_code="WXYZ"))
        await storage.save_snapshot(make_game(room_code="WXYZ"))

        await storage.delete_game("game-1")

        assert await storage.get_events("game-1") == []
        assert await storage.get_snapshot("game-1") is None
        assert await storage.get_game_by_room_code("WXYZ") is None

    async def test_delete_game_leaves_other_games_alone(self, storage: StoragePort) -> None:
        kept_event = make_game_created(game_id="game-2", room_code="QRST")
        kept_game = make_game(game_id="game-2", room_code="QRST")
        await storage.save_event(make_game_created())
        await storage.save_snapshot(make_game())
        await storage.save_event(kept_event)
        await storage.save_snapshot(kept_game)

        await storage.delete_game("game-1")

        assert await storage.get_events("game-2") == [kept_event]
        assert await storage.get_snapshot("game-2") == kept_game
        assert await storage.get_game_by_room_code("QRST") == kept_game

    async def test_delete_unknown_game_is_a_no_op(self, storage: StoragePort) -> None:
        await storage.delete_game("missing")

        assert await storage.get_events("missing") == []
