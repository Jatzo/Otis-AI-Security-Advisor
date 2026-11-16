"""Makes docs/img/otis-search.gif: a query typed into a mockup of the planned live search page, and
the 10 records the real keyword search returns for it.

The results are not drawn by hand. The script runs the shipped retrieval (keyword search over each
record's header and body, R1) over the published text for one dev question, in the local store, and
writes the ranking, the scores and the time it took to docs/img/demo/search-data.js. The frame page
shows that file, and make_demo_gif.py shoots it tick by tick. The frame says the interface is a
mockup. No model is called.

Needs the local store, Edge or Chrome, and ffmpeg on the path.

Usage:
    python scripts/make_search_gif.py
"""

import json
import re
import sqlite3
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import make_demo_gif  # noqa: E402
from build_search_index import published_docs  # noqa: E402

from advisor.retrieval.bm25 import Bm25Index  # noqa: E402
from advisor.retrieval.metrics import evidence_ids  # noqa: E402

QUESTION_ID = "vr-002"  # a dev question whose three needed records land at ranks 3, 5 and 8
FRAME = ROOT / "docs" / "img" / "demo" / "frame-search.html"
DATA = ROOT / "docs" / "img" / "demo" / "search-data.js"
OUT = ROOT / "docs" / "img" / "otis-search.gif"
SOURCES = {"ghsa": "GitHub", "nvd": "NVD", "kev": "KEV"}
TIMED_RUNS = 30


def read_row(path: Path, row_id: str) -> dict:
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["id"] == row_id:
            return row
    raise SystemExit(f"{row_id} is not in {path.name}.")


def one_line(header: str) -> str:
    """The parts of a record header a result row shows: package, date, severity and score."""
    parts = []
    package = re.search(r"Package: (\S+) \((\w+)\)", header)
    if package:
        parts.append(f"{package.group(1).split(':')[-1]} ({package.group(2)})")
    published = re.search(r"Published (\d{4}-\d{2}-\d{2})", header)
    if published:
        parts.append(f"published {published.group(1)}")
    severity = re.search(r"Severity (\w+)", header)
    if severity:
        parts.append(severity.group(1).capitalize())
    score = re.search(r"CVSS v3 (\d+(?:\.\d+)?)", header)
    if score:
        parts.append(f"CVSS {score.group(1)}")
    return ", ".join(parts) or header[:110]


def search_data(db: sqlite3.Connection) -> dict:
    docs = published_docs(db)
    by_id = {d.doc_id: d for d in docs}
    index = Bm25Index(docs, with_header=True)
    question = read_row(ROOT / "eval" / "questions.jsonl", QUESTION_ID)
    needed = evidence_ids(read_row(ROOT / "eval" / "gold.jsonl", QUESTION_ID))
    times = []
    for _ in range(TIMED_RUNS):
        start = time.perf_counter()
        ranked = index.search(question["question"], 100)
        times.append((time.perf_counter() - start) * 1000)
    top = ranked[:10]
    return {
        "question": QUESTION_ID,
        "query": question["question"],
        "units": len(docs),
        "ms": round(statistics.median(times), 1),
        "needed": len(needed),
        "found": sum(doc_id in needed for doc_id, _ in top),
        "results": [
            {
                "id": doc_id.split(":", 1)[1], "source": SOURCES[doc_id.split(":", 1)[0]],
                "summary": one_line(by_id[doc_id].header), "score": round(score, 2),
                "needed": doc_id in needed,
            }
            for doc_id, score in top
        ],
    }  # fmt: skip


def main() -> int:
    db = sqlite3.connect(f"file:{ROOT / 'data' / 'advisor.db'}?mode=ro", uri=True)
    data = search_data(db)
    DATA.write_text(
        "// Written by scripts/make_search_gif.py from the real keyword search. Do not edit.\n"
        f"window.SEARCH = {json.dumps(data, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {DATA.relative_to(ROOT)}: {data['found']} of {data['needed']} needed records "
          f"in the top 10, {data['ms']} ms.")  # fmt: skip
    make_demo_gif.render(FRAME, OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
