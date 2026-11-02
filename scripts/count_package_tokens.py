"""Measures, with the API's free token-counting call, how big each package's long-context prompt is.

The prompt for a package does not depend on any question, so this reads no question at all. It
sets the long-context row's worst-case cost before the cap is chosen (docs/test-plan.md). The
counts go to eval/results/phase5-package-tokens.json.

Usage:
    python scripts/count_package_tokens.py
"""

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import anthropic  # noqa: E402

from advisor.generation import answer  # noqa: E402
from advisor.longcontext import package_records, system_blocks  # noqa: E402
from advisor.packages import PACKAGES  # noqa: E402
from advisor.retrieval.units import build_units  # noqa: E402

OUT = ROOT / "eval" / "results" / "phase5-package-tokens.json"
STORE = ROOT / "data" / "advisor.db"


def main() -> int:
    key = answer.read_key()
    if not key:
        print("No ANTHROPIC_API_KEY. Add it to .env (gitignored), then run again.")
        return 1
    client = anthropic.Anthropic(api_key=key, max_retries=2)
    db = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
    units = build_units(db)
    counts = {}
    for _, name in PACKAGES:
        blocks = system_blocks(package_records(units, [name]))
        result = client.messages.count_tokens(
            model=answer.MODEL, system=blocks, messages=[{"role": "user", "content": "Question: ?"}]
        )
        counts[name] = result.input_tokens
        print(f"{name:<45}{result.input_tokens:>9}")
    OUT.write_text(json.dumps(counts, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Written to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
