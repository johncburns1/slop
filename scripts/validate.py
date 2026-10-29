# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Set up the project and run every static check and test.

Usage: uv run scripts/validate.py [--json PATH] [--report PATH]

Runs `uv sync --all-extras`, then ruff lint, ruff format check, mypy, and pytest.
Every check runs even if an earlier one fails. Prints a summary, writes a JSON
summary (default: .validation/summary.json) and a Markdown report (default:
.validation/report.md), and exits 1 if anything failed.

Evidence: checks run with SLOP_EVIDENCE_DIR set to an `evidence/` directory next to
the report, emptied at the start of each run. Tests contribute evidence (event logs,
player views) by writing files there, e.g. with `tests.evidence.write_evidence`. The
report embeds Markdown files as-is, other text files in code blocks, and lists the rest.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JSON = ROOT / ".validation" / "summary.json"
DEFAULT_REPORT = ROOT / ".validation" / "report.md"
EVIDENCE_ENV = "SLOP_EVIDENCE_DIR"
TAIL_LINES = 60
MAX_EMBED_BYTES = 20_000
TEXT_SUFFIXES = {".txt", ".log", ".json", ".jsonl", ".csv", ".yaml", ".yml"}


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]


@dataclass(frozen=True)
class CheckResult:
    name: str
    command: str
    exit_code: int
    duration_s: float
    output: str = ""

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


SETUP = Check("setup", ("uv", "sync", "--all-extras"))
CHECKS = (
    Check("ruff-lint", ("uv", "run", "--no-sync", "ruff", "check")),
    Check("ruff-format", ("uv", "run", "--no-sync", "ruff", "format", "--check")),
    Check("mypy", ("uv", "run", "--no-sync", "mypy", "src", "scripts")),
    Check("pytest", ("uv", "run", "--no-sync", "pytest")),
)


class Outcome(NamedTuple):
    exit_code: int
    output: str


Runner = Callable[[Check, Mapping[str, str]], Outcome]


def run_subprocess(check: Check, extra_env: Mapping[str, str]) -> Outcome:
    """Run a check in the repo root, streaming its output and capturing it."""
    # `uv run scripts/validate.py` runs this script in its own environment; drop it
    # so the checks use the project's .venv.
    env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    env.update(extra_env)
    print(f"\n==> {check.name}: {' '.join(check.command)}", flush=True)
    lines: list[str] = []
    with subprocess.Popen(
        check.command,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    ) as process:
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            lines.append(line)
    return Outcome(process.returncode, "".join(lines))


def run_check(check: Check, runner: Runner, env: Mapping[str, str]) -> CheckResult:
    start = time.monotonic()
    outcome = runner(check, env)
    duration_s = round(time.monotonic() - start, 3)
    command = " ".join(check.command)
    return CheckResult(check.name, command, outcome.exit_code, duration_s, outcome.output)


def run_all(
    runner: Runner = run_subprocess, env: Mapping[str, str] | None = None
) -> list[CheckResult]:
    """Run setup, then every check. Skip the checks if setup fails."""
    env = env or {}
    setup = run_check(SETUP, runner, env)
    if not setup.passed:
        return [setup]
    return [setup, *(run_check(check, runner, env) for check in CHECKS)]


def all_passed(results: Sequence[CheckResult]) -> bool:
    return all(result.passed for result in results)


def failed_names(results: Sequence[CheckResult]) -> list[str]:
    return [result.name for result in results if not result.passed]


def format_summary(results: Sequence[CheckResult]) -> str:
    lines = ["", "Validation summary"]
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(f"  {status}  {result.name:<12} {result.duration_s:7.2f}s")
    failed = failed_names(results)
    lines.append(f"FAILED: {', '.join(failed)}" if failed else "All checks passed.")
    return "\n".join(lines)


def write_summary(results: Sequence[CheckResult], path: Path) -> None:
    summary = {
        "passed": all_passed(results),
        "failed": failed_names(results),
        "checks": [
            {
                "name": result.name,
                "command": result.command,
                "passed": result.passed,
                "exit_code": result.exit_code,
                "duration_s": result.duration_s,
            }
            for result in results
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2) + "\n")


def fence(text: str, info: str = "") -> str:
    """Wrap text in a code fence longer than any backtick run inside it."""
    longest = run = 0
    for char in text:
        run = run + 1 if char == "`" else 0
        longest = max(longest, run)
    ticks = "`" * max(3, longest + 1)
    return f"{ticks}{info}\n{text.rstrip(chr(10))}\n{ticks}"


def tail(text: str, lines: int = TAIL_LINES) -> str:
    return "\n".join(text.rstrip("\n").splitlines()[-lines:])


def collect_evidence(evidence_dir: Path) -> list[Path]:
    """Return every file under the evidence directory, sorted by path."""
    if not evidence_dir.is_dir():
        return []
    return sorted(path for path in evidence_dir.rglob("*") if path.is_file())


def format_evidence(path: Path, evidence_dir: Path) -> str:
    name = path.relative_to(evidence_dir).as_posix()
    suffix = path.suffix.lower()
    if suffix != ".md" and suffix not in TEXT_SUFFIXES:
        return f"### {name}\n\nNot embedded ({path.stat().st_size} bytes); see the artifact."
    data = path.read_bytes()
    text = data[:MAX_EMBED_BYTES].decode("utf-8", errors="replace")
    note = (
        f"\n\n_Truncated to {MAX_EMBED_BYTES} of {len(data)} bytes; see the artifact._"
        if len(data) > MAX_EMBED_BYTES
        else ""
    )
    body = text.rstrip("\n") if suffix == ".md" else fence(text)
    return f"### {name}\n\n{body}{note}"


def format_report(
    results: Sequence[CheckResult], evidence: Sequence[Path], evidence_dir: Path | None = None
) -> str:
    """Render a short Markdown report: result table, failure output tails, evidence."""
    failed = failed_names(results)
    status = (
        f"**FAILED**: {', '.join(failed)}" if failed else f"**PASSED**: all {len(results)} checks"
    )
    sections = [
        "# Validation report",
        status,
        "| Check | Result | Duration | Command |\n| --- | --- | --- | --- |\n"
        + "\n".join(
            f"| {r.name} | {'✅ PASS' if r.passed else '❌ FAIL'} | {r.duration_s:.2f}s "
            f"| `{r.command}` |"
            for r in results
        ),
    ]
    if failed:
        sections.append("## Failures")
        for result in results:
            if not result.passed:
                sections.append(
                    f"### {result.name} (exit {result.exit_code})\n\n"
                    f"Output, last {TAIL_LINES} lines:\n\n{fence(tail(result.output))}"
                )
    sections.append("## Evidence")
    if evidence and evidence_dir is not None:
        sections.extend(format_evidence(path, evidence_dir) for path in evidence)
    else:
        sections.append(
            f"No evidence captured. Tests add evidence by writing files to `${EVIDENCE_ENV}`."
        )
    return "\n\n".join(sections) + "\n"


def write_report(results: Sequence[CheckResult], path: Path, evidence_dir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_report(results, collect_evidence(evidence_dir), evidence_dir))


def main(argv: Sequence[str] | None = None, runner: Runner = run_subprocess) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--json", type=Path, default=DEFAULT_JSON, help="where to write the JSON summary"
    )
    parser.add_argument(
        "--report", type=Path, default=DEFAULT_REPORT, help="where to write the Markdown report"
    )
    args = parser.parse_args(argv)

    evidence_dir = args.report.parent / "evidence"
    shutil.rmtree(evidence_dir, ignore_errors=True)
    results = run_all(runner, {EVIDENCE_ENV: str(evidence_dir)})
    print(format_summary(results))
    write_summary(results, args.json)
    write_report(results, args.report, evidence_dir)
    print(f"JSON summary: {args.json}")
    print(f"Report: {args.report}")
    return 0 if all_passed(results) else 1


if __name__ == "__main__":
    sys.exit(main())
