"""Command line for the snapshot: python -m advisor.ingest <step>.

Steps run in this order: osv, kev, nvd (slow, resumable), manifest, build, report, sample.
"""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from advisor import report, store
from advisor.ingest import kev, nvd, osv, raw, sample

DATA = Path("data")
RAW = DATA / "raw"
DOCS = Path("docs")


def snapshot_id() -> str:
    """Named from the records on disk now, not from a manifest that may be out of date."""
    return raw.build_manifest(RAW)["snapshot_id"]


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m advisor.ingest")
    parser.add_argument(
        "step", choices=["osv", "kev", "nvd", "manifest", "build", "report", "sample"]
    )
    step = parser.parse_args().step
    if step == "osv":
        result: object = osv.fetch_all(RAW / "osv")
    elif step == "kev":
        result = kev.fetch(RAW / "kev")
    elif step == "nvd":
        result = nvd.fetch_cves(osv.cve_ids(RAW / "osv"), RAW / "nvd")
    elif step == "manifest":
        manifest = raw.build_manifest(RAW)
        text = json.dumps(manifest, indent=1) + raw.LF
        (DATA / "manifest.json").write_text(text, encoding="utf-8", newline=raw.LF)
        result = {name: s["records"] for name, s in manifest["sources"].items()}
    elif step == "build":
        result = store.build(RAW, DATA / "advisor.db")
    elif step == "sample":
        result = sample.write_sample(RAW, DATA / "advisor.db", DATA / "sample", snapshot_id())
    else:
        with closing(sqlite3.connect(DATA / "advisor.db")) as db:
            text = report.render(db, snapshot_id())
        (DOCS / "data-report.md").write_text(text, encoding="utf-8", newline=raw.LF)
        result = {"written": "docs/data-report.md", "snapshot_id": snapshot_id()}
    print(json.dumps(result, indent=1))  # noqa: T201


if __name__ == "__main__":
    main()
