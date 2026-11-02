"""The blind spot-check: draw a sample of replies, then build the sheet Joe marks by hand.

docs/test-plan.md. The sample is drawn once, by a seeded choice from the question ids and types
only, before any test row is run, and committed. The sheet is built after the rows are in. It shows
the question, the reply as a reader would get it and links to the records named in them. It does
not show the gold, the scorer's verdict, the checker's route or which row a reply came from.

Usage:
    python scripts/spotcheck.py draw --split test
    python scripts/spotcheck.py sheet --split test
"""

import argparse
import html
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from advisor.generation.reading import ANY_ID, normal_id, read_reply  # noqa: E402

RESULTS = ROOT / "eval" / "results"
SEED = 20261102
# From the system (G): how many of each type. From the baseline (B): this many, any type.
SYSTEM = {"lookup": 4, "version": 4, "disagree": 4, "multihop": 3, "abstain": 3}
BASELINE = 6
FILES = {
    "dev": {"G": "generation-dev-checked.jsonl", "B": "baseline-dev.jsonl"},
    "test": {"G": "test-generation-checked.jsonl", "B": "baseline-test.jsonl"},
}


def sample_path(split: str) -> Path:
    return RESULTS / ("spotcheck-sample.json" if split == "test" else "spotcheck-sample-dev.json")


def read_lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def draw(questions: list[dict]) -> list[dict]:
    """Seeded and shuffled, from ids and types only. The question text is not looked at."""
    rng = random.Random(SEED)  # noqa: S311 - a seeded, repeatable choice, not security
    by_type: dict[str, list[str]] = {}
    for q in sorted(questions, key=lambda q: q["id"]):
        by_type.setdefault(q["type"], []).append(q["id"])
    chosen = {name: rng.sample(by_type[name], count) for name, count in SYSTEM.items()}
    taken = {i for ids in chosen.values() for i in ids}
    rest = sorted(q["id"] for q in questions if q["id"] not in taken)
    entries = [{"id": i, "row": "G"} for ids in chosen.values() for i in ids]
    entries += [{"id": i, "row": "B"} for i in rng.sample(rest, BASELINE)]
    rng.shuffle(entries)
    return [{"n": n, **entry} for n, entry in enumerate(entries, start=1)]


def links(text: str) -> list[tuple[str, str]]:
    """A link for each advisory or CVE ID in the text, built from the ID alone."""
    found = []
    for found_id in dict.fromkeys(normal_id(raw) for raw in ANY_ID.findall(text)):
        if found_id.startswith("GHSA-"):
            found.append((found_id, f"https://github.com/advisories/{found_id}"))
        else:
            found.append((found_id, f"https://nvd.nist.gov/vuln/detail/{found_id}"))
    return found


def reader_view(text: str) -> str:
    """The reply as a reader would get it: what was answered, in plain lines. Everything is escaped
    because it comes from a model that read upstream text."""
    answer, problem = read_reply(text)
    if answer is None:
        why, raw = html.escape(problem or ""), html.escape(text[:1500])
        return f"<p><em>The reply could not be read ({why}).</em></p><pre>{raw}</pre>"
    if answer["abstain"]:
        # No explanation: the wording of a refusal would name the row that wrote it.
        return "<p><em>Declined to answer.</em></p>"
    parts = []
    if answer["verdict"] is not None:
        parts.append(f"<li>Verdict: <b>{html.escape(answer['verdict'])}</b></li>")
    if answer["ids"]:
        parts.append(f"<li>IDs: {html.escape(', '.join(answer['ids']))}</li>")
    if answer["value"] is not None:
        parts.append(f"<li>Value: <b>{html.escape(answer['value'])}</b></li>")
    d = answer["disagreement"]
    if d["flagged"] or any(v is not None for v in d["values"].values()):
        values = ", ".join(f"{k} {html.escape(str(v))}" for k, v in d["values"].items())
        parts.append(
            f"<li>Sources differ: <b>{'yes' if d['flagged'] else 'no'}</b> ({values})</li>"
        )
    body = "<ul>" + "".join(parts) + "</ul>" if parts else ""
    return f"{body}<p>{html.escape(answer['explanation'])}</p>"


PAGE = """<!doctype html><html lang="en-GB"><meta charset="utf-8"><title>Spot-check</title>
<style>body{{font:15px/1.5 system-ui;max-width:52rem;margin:2rem auto;padding:0 1rem}}
section{{border-top:1px solid #999;padding:1rem 0}}textarea{{width:100%}}label{{margin-right:1rem}}
pre{{white-space:pre-wrap}}</style>
<h1>Spot-check: {count} replies</h1>
<p>Mark each reply right, wrong or can't tell, as you would if you had looked the answer up in the
linked records yourself. You are not shown the gold, the scorer's verdict or which system wrote it.
When you have marked them all, press the button and send the text it gives you back.</p>
{sections}
<p><button id="go">Make my marks</button></p><textarea id="out" rows="10" readonly></textarea>
<script>
document.getElementById("go").onclick = function () {{
  var marks = {{}};
  document.querySelectorAll("section").forEach(function (s) {{
    var n = s.dataset.n, pick = s.querySelector("input:checked");
    marks[n] = {{mark: pick ? pick.value : null, note: s.querySelector("textarea").value}};
  }});
  var box = document.getElementById("out");
  box.value = JSON.stringify(marks, null, 1);
  box.select();
}};
</script></html>"""


def section(entry: dict, question: str, text: str) -> str:
    seen = links(question + " " + text)
    anchors = " ".join(
        f'<a href="{url}" rel="noreferrer">{html.escape(name)}</a>' for name, url in seen
    )
    n = entry["n"]
    radios = "".join(
        f'<label><input type="radio" name="m{n}" value="{v}"> {label}</label>'
        for v, label in (("right", "Right"), ("wrong", "Wrong"), ("unsure", "Can't tell"))
    )
    return (
        f'<section data-n="{n}"><h2>{n}</h2><p><b>{html.escape(question)}</b></p>'
        f"{reader_view(text)}<p>Records: {anchors or 'none named'}</p>"
        f'<p>{radios}</p><textarea rows="2" placeholder="Note (optional)"></textarea></section>'
    )


def build_sheet(split: str, sample: list[dict], questions: dict[str, dict]) -> str:
    replies = {}
    for row, name in FILES[split].items():
        replies[row] = {x["id"]: x["text"] for x in read_lines(RESULTS / name) if x["run"] == 1}
    parts = [section(e, questions[e["id"]]["question"], replies[e["row"]][e["id"]]) for e in sample]
    return PAGE.format(count=len(sample), sections="\n".join(parts))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["draw", "sheet"])
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    args = parser.parse_args()
    questions = [
        q for q in read_lines(ROOT / "eval" / "questions.jsonl") if q["split"] == args.split
    ]
    path = sample_path(args.split)
    if args.command == "draw":
        if path.exists():
            print(f"{path.name} already exists. The sample is drawn once.")
            return 1
        sample = draw(questions)
        path.write_text(json.dumps(sample, indent=1) + "\n", encoding="utf-8")
        print(f"{len(sample)} replies drawn: {path.relative_to(ROOT)}")
        return 0
    sample = json.loads(path.read_text(encoding="utf-8"))
    sheet = RESULTS / f"spotcheck-sheet-{args.split}.html"
    sheet.write_text(
        build_sheet(args.split, sample, {q["id"]: q for q in questions}), encoding="utf-8"
    )
    print(f"Sheet written: {sheet.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
