"""Prints docs/brief/brief.html to docs/brief.pdf with headless Edge or Chrome.

The brief is one A4 page for someone skimming. Every number in it is copied from a written result
(docs/test-results.md and docs/red-team-report.md). The script fails if the PDF has more than one
page, so the brief cannot quietly spill onto a second. No API call is made.

Usage:
    python scripts/make_brief.py
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "brief" / "brief.html"
OUT = ROOT / "docs" / "brief.pdf"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def browser() -> str:
    for name in ("msedge", "chrome", "google-chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    if Path(EDGE).exists():
        return EDGE
    raise SystemExit("No Chromium browser found.")


def page_count(pdf: Path) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes()))


def main() -> int:
    with tempfile.TemporaryDirectory() as profile:
        command = [
            browser(), "--headless=new", "--disable-gpu", "--no-first-run",
            f"--user-data-dir={profile}", "--no-pdf-header-footer",
            f"--print-to-pdf={OUT}", SOURCE.as_uri(),
        ]  # fmt: skip
        subprocess.run(command, capture_output=True, timeout=90, check=False)  # noqa: S603
    if not OUT.exists():
        raise SystemExit("The browser wrote no PDF.")
    pages = page_count(OUT)
    if pages != 1:
        raise SystemExit(f"The brief is {pages} pages. It must be one.")
    print(f"Wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB, 1 page)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
