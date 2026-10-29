"""Write evidence files that the validation report embeds.

`scripts/validate.py` sets SLOP_EVIDENCE_DIR for the checks it runs and lists every
file in it under the report's "Evidence" section. Use `.md` for content to render
as-is (e.g. player views), and `.jsonl`/`.json`/`.txt`/`.log` for content shown in a
code block (e.g. event logs). Name files `<scenario>/<what>.<ext>`.
"""

import os
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
