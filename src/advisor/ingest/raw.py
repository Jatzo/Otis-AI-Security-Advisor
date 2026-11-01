"""The raw snapshot on disk: one JSON file per source record, plus a manifest of hashes.

Records are written with sorted keys so the same record always hashes the same, which
is what lets the weekly drift check tell a real upstream change from a reformat.
"""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FETCH_LOG = "_fetch.json"
# Files are written with LF on every platform. Windows would otherwise write CRLF, and the
# same record would hash differently once git normalises it.
LF = "\n"
# Record IDs come from upstream feeds and become file names, so only the shapes the
# sources really use are allowed. Anything else, "../" included, is refused.
RECORD_ID = re.compile(
    r"GHSA(-[23456789cfghjmpqrvwx]{4}){3}|CVE-\d{4}-\d{4,}|known_exploited_vulnerabilities"
)


def write_record(directory: Path, record_id: str, record: Any) -> Path:
    if not RECORD_ID.fullmatch(record_id):
        raise ValueError(f"Refusing to write a record with an unexpected ID: {record_id!r}")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record_id}.json"
    # Always LF and a closing newline, so a record hashes the same on every machine and no
    # tool (git, an editor, the pre-commit end-of-file fixer) has anything to normalise.
    text = json.dumps(record, sort_keys=True, indent=1) + LF
    path.write_text(text, encoding="utf-8", newline=LF)
    return path


def read_record(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def record_paths(directory: Path) -> list[Path]:
    return sorted(p for p in directory.glob("*.json") if p.name != FETCH_LOG)


def log_fetch(directory: Path, source: str, endpoint: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    log = {"source": source, "endpoint": endpoint, "fetched_at": now()}
    text = json.dumps(log, indent=1) + LF
    (directory / FETCH_LOG).write_text(text, encoding="utf-8", newline=LF)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest(raw_root: Path) -> dict:
    """Describe every source folder under raw_root: when it was fetched, from where,
    and the hash of each record, so a snapshot can be named and checked later."""
    sources = {}
    for directory in sorted(p for p in raw_root.iterdir() if p.is_dir()):
        log_path = directory / FETCH_LOG
        log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
        files = {p.stem: sha256_of(p) for p in record_paths(directory)}
        sources[directory.name] = {**log, "records": len(files), "sha256": files}
    return {"snapshot_id": snapshot_id(sources), "built_at": now(), "sources": sources}


def snapshot_id(sources: dict) -> str:
    """A name for the data itself: a hash of every record hash. Dates are left out on
    purpose, because the fetch time changes on every resume and would rename the same data."""
    lines = sorted(
        f"{name}/{record}:{digest}"
        for name, s in sources.items()
        for record, digest in s["sha256"].items()
    )
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()[:12]


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
