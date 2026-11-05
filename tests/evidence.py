"""Write evidence files that the validation report embeds.

`scripts/validate.py` sets SLOP_EVIDENCE_DIR for the checks it runs and lists every
file in it under the report's "Evidence" section. Use `.md` for content to render
as-is (e.g. player views), and `.jsonl`/`.json`/`.txt`/`.log` for content shown in a
code block (e.g. event logs). Name files `<scenario>/<what>.<ext>`.

Other files, such as screenshots, are only listed in the report. CI uploads them in its
validation artifact, and `screenshots_markdown` writes the Markdown that points at them.
"""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parent.parent / ".validation" / "evidence"


def evidence_dir() -> Path:
    return Path(os.environ.get("SLOP_EVIDENCE_DIR", DEFAULT_DIR))


def write_evidence(name: str, content: str) -> Path:
    """Write content to `name` inside the evidence directory and return its path."""
    path = evidence_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def evidence_path(name: str) -> Path:
    """Return where `name` goes in the evidence directory, for tools that write files."""
    path = evidence_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@dataclass(frozen=True)
class Screenshot:
    name: str  # path inside the evidence directory
    caption: str


def screenshots_markdown(shots: Sequence[Screenshot]) -> str:
    """Markdown for screenshots, to be read from `.validation/report.md`.

    The evidence directory sits next to the report, so locally the images embed. CI
    also uses the report as its job summary, which can't show local images, so there
    it lists the files and links to the run holding the artifact.
    """
    run_id = os.environ.get("GITHUB_RUN_ID")
    if run_id is None:
        return "\n\n".join(
            f"{shot.caption}:\n\n![{shot.caption}](evidence/{shot.name})" for shot in shots
        )
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run_url = f"{server}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{run_id}#artifacts"
    files = "\n".join(f"- `evidence/{shot.name}`: {shot.caption}" for shot in shots)
    return (
        "GitHub's job summary can't show local images. Download the `validation-summary` "
        f"artifact from [this run]({run_url}) to see these files:\n\n{files}"
    )
