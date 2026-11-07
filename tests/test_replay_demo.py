"""The replay demo: the data file, the page that shows it, and the script that builds it.

None of it calls a model. The data file is a committed file, so its shape, its split and its size
are checked here on every machine. Rebuilding it needs the local store, so that test skips where
the store is not present. The page is put through a real browser with hostile text in every field,
as the answer page is in test_render.py.
"""

import builtins
import importlib.util
import io
import json
import pathlib
import re
import subprocess
import sys
from pathlib import Path

import pytest
from generation_world import DB, FACTS, A, reply, shown
from test_render import PAYLOADS, Collect, dump, need_browser

from advisor.generation.checker import check
from advisor.web.headers import CONTENT_SECURITY_POLICY
from advisor.web.view import GITHUB, NVD, link_for, view

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "docs" / "demo"
DATA = DEMO / "data.json"
HARNESS = Path(__file__).parent / "replay_harness.html"
RESULTS = ROOT / "eval" / "results"
MAX_BYTES = 2 * 1024 * 1024

_loaded = importlib.util.spec_from_file_location(
    "build_replay", ROOT / "scripts" / "build_replay.py"
)
build_replay = importlib.util.module_from_spec(_loaded)
sys.modules["build_replay"] = build_replay
_loaded.loader.exec_module(build_replay)

ALLOWED_TAGS = {
    "section",
    "div",
    "h2",
    "h3",
    "h4",
    "h5",
    "p",
    "ul",
    "li",
    "a",
    "span",
    "strong",
    "button",
}
ALLOWED_ATTRIBUTES = {"class", "href", "rel", "target", "id", "type"}
STATUSES = {"passed", "failed", "unverifiable"}
OUTCOMES = {"correct", "wrong"}
VIEW_KEYS = {"state", "verdict", "ids", "value", "sources_differ", "scores", "explanation", "links"}
CHECKED_KEYS = {"declined", "outcome", "verdict", "route", "rule", "reasons", "claims", "view"}


def read_lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


@pytest.fixture(scope="module")
def data() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


# --- the data file ---------------------------------------------------------------------------


def check_view(found: dict) -> None:
    assert {"state", "explanation", "ids", "links"} <= set(found) <= VIEW_KEYS
    assert found["state"] in {"answer", "declined", "unreadable"}
    assert isinstance(found["explanation"], str) and isinstance(found["ids"], list)


def check_checked(found: dict) -> None:
    assert set(found) == CHECKED_KEYS
    assert found["outcome"] in OUTCOMES and isinstance(found["declined"], bool)
    assert found["verdict"] in {"passed", "repaired", "abstained", "refused"}
    assert isinstance(found["reasons"], list) and all(isinstance(r, str) for r in found["reasons"])
    for claim in found["claims"]:
        assert set(claim) == {"index", "claim", "status", "rule", "reason"}
        assert claim["status"] in STATUSES and isinstance(claim["claim"], str)
    check_view(found["view"])


def test_the_data_file_has_the_fixed_shape(data):
    assert set(data) == {"meta", "records", "questions"}
    assert set(data["meta"]) == {
        "run", "run_date", "model", "run_commit", "systems", "questions", "totals", "cost_usd",
    }  # fmt: skip
    assert data["meta"]["questions"] == len(data["questions"]) == 40
    assert set(data["meta"]["systems"]) == {"phase5-system-v1", "phase6-system-v1"}
    for question in data["questions"]:
        assert set(question) == {
            "id", "type", "question", "gold", "raw", "phase5", "phase6", "shown", "cost_usd",
            "latency_s",
        }  # fmt: skip
        assert set(question["gold"]) == {"text", "derivation"}
        assert set(question["raw"]) == {"declined", "outcome", "view"}
        assert question["raw"]["outcome"] in OUTCOMES
        check_view(question["raw"]["view"])
        check_checked(question["phase5"])
        check_checked(question["phase6"])
        assert isinstance(question["cost_usd"], float) and isinstance(question["latency_s"], float)
        assert len(question["shown"]) == 10 and set(question["shown"]) <= set(data["records"])


def test_every_record_link_is_one_the_answer_view_would_build(data):
    for unit_id, record in data["records"].items():
        assert set(record) == {"id", "source", "header", "excerpt", "url"}
        assert record["source"] in {"ghsa", "nvd", "kev"} and unit_id.startswith(record["source"])
        assert record["url"] == link_for(record["id"])["url"]
        assert record["url"].startswith((GITHUB, NVD))


def test_the_demo_shows_the_dev_split_only(data):
    questions = read_lines(ROOT / "eval" / "questions.jsonl")
    dev = {q["id"] for q in questions if q["split"] == "dev"}
    elsewhere = [q for q in questions if q["split"] != "dev"]
    elsewhere += read_lines(ROOT / "eval-v2" / "questions.jsonl")
    text = DATA.read_text(encoding="utf-8")
    assert {q["id"] for q in data["questions"]} == dev
    for question in elsewhere:
        assert question["question"] not in text, question["id"]
    tokens = set(re.findall(r'"([a-z]{2}-\d{3})"', text))
    assert tokens <= dev, sorted(tokens - dev)


def test_the_data_file_holds_no_email_address():
    text = DATA.read_text(encoding="utf-8")
    assert build_replay.EMAIL.findall(text) == []


def test_cut_removes_an_email_address_and_leaves_a_package_pin_alone():
    cut = build_replay.cut
    assert cut("Credits: Researcher: A. Person (a.person@example.com) found it", 200) == (
        "Credits: Researcher: A. Person ([email removed]) found it"
    )
    pins = "Upgrade to lodash@4.17.21, @types/node@20.1.0 or spring-webmvc@5.2.20.RELEASE"
    assert cut(pins, 200) == pins


def test_the_data_file_and_the_page_together_stay_under_two_megabytes():
    assert DATA.stat().st_size < MAX_BYTES
    assert sum(p.stat().st_size for p in DEMO.rglob("*") if p.is_file()) < MAX_BYTES


def test_the_totals_and_the_checked_replies_match_the_saved_results(data):
    for name, scored in (("raw", "raw"), ("phase5", "checked"), ("phase6", "checked-phase6")):
        rows = [r for r in read_lines(RESULTS / f"generation-dev-{scored}.scored.jsonl")
                if r["run"] == 1]  # fmt: skip
        found = data["meta"]["totals"][name]
        assert found == {"correct": sum(r["outcome"] == "correct" for r in rows), "of": len(rows)}
    by_id = {q["id"]: q for q in data["questions"]}
    for name, key in (("checked", "phase5"), ("checked-phase6", "phase6")):
        for line in read_lines(RESULTS / f"generation-dev-{name}.jsonl"):
            if line["run"] == 1:
                assert by_id[line["id"]][key]["view"] == view(line["text"])
                assert by_id[line["id"]][key]["verdict"] == line["checker"]["verdict"]
    for line in read_lines(RESULTS / "generation-dev-raw.jsonl"):
        if line["run"] == 1:
            assert by_id[line["id"]]["raw"]["view"] == view(line["text"])
            assert by_id[line["id"]]["cost_usd"] == line["cost_usd"]


# --- the page --------------------------------------------------------------------------------


def test_the_page_script_never_sets_html_or_reaches_for_the_network_except_its_own_data():
    source = DEMO.joinpath("app.js").read_text(encoding="utf-8")
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(",
                   "new Function", "srcdoc", ".style", "setAttribute", "XMLHttpRequest",
                   "WebSocket", "localStorage", "sendBeacon"):  # fmt: skip
        assert banned not in source, banned
    assert source.count("fetch(") == 1 and 'fetch("data.json")' in source


def test_the_page_has_no_inline_script_or_handler_and_loads_only_its_own_files():
    page = DEMO.joinpath("index.html").read_text(encoding="utf-8")
    assert re.findall(r"<script(?![^>]*\bsrc=)", page) == []
    assert not re.search(r"\son[a-z]+\s*=", page) and "style=" not in page
    assert re.findall(r'<(?:script|link|img)[^>]*(?:src|href)="(https?:)?//', page) == []
    start = page.index('http-equiv="Content-Security-Policy" content="') + len(
        'http-equiv="Content-Security-Policy" content="'
    )
    policy = page[start : page.index('"', start)]
    assert set(policy.split("; ")) <= set(CONTENT_SECURITY_POLICY.split("; "))
    assert "unsafe-inline" not in policy and "unsafe-eval" not in policy


def harness(cases: list[dict], real: dict, folder: Path) -> Collect:
    folder.mkdir(exist_ok=True)
    (folder / "cases.js").write_text(
        "window.__real = " + json.dumps(real) + "; window.__cases = " + json.dumps(cases) + ";",
        encoding="utf-8",
    )
    page = folder / "harness.html"
    page.write_text(
        HARNESS.read_text(encoding="utf-8").replace("APP_JS", DEMO.joinpath("app.js").as_uri()),
        encoding="utf-8",
    )
    found = Collect()
    found.feed(dump(page, "", folder / "profile"))
    return found


def hostile(value, payload: str, keep: tuple = ()):
    """Every text value replaced by the payload, with the object's keys and shape kept. A key in
    `keep` holds a value that is left alone."""
    if isinstance(value, dict):
        return {k: v if k in keep else hostile(v, payload, keep) for k, v in value.items()}
    if isinstance(value, list):
        return [hostile(v, payload, keep) for v in value]
    return payload if isinstance(value, str) else value


def assert_made_by_the_page(found: Collect, expected: int) -> None:
    assert found.html_flags.get("data-done") == "1", "the harness did not finish"
    assert found.html_flags.get("data-pwned") == "0", "a payload ran script"
    assert len(found.boxes) == expected
    for box, elements in found.boxes.items():
        for tag, attributes in elements:
            assert tag in ALLOWED_TAGS, f"{box}: an element the page did not make: {tag}"
            assert set(attributes) <= ALLOWED_ATTRIBUTES, f"{box}: {tag} has {set(attributes)}"
            if tag == "a":
                assert attributes["href"].startswith((GITHUB, NVD)), f"{box}: {attributes['href']}"
                assert attributes["rel"] == "noopener noreferrer"
            if tag == "button":
                assert attributes == {"class": "pick", "type": "button"}


def test_every_real_question_and_the_list_render_with_nothing_the_page_did_not_make(data, tmp_path):
    need_browser()
    cases = [{"real": True, "index": i} for i in range(len(data["questions"]))]
    cases += [{"real": True, "what": w} for w in ("list", "summary", "systems")]
    found = harness(cases, data, tmp_path)
    assert_made_by_the_page(found, len(cases))
    assert "GHSA-p6xc-xr62-6r2g" in " ".join(found.texts)


def test_hostile_text_in_any_field_of_the_data_cannot_become_markup_script_or_a_link(
    data, tmp_path
):
    need_browser()
    rich = next(q for q in data["questions"] if q["id"] == "dg-003")
    cases = []
    for payload in PAYLOADS:
        for keep in ((), ("shown",)):  # the list of shown records is kept so they are drawn
            cases.append({
                "data": {"meta": hostile(data["meta"], payload), "questions": [],
                         "records": hostile(data["records"], payload)},
                "question": hostile(rich, payload, keep),
            })  # fmt: skip
        cases.append({"what": "list", "data": {"questions": [hostile(rich, payload)]}})
        cases.append({"what": "summary", "data": {"meta": hostile(data["meta"], payload)}})
        cases.append({"what": "systems", "data": {"meta": hostile(data["meta"], payload)}})
    found = harness(cases, data, tmp_path)
    assert_made_by_the_page(found, len(cases))


def test_hostile_text_is_shown_as_text_not_run(data, tmp_path):
    need_browser()
    sample = '<img src=x onerror="window.__pwned=1">'
    rich = next(q for q in data["questions"] if q["id"] == "dg-003")
    cases = [{"data": data, "question": hostile(rich, sample, ("shown",))}]
    found = harness(cases, data, tmp_path)
    assert sample in " ".join(found.texts)


# --- the build script ------------------------------------------------------------------------


def small_files() -> dict:
    question = f"Is django 3.0.4 affected by {A}?"
    reply_text = reply(
        verdict="yes", ids=[A],
        claims=[{"kind": "affects", "record": A, "package": "django", "version": "3.0.4",
                 "affected": True}],
    )  # fmt: skip
    done = check(question, reply_text, "end_turn", shown(f"ghsa:{A}"), FACTS)
    raw = {"id": "vr-001", "run": 1, "text": reply_text, "shown": [f"ghsa:{A}"],
           "stop_reason": "end_turn", "cost_usd": 0.03, "latency_s": 2.5,
           "model": "claude-sonnet-5-5", "commit": "abc1234"}  # fmt: skip
    checked = {**raw, "text": done.text, "checker": done.record()}
    scored = [{"id": "vr-001", "run": 1, "outcome": "correct", "abstained": False}]
    return {
        "questions": [
            {
                "id": "vr-001",
                "split": "dev",
                "type": "version",
                "question": question,
                "answers_with": "verdict",
            },
            {
                "id": "vr-901",
                "split": "test",
                "type": "version",
                "question": "Held back?",
                "answers_with": "verdict",
            },
        ],  # fmt: skip
        "gold": [{"id": "vr-001", "gold": {"verdict": "yes"}, "derivation": "In the range."}],
        "raw": [raw],
        "checked_old": [checked],
        "checked_new": [checked],
        "scored_raw": scored,
        "scored_old": scored,
        "scored_new": scored,
    }


def test_the_build_makes_the_page_data_from_saved_lines_and_leaves_the_test_split_out():
    files = small_files()
    built = build_replay.build(
        DB, files, {"phase5-system-v1": "a" * 40, "phase6-system-v1": "b" * 40}
    )

    assert [q["id"] for q in built["questions"]] == ["vr-001"]
    question = built["questions"][0]
    assert question["gold"]["text"] == "Verdict: yes."
    assert question["phase5"]["verdict"] == "passed" and question["phase5"]["outcome"] == "correct"
    assert question["phase5"]["view"] == view(files["checked_old"][0]["text"])
    assert question["phase5"]["claims"][0]["status"] == "passed"
    assert question["phase5"]["claims"][0]["claim"].startswith("affects record=")
    assert built["records"][f"ghsa:{A}"]["url"] == GITHUB + A
    assert built["meta"]["totals"]["raw"] == {"correct": 1, "of": 1}
    assert "Held back?" not in json.dumps(built)


# --- no model, no key, no .env ---------------------------------------------------------------


def test_the_build_script_has_no_way_to_reach_a_model_a_key_or_an_env_file():
    source = ROOT.joinpath("scripts", "build_replay.py").read_text(encoding="utf-8")
    for banned in (".env", "dotenv", "environ", "getenv", "anthropic", "answer.ask", "API_KEY"):
        assert banned not in source, banned
    program = ";".join(
        [
            "import sys",
            f"sys.path[:0] = [{str(ROOT / 'src')!r}, {str(ROOT / 'scripts')!r}]",
            "import build_replay",
            "names = ('anthropic', 'dotenv', 'advisor.generation.answer')",
            "print(','.join(m for m in names if m in sys.modules))",
        ]
    )
    done = subprocess.run(  # noqa: S603 - our own interpreter and a program written above
        [sys.executable, "-I", "-c", program], capture_output=True, text=True, check=True, cwd=ROOT
    )
    assert done.stdout.strip() == ""


def test_rebuilding_from_the_local_store_reproduces_the_committed_file_and_opens_no_env_file(
    tmp_path, monkeypatch
):
    store = ROOT / "data" / "advisor.db"
    if not store.exists():
        pytest.skip("The local store is not here, so the data file cannot be rebuilt.")
    opened: list[str] = []
    originals = {
        "open": builtins.open, "io": io.open, "read_text": pathlib.Path.read_text,
        "read_bytes": pathlib.Path.read_bytes, "path_open": pathlib.Path.open,
    }  # fmt: skip

    def note(path) -> None:
        opened.append(str(path))

    monkeypatch.setattr(
        builtins, "open", lambda f, *a, **k: (note(f), originals["open"](f, *a, **k))[1]
    )
    monkeypatch.setattr(io, "open", lambda f, *a, **k: (note(f), originals["io"](f, *a, **k))[1])
    monkeypatch.setattr(
        pathlib.Path,
        "read_text",
        lambda self, *a, **k: (note(self), originals["read_text"](self, *a, **k))[1],
    )
    monkeypatch.setattr(
        pathlib.Path, "read_bytes", lambda self: (note(self), originals["read_bytes"](self))[1]
    )
    monkeypatch.setattr(
        pathlib.Path,
        "open",
        lambda self, *a, **k: (note(self), originals["path_open"](self, *a, **k))[1],
    )
    out = tmp_path / "data.json"
    monkeypatch.setattr(sys, "argv", ["build_replay.py", "--out", str(out)])

    assert build_replay.main() == 0

    assert out.read_text(encoding="utf-8") == DATA.read_text(encoding="utf-8")
    assert not [p for p in opened if ".env" in Path(p).name], opened
    assert not [p for p in opened if "test-generation" in p or "eval-v2" in p], opened
