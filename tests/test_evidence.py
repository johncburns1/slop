"""Tests for the evidence helper tests use to contribute to the validation report."""

from pathlib import Path

import pytest

from tests import evidence


def test_writes_to_dir_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SLOP_EVIDENCE_DIR", str(tmp_path / "ev"))

    path = evidence.write_evidence("scenario/events.jsonl", '{"type": "GameCreated"}\n')

    assert path == tmp_path / "ev" / "scenario" / "events.jsonl"
    assert path.read_text() == '{"type": "GameCreated"}\n'


def test_defaults_to_validation_evidence_dir(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SLOP_EVIDENCE_DIR", raising=False)

    assert (
        evidence.evidence_dir() == Path(__file__).resolve().parent.parent / ".validation/evidence"
    )
