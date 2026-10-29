"""Tests for the one-command validation script."""

import json
from pathlib import Path

from scripts import validate
from scripts.validate import CHECKS, SETUP, Check


def fake_runner(exit_codes: dict[str, int]) -> validate.Runner:
    """Build a runner that returns canned exit codes and records what ran."""

    def run(check: Check) -> int:
        run.calls.append(check.name)  # type: ignore[attr-defined]
        return exit_codes.get(check.name, 0)

    run.calls = []  # type: ignore[attr-defined]
    return run


def test_checks_cover_lint_format_types_and_tests():
    names = [check.name for check in CHECKS]
    assert names == ["ruff-lint", "ruff-format", "mypy", "pytest"]


def test_setup_installs_all_extras():
    assert SETUP.command == ("uv", "sync", "--all-extras")


def test_all_checks_pass():
    runner = fake_runner({})
    results = validate.run_all(runner)

    assert runner.calls == ["setup", "ruff-lint", "ruff-format", "mypy", "pytest"]  # type: ignore[attr-defined]
    assert all(result.passed for result in results)
    assert validate.all_passed(results)


def test_failed_check_is_reported_and_later_checks_still_run():
    runner = fake_runner({"mypy": 1})
    results = validate.run_all(runner)

    assert runner.calls == ["setup", "ruff-lint", "ruff-format", "mypy", "pytest"]  # type: ignore[attr-defined]
    failed = [result.name for result in results if not result.passed]
    assert failed == ["mypy"]
    assert not validate.all_passed(results)


def test_failed_setup_skips_checks():
    runner = fake_runner({"setup": 2})
    results = validate.run_all(runner)

    assert runner.calls == ["setup"]  # type: ignore[attr-defined]
    assert [result.name for result in results] == ["setup"]
    assert results[0].exit_code == 2
    assert not validate.all_passed(results)


def test_json_summary_lists_each_check(tmp_path: Path):
    results = validate.run_all(fake_runner({"pytest": 1}))
    path = tmp_path / "out" / "summary.json"

    validate.write_summary(results, path)

    summary = json.loads(path.read_text())
    assert summary["passed"] is False
    assert summary["failed"] == ["pytest"]
    by_name = {check["name"]: check for check in summary["checks"]}
    assert by_name["pytest"]["passed"] is False
    assert by_name["pytest"]["exit_code"] == 1
    assert by_name["mypy"]["passed"] is True
    assert by_name["mypy"]["command"] == "uv run --no-sync mypy src scripts"
    assert all(isinstance(check["duration_s"], float) for check in summary["checks"])


def test_human_summary_names_failed_check():
    results = validate.run_all(fake_runner({"ruff-format": 1}))

    text = validate.format_summary(results)

    assert "FAIL  ruff-format" in text
    assert "PASS  pytest" in text
    assert "FAILED: ruff-format" in text


def test_main_exit_code_reflects_results(tmp_path: Path):
    path = tmp_path / "summary.json"
    assert validate.main(["--json", str(path)], runner=fake_runner({})) == 0
    assert validate.main(["--json", str(path)], runner=fake_runner({"pytest": 1})) == 1
    assert json.loads(path.read_text())["failed"] == ["pytest"]
