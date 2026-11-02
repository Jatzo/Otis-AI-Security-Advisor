"""The cross-row analysis runs end to end on saved dev results copied into a scratch folder."""

import csv
import importlib.util
import json
import shutil
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "analyse_test_for_tests", Path("scripts/analyse_test.py")
)
analysis = importlib.util.module_from_spec(spec)
sys.modules["analyse_test_for_tests"] = analysis
spec.loader.exec_module(analysis)


def test_the_dev_rows_give_a_per_question_file_and_the_named_comparisons(tmp_path, monkeypatch):
    results = Path("eval/results")
    for name in ("baseline-dev.scored.jsonl", "generation-dev-raw.scored.jsonl",
                 "generation-dev-checked.scored.jsonl", "generation-dev-checked.jsonl",
                 "generation-dev-raw.jsonl", "retrieval-dev.json"):  # fmt: skip
        shutil.copy(results / name, tmp_path / name)
    monkeypatch.setattr(analysis, "RESULTS", tmp_path)
    monkeypatch.setattr(sys, "argv", ["analyse_test.py", "--split", "dev"])

    assert analysis.main() == 0

    report = json.loads((tmp_path / "dev-rows-analysis.json").read_text("utf-8"))
    rows = list(csv.DictReader((tmp_path / "dev-per-question.csv").open(encoding="utf-8")))
    assert report["rows_run"] == ["B", "G", "G_raw"] and report["rows_not_run"] == ["L", "S"]
    assert len(rows) == 40 and {"id", "B", "G", "G_raw", "checker_route"} <= set(rows[0])
    assert report["comparisons"]["G against B"]["shared_questions"] == 40
    assert report["retrieval_matches_system"] == {"questions_compared": 32, "different": []}
