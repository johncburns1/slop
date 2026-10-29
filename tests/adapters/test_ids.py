"""Tests for the id generator adapters."""

from slop.adapters.ids import ROOM_CODE_ALPHABET, RandomIds, SequentialIds


def test_random_ids_are_unique():
    ids = RandomIds()

    assert len({ids.new_id() for _ in range(100)}) == 100


def test_random_room_codes_are_four_letters_from_the_alphabet():
    codes = [RandomIds().new_room_code() for _ in range(100)]

    assert all(len(code) == 4 and set(code) <= set(ROOM_CODE_ALPHABET) for code in codes)


def test_sequential_ids_count_up():
    ids = SequentialIds()

    assert [ids.new_id() for _ in range(3)] == ["id-1", "id-2", "id-3"]


def test_sequential_room_codes_use_the_script_then_count_up():
    ids = SequentialIds(["ABCD", "WXYZ"])

    assert [ids.new_room_code() for _ in range(4)] == ["ABCD", "WXYZ", "ROOM1", "ROOM2"]
