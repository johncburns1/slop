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


def test_evidence_path_makes_the_directory_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SLOP_EVIDENCE_DIR", str(tmp_path))

    path = evidence.evidence_path("scenario/screens/final.png")

    assert path == tmp_path / "scenario" / "screens" / "final.png"
    assert path.parent.is_dir()
    assert not path.exists()


SHOTS = (evidence.Screenshot("scenario/screens/final.png", "The final screen"),)


def test_screenshots_embed_as_images_relative_to_the_report_outside_ci(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)

    text = evidence.screenshots_markdown(SHOTS)

    assert "![The final screen](evidence/scenario/screens/final.png)" in text


def test_screenshots_list_files_and_link_the_artifact_in_ci(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/slop")
    monkeypatch.setenv("GITHUB_RUN_ID", "42")

    text = evidence.screenshots_markdown(SHOTS)

    assert "![" not in text  # the job summary can't show them
    assert "[this run](https://github.com/acme/slop/actions/runs/42#artifacts)" in text
    assert "`evidence/scenario/screens/final.png`: The final screen" in text
