"""Command line for the snapshot: python -m advisor.ingest <step>.

Steps run in this order: osv, kev, nvd (slow, resumable), manifest, build.
"""

import argparse
import json
from pathlib import Path

from advisor import store
from advisor.ingest import kev, nvd, osv, raw

DATA = Path("data")
RAW = DATA / "raw"


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m advisor.ingest")
    parser.add_argument("step", choices=["osv", "kev", "nvd", "manifest", "build"])
    step = parser.parse_args().step
    if step == "osv":
        result: object = osv.fetch_all(RAW / "osv")
    elif step == "kev":
        result = kev.fetch(RAW / "kev")
    elif step == "nvd":
        result = nvd.fetch_cves(osv.cve_ids(RAW / "osv"), RAW / "nvd")
    elif step == "manifest":
        manifest = raw.build_manifest(RAW)
        (DATA / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        result = {name: s["records"] for name, s in manifest["sources"].items()}
    else:
        result = store.build(RAW, DATA / "advisor.db")
    print(json.dumps(result, indent=1))  # noqa: T201


if __name__ == "__main__":
    main()
