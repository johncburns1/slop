# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Set up the project and run every static check and test.

Usage: uv run scripts/validate.py [--json PATH]

Runs `uv sync --all-extras`, then ruff lint, ruff format check, mypy, and pytest.
Every check runs even if an earlier one fails. Prints a summary, writes a JSON
summary (default: .validation/summary.json), and exits 1 if anything failed.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JSON = ROOT / ".validation" / "summary.json"


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

Runner = Callable[[Check], int]


def run_subprocess(check: Check) -> int:
    """Run a check in the repo root, streaming its output."""
    # `uv run scripts/validate.py` runs this script in its own environment; drop it
    # so the checks use the project's .venv.
    env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    print(f"\n==> {check.name}: {' '.join(check.command)}", flush=True)
    return subprocess.run(check.command, cwd=ROOT, env=env, check=False).returncode


def run_check(check: Check, runner: Runner) -> CheckResult:
    start = time.monotonic()
    exit_code = runner(check)
    duration_s = round(time.monotonic() - start, 3)
    return CheckResult(check.name, " ".join(check.command), exit_code, duration_s)


def run_all(runner: Runner = run_subprocess) -> list[CheckResult]:
    """Run setup, then every check. Skip the checks if setup fails."""
    setup = run_check(SETUP, runner)
    if not setup.passed:
        return [setup]
    return [setup, *(run_check(check, runner) for check in CHECKS)]


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


def main(argv: Sequence[str] | None = None, runner: Runner = run_subprocess) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--json", type=Path, default=DEFAULT_JSON, help="where to write the JSON summary"
    )
    args = parser.parse_args(argv)

    results = run_all(runner)
    print(format_summary(results))
    write_summary(results, args.json)
    print(f"JSON summary: {args.json}")
    return 0 if all_passed(results) else 1


if __name__ == "__main__":
    sys.exit(main())
