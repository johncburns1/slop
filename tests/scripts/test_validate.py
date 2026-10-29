"""Tests for the one-command validation script."""

import json
from pathlib import Path

from scripts import validate
from scripts.validate import CHECKS, SETUP, Check, Outcome


def fake_runner(
    exit_codes: dict[str, int], outputs: dict[str, str] | None = None
) -> validate.Runner:
    """Build a runner that returns canned exit codes and output and records what ran."""

    def run(check: Check, env: dict[str, str]) -> Outcome:
        run.calls.append(check.name)  # type: ignore[attr-defined]
        run.envs.append(env)  # type: ignore[attr-defined]
        return Outcome(exit_codes.get(check.name, 0), (outputs or {}).get(check.name, ""))

    run.calls = []  # type: ignore[attr-defined]
    run.envs = []  # type: ignore[attr-defined]
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


def test_json_summary_keeps_its_format(tmp_path: Path):
    results = validate.run_all(fake_runner({}, {"pytest": "lots of output"}))
    path = tmp_path / "summary.json"

    validate.write_summary(results, path)

    summary = json.loads(path.read_text())
    assert set(summary) == {"passed", "failed", "checks"}
    assert set(summary["checks"][0]) == {"name", "command", "passed", "exit_code", "duration_s"}


def test_main_exit_code_reflects_results(tmp_path: Path):
    path = tmp_path / "summary.json"
    args = ["--json", str(path), "--report", str(tmp_path / "report.md")]
    assert validate.main(args, runner=fake_runner({})) == 0
    assert validate.main(args, runner=fake_runner({"pytest": 1})) == 1
    assert json.loads(path.read_text())["failed"] == ["pytest"]


def test_checks_run_with_evidence_dir_in_env(tmp_path: Path):
    runner = fake_runner({})
    report = tmp_path / "out" / "report.md"

    validate.main(["--json", str(tmp_path / "s.json"), "--report", str(report)], runner=runner)

    evidence_dir = str(tmp_path / "out" / "evidence")
    assert all(env == {"SLOP_EVIDENCE_DIR": evidence_dir} for env in runner.envs)  # type: ignore[attr-defined]


def test_main_clears_stale_evidence_and_writes_report(tmp_path: Path):
    stale = tmp_path / "evidence" / "old.txt"
    stale.parent.mkdir()
    stale.write_text("from a previous run")
    report = tmp_path / "report.md"

    validate.main(["--json", str(tmp_path / "s.json"), "--report", str(report)], fake_runner({}))

    assert not stale.exists()
    assert "# Validation report" in report.read_text()


def test_report_has_result_table_with_durations():
    results = validate.run_all(fake_runner({"mypy": 1}))

    report = validate.format_report(results, evidence=[])

    assert "**FAILED**: mypy" in report
    assert "| Check | Result | Duration | Command |" in report
    assert "| mypy | ❌ FAIL |" in report
    assert "| pytest | ✅ PASS |" in report
    assert "`uv run --no-sync mypy src scripts`" in report


def test_report_shows_passed_when_everything_passes():
    report = validate.format_report(validate.run_all(fake_runner({})), evidence=[])

    assert "**PASSED**: all 5 checks" in report
    assert "## Failures" not in report


def test_report_includes_output_tail_of_failing_check_only():
    output = "\n".join(f"line {n}" for n in range(1, 201))
    results = validate.run_all(
        fake_runner({"pytest": 1}, {"pytest": output, "mypy": "mypy chatter"})
    )

    report = validate.format_report(results, evidence=[])

    assert "## Failures" in report
    assert "### pytest (exit 1)" in report
    assert "line 200" in report
    assert "line 1\n" not in report
    assert f"last {validate.TAIL_LINES} lines" in report
    assert "mypy chatter" not in report


def test_report_fences_output_containing_backticks():
    results = validate.run_all(fake_runner({"pytest": 1}, {"pytest": "```\nnot the end"}))

    report = validate.format_report(results, evidence=[])

    assert "````\n```\nnot the end\n````" in report


def test_report_says_when_no_evidence_was_captured():
    report = validate.format_report(validate.run_all(fake_runner({})), evidence=[])

    assert "## Evidence" in report
    assert "No evidence captured" in report


def test_collect_evidence_lists_files_in_order(tmp_path: Path):
    assert validate.collect_evidence(tmp_path / "missing") == []
    (tmp_path / "b.txt").write_text("b")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "a.md").write_text("a")

    files = validate.collect_evidence(tmp_path)

    assert [file.relative_to(tmp_path).as_posix() for file in files] == ["b.txt", "nested/a.md"]


def test_report_embeds_markdown_and_text_evidence(tmp_path: Path):
    (tmp_path / "views.md").write_text("### Player view\nAlice sees the script.\n")
    (tmp_path / "events.jsonl").write_text('{"type": "GameCreated"}\n')
    (tmp_path / "shot.png").write_bytes(b"\x89PNG")
    results = validate.run_all(fake_runner({}))

    report = validate.format_report(results, validate.collect_evidence(tmp_path), tmp_path)

    assert "### views.md\n\n### Player view\nAlice sees the script." in report
    assert '### events.jsonl\n\n```\n{"type": "GameCreated"}\n```' in report
    assert "### shot.png\n\nNot embedded" in report


def test_report_truncates_large_evidence(tmp_path: Path):
    (tmp_path / "big.log").write_text("x" * (validate.MAX_EMBED_BYTES + 10))

    report = validate.format_report([], validate.collect_evidence(tmp_path), tmp_path)

    assert "x" * validate.MAX_EMBED_BYTES in report
    assert "x" * (validate.MAX_EMBED_BYTES + 1) not in report
    assert "Truncated to" in report
