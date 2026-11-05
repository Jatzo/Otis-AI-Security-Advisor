"""Text that tries to become markup, script or a link, put through the real page code in a real
browser. A payload can arrive in a record (and so in the model's reply) or in the question (and
so in the reply's echo of it), and both come out of view() the same way, so each payload is put
in every field of a reply and sent through view() first. No test here calls the API.

Needs a Chromium browser: Edge or Chrome on this machine, Chrome on CI. With none found it skips
on a developer machine and fails on CI, so a missing browser there cannot pass quietly.
"""

import json
import os
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest
from generation_world import reply

from advisor.web.headers import CONTENT_SECURITY_POLICY, SECURITY_HEADERS
from advisor.web.view import GITHUB, NVD, view

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "src" / "advisor" / "web" / "page"
HARNESS = Path(__file__).parent / "render_harness.html"
WINDOWS_EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

PAYLOADS = [
    "<script>window.__pwned=1</script>",
    '<img src=x onerror="window.__pwned=1">',
    '<svg onload="window.__pwned=1"></svg>',
    '<iframe srcdoc="<script>parent.__pwned=1</script>"></iframe>',
    '<a href="javascript:window.__pwned=1">click</a>',
    "javascript:window.__pwned=1",
    "data:text/html,<script>window.__pwned=1</script>",
    "[click here](https://evil.example/)",
    "![x](https://evil.example/x.png)",
    '<a href="https://evil.example/">GHSA-aaaa-aaaa-aaaa</a>',
    "https://evil.example/",
    "&lt;script&gt;window.__pwned=1&lt;/script&gt;",
    "&#60;img src=x onerror=window.__pwned=1&#62;",
    '</section><img src=x onerror="window.__pwned=1">',
    '"><img src=x onerror="window.__pwned=1">',
    "' onmouseover='window.__pwned=1' x='",
    "<style>body{display:none}</style>",
    '<div style="position:fixed;inset:0">overlay</div>',
    '<meta http-equiv="refresh" content="0;url=https://evil.example/">',
    '<base href="https://evil.example/">',
    '<form action="https://evil.example/"><input name=q></form>',
    '<details open ontoggle="window.__pwned=1">x</details>',
    "{{7*7}} ${7*7} <%= 7*7 %>",
    "\u202eevil\u202c \u200b\u200bhidden\u200b",
    "A" * 20000,
    "<" * 5000,
    "<!--",
    "\x00<script>window.__pwned=1</script>",
    "<math><mtext></p><img src=x onerror=window.__pwned=1>",
    '<object data="https://evil.example/"></object>',
]

ALLOWED_TAGS = {"section", "h2", "p", "ul", "li", "a", "span"}
ALLOWED_ATTRIBUTES = {"class", "href", "rel", "target", "id"}


def find_browser() -> str | None:
    for name in ("msedge", "chrome", "google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return WINDOWS_EDGE if Path(WINDOWS_EDGE).exists() else None


BROWSER = find_browser()


def need_browser() -> str:
    if BROWSER:
        return BROWSER
    if os.environ.get("CI"):
        pytest.fail("No Chromium browser on CI, so the render tests could not run.")
    pytest.skip("No Chromium browser found on this machine.")


def dump(page: Path, fragment: str, profile: Path) -> str:
    browser = need_browser()
    url = page.resolve().as_uri() + ("#" + fragment if fragment else "")
    command = [
        browser, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
        f"--user-data-dir={profile}", "--virtual-time-budget=4000", "--dump-dom", url,
    ]  # fmt: skip
    done = subprocess.run(  # noqa: S603 - a fixed browser path and a file URL we built
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        check=False,
    )
    return done.stdout


def run_harness(views: list[dict], folder: Path) -> "Collect":
    """Writes the views next to a copy of the harness that points at the page's real script, loads
    it in the browser and reads back what the page made."""
    folder.mkdir(exist_ok=True)
    (folder / "views.js").write_text(
        "window.__views = " + json.dumps(views) + ";", encoding="utf-8"
    )
    page = folder / "harness.html"
    page.write_text(
        HARNESS.read_text(encoding="utf-8").replace("APP_JS", (PAGE / "app.js").as_uri()),
        encoding="utf-8",
    )
    found = Collect()
    found.feed(dump(page, "", folder / "profile"))
    return found


class Collect(HTMLParser):
    """Every element and attribute inside each view box, and the page's own flags."""

    def __init__(self) -> None:
        super().__init__()
        self.html_flags: dict[str, str | None] = {}
        self.boxes: dict[str, list[tuple[str, dict]]] = {}
        self.current: str | None = None
        self.texts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "html":
            self.html_flags = attributes
        if tag == "section" and attributes.get("id", "").startswith("v"):
            self.current = attributes["id"]
            self.boxes[self.current] = []
        elif self.current is not None:
            self.boxes[self.current].append((tag, attributes))

    def handle_data(self, data):
        if self.current is not None:
            self.texts.append(data)


def views_for(payload: str) -> list[dict]:
    """The payload in every field a reply has, once in the known fields and once as an extra one."""
    body = json.loads(reply(abstain=False, explanation=payload, value=payload, verdict="yes"))
    body["ids"] = [payload, "GHSA-aaaa-aaaa-aaaa"]
    body["disagreement"] = {"flagged": True, "values": {"github": payload, "nvd": payload}}
    extra = {**body, "link": payload, "html": payload}
    return [
        view(json.dumps(body)),
        view(json.dumps(extra)),
        view("before " + json.dumps(body) + payload),
    ]


def test_no_payload_runs_script_or_becomes_an_element_or_a_link(tmp_path):
    views = [v for payload in PAYLOADS for v in views_for(payload)]
    found = run_harness(views, tmp_path)
    assert found.html_flags.get("data-done") == "1", "the harness did not finish"
    assert found.html_flags.get("data-pwned") == "0", "a payload ran script"
    assert len(found.boxes) == len(views)
    for box, elements in found.boxes.items():
        for tag, attributes in elements:
            assert tag in ALLOWED_TAGS, f"{box}: an element the page did not make: {tag}"
            assert set(attributes) <= ALLOWED_ATTRIBUTES, f"{box}: {tag} has {set(attributes)}"
            if tag == "a":
                assert attributes["href"].startswith((GITHUB, NVD)), f"{box}: {attributes['href']}"
                assert attributes["rel"] == "noopener noreferrer"


def test_the_payload_text_is_shown_as_text_not_run(tmp_path):
    sample = '<img src=x onerror="window.__pwned=1">'
    found = run_harness([view(reply(explanation=sample))], tmp_path)
    shown = " ".join(found.texts)
    assert sample in shown


# --- the policy in the real page -------------------------------------------------------------


def test_the_real_pages_policy_blocks_inline_script(tmp_path):
    """Copy the page and its files, add an inline script and an event handler, and load it. With
    the policy in the page's own meta tag, neither may run, and the page's own script still does."""
    for name in ("index.html", "app.js", "style.css"):
        shutil.copy(PAGE / name, tmp_path / name)
    page = tmp_path / "index.html"
    text = page.read_text(encoding="utf-8")
    text = text.replace(
        "</body>",
        '<script>document.documentElement.setAttribute("data-inline", "ran")</script>'
        "<img src=\"x\" onerror=\"document.documentElement.setAttribute('data-handler', 'ran')\">"
        "<script>window.setTimeout(function(){"
        'document.documentElement.setAttribute("data-page-script", String(!!window.OtisPage))},300)'
        "</script></body>",
    )
    page.write_text(text, encoding="utf-8")
    found = Collect()
    found.feed(dump(page, "", tmp_path / "profile"))
    assert "data-inline" not in found.html_flags
    assert "data-handler" not in found.html_flags
    assert "data-page-script" not in found.html_flags  # the inline timer was blocked as well


def test_the_pages_own_script_still_loads_under_its_policy(tmp_path):
    for name in ("index.html", "app.js", "style.css"):
        shutil.copy(PAGE / name, tmp_path / name)
    page = tmp_path / "index.html"
    marker = tmp_path / "probe.js"
    marker.write_text(
        "window.setTimeout(function(){document.documentElement.setAttribute("
        '"data-page-script", String(!!window.OtisPage))}, 300)',
        encoding="utf-8",
    )
    page.write_text(
        page.read_text(encoding="utf-8").replace(
            "</body>", '<script src="probe.js"></script></body>'
        ),
        encoding="utf-8",
    )
    found = Collect()
    found.feed(dump(page, "", tmp_path / "profile"))
    assert found.html_flags.get("data-page-script") == "true"


def test_the_pages_policy_is_inside_the_servers_policy():
    meta = PAGE.joinpath("index.html").read_text(encoding="utf-8")
    start = meta.index('http-equiv="Content-Security-Policy" content="') + len(
        'http-equiv="Content-Security-Policy" content="'
    )
    page_policy = meta[start : meta.index('"', start)]
    server_directives = set(CONTENT_SECURITY_POLICY.split("; "))
    assert set(page_policy.split("; ")) <= server_directives


def test_the_server_policy_and_headers_close_the_usual_holes():
    policy = SECURITY_HEADERS["Content-Security-Policy"]
    assert "unsafe-inline" not in policy and "unsafe-eval" not in policy
    for directive in ("default-src 'none'", "frame-ancestors 'none'", "base-uri 'none'"):
        assert directive in policy
    assert SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"


def test_the_page_script_never_sets_html():
    source = PAGE.joinpath("app.js").read_text(encoding="utf-8")
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(",
                   "new Function", "srcdoc"):  # fmt: skip
        assert banned not in source, banned
