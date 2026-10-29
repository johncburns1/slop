"""Tests for the recording realtime stand-in."""

import pytest

from slop.adapters.websocket import Delivery, RecordingRealtime
from slop.domain import RoundStarted, ScriptGenerated
from slop.domain.events import GameEvent
from slop.ports import RealtimePort
from tests.adapters.websocket.contract import (
    RealtimePortContract,
    Received,
    make_game_created,
    make_round_started,
    make_script_generated,
)


class TestRecordingRealtime(RealtimePortContract):
    """Run the RealtimePort contract against RecordingRealtime."""

    @pytest.fixture
    def recording(self) -> RecordingRealtime:
        return RecordingRealtime()

    @pytest.fixture
    def realtime(self, recording: RecordingRealtime) -> RealtimePort:
        return recording

    @pytest.fixture
    def received(self, recording: RecordingRealtime) -> Received:
        async def received(socket_id: str) -> list[GameEvent]:
            return recording.received_by(socket_id)

        return received


async def test_only_the_acting_team_receives_the_script() -> None:
    """The scenario this stand-in exists for: who saw what."""
    realtime = RecordingRealtime()
    for socket_id in ("actor-1", "actor-2", "guesser-1", "guesser-2"):
        await realtime.join_room(socket_id, "ABCD")

    await realtime.broadcast_to_room("ABCD", make_round_started())
    for actor in ("actor-1", "actor-2"):
        await realtime.send_to_player(actor, make_script_generated())

    assert realtime.who_received(ScriptGenerated) == {"actor-1", "actor-2"}
    assert realtime.who_received(RoundStarted) == {"actor-1", "actor-2", "guesser-1", "guesser-2"}


async def test_members_of_tracks_joins_and_leaves() -> None:
    realtime = RecordingRealtime()
    await realtime.join_room("socket-1", "ABCD")
    await realtime.join_room("socket-2", "ABCD")
    await realtime.leave_room("socket-1", "ABCD")

    assert realtime.members_of("ABCD") == {"socket-2"}
    assert realtime.members_of("WXYZ") == frozenset()


async def test_rooms_of_lists_every_room_a_socket_is_in() -> None:
    realtime = RecordingRealtime()
    await realtime.join_room("socket-1", "ABCD")
    await realtime.join_room("socket-1", "WXYZ")

    assert realtime.rooms_of("socket-1") == {"ABCD", "WXYZ"}
    assert realtime.rooms_of("socket-2") == frozenset()


async def test_deliveries_record_how_each_message_arrived() -> None:
    realtime = RecordingRealtime()
    await realtime.join_room("socket-1", "ABCD")
    broadcast, direct = make_game_created(), make_round_started()

    await realtime.broadcast_to_room("ABCD", broadcast)
    await realtime.send_to_player("socket-1", direct)

    assert realtime.deliveries_to("socket-1") == [
        Delivery(socket_id="socket-1", event=broadcast, room_code="ABCD"),
        Delivery(socket_id="socket-1", event=direct, room_code=None),
    ]


async def test_broadcasts_to_records_room_traffic_even_with_no_members() -> None:
    realtime = RecordingRealtime()
    event = make_game_created()

    await realtime.broadcast_to_room("ABCD", event)

    assert realtime.broadcasts_to("ABCD") == [event]
    assert realtime.broadcasts_to("WXYZ") == []


async def test_mutating_a_sent_event_does_not_change_the_record() -> None:
    realtime = RecordingRealtime()
    event = make_script_generated()
    await realtime.send_to_player("socket-1", event)

    event.roles.append({"name": "Intruder", "description": "Should not be recorded"})

    recorded = realtime.received_by("socket-1")[0]
    assert isinstance(recorded, ScriptGenerated)
    assert len(recorded.roles) == 1


async def test_mutating_query_results_does_not_change_the_record() -> None:
    realtime = RecordingRealtime()
    await realtime.join_room("socket-1", "ABCD")
    await realtime.send_to_player("socket-1", make_script_generated())

    recorded = realtime.received_by("socket-1")
    assert isinstance(recorded[0], ScriptGenerated)
    recorded[0].roles.clear()
    recorded.clear()

    [again] = realtime.received_by("socket-1")
    assert isinstance(again, ScriptGenerated)
    assert len(again.roles) == 1


async def test_instances_do_not_share_state() -> None:
    first, second = RecordingRealtime(), RecordingRealtime()
    await first.join_room("socket-1", "ABCD")
    await first.send_to_player("socket-1", make_round_started())

    assert second.members_of("ABCD") == frozenset()
    assert second.received_by("socket-1") == []
