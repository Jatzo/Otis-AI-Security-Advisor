"""Draws the figures in the README and the docs as SVG, from the numbers in the result files.

Every number below is copied from a written result, and the source is named next to it. Nothing is
measured here and no model is called. Run it to rebuild docs/img/*.svg:

    python scripts/make_figures.py
"""

import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "img"

INK, MUTED, FAINT = "#2A1C16", "#6B5B52", "#94867D"
BLUE, BLUE_D, BLUE_L = "#8EC1EE", "#4F93C9", "#D6E8F7"
PINK, PINK_D, PINK_L = "#E89AA7", "#C45F72", "#F7DDE1"
PAPER, CARD, LINE = "#FBF8F5", "#FFFFFF", "#DDD5CD"
GREY, GREY_L = "#B9AFA7", "#E9E3DD"
FONT = "Segoe UI, Helvetica Neue, Helvetica, Arial, sans-serif"


def text(x, y, s, size=13, weight=400, fill=INK, anchor="start", italic=False):
    style = ' font-style="italic"' if italic else ""
    return (
        f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" text-anchor="{anchor}"{style}>{escape(str(s))}</text>'
    )


def lines(x, y, rows, size=12.5, gap=18, fill=MUTED, anchor="start", weight=400):
    return "".join(
        text(x, y + i * gap, row, size, weight, fill, anchor) for i, row in enumerate(rows)
    )


def rect(x, y, w, h, fill=CARD, stroke=LINE, rx=10, sw=1.2):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def line(x1, y1, x2, y2, stroke=LINE, sw=1.2, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{sw}"{d}/>'
    )


def arrow(x1, y1, x2, y2, stroke=MUTED):
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="1.6" '
        'marker-end="url(#head)"/>'
    )


def frame(w, h, title, subtitle, body, label):
    defs = (
        '<defs><marker id="head" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{MUTED}"/>'
        "</marker></defs>"
    )
    head = text(32, 40, title, 17, 700) + text(32, 62, subtitle, 12.5, 400, MUTED)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'role="img" aria-label="{escape(label)}">{defs}'
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="16" fill="{PAPER}" stroke="{LINE}"/>'
        f"{head}{body}</svg>\n"
    )


def save(name, svg):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(svg, encoding="utf-8")
    print(f"docs/img/{name}")


# --- Figure 1: how an answer is made ---------------------------------------------------------


def architecture():
    steps = [
        (
            30,
            120,
            "Question",
            FAINT,
            [
                "Free text, for",
                "example: 'Does",
                "CVE-2020-9402",
                "affect django",
                "version 3.0.4?'",
            ],
        ),
        (
            174,
            170,
            "1  Gate",
            BLUE_D,
            [
                "If the question names",
                "a GHSA or CVE ID that",
                "no record holds, refuse.",
                "The model is not called.",
            ],
        ),
        (
            368,
            190,
            "2  Retrieve",
            BLUE_D,
            [
                "Keyword search (BM25)",
                "over 1,164 records, each",
                "with a short header:",
                "package, dates, score,",
                "ranges, aliases.",
                "The top 10 are shown.",
            ],
        ),
        (
            582,
            190,
            "3  Answer",
            BLUE_D,
            [
                "Claude Sonnet 5.5, one",
                "pass, no tools. It",
                "writes JSON: verdict,",
                "IDs, value, explanation,",
                "and the claims the",
                "answer rests on.",
            ],
        ),
        (
            796,
            200,
            "4  Check",
            PINK_D,
            [
                "Code reads each claim",
                "against the store, not",
                "against the model's text.",
                "One claim that is wrong",
                "or cannot be checked",
                "refuses the whole reply.",
            ],
        ),
    ]
    body = []
    for x, w, name, colour, rows in steps:
        body.append(rect(x, 92, w, 170, CARD))
        body.append(f'<rect x="{x}" y="92" width="{w}" height="30" rx="10" fill="{colour}"/>')
        body.append(f'<rect x="{x}" y="108" width="{w}" height="14" fill="{colour}"/>')
        body.append(text(x + 14, 112, name, 13.5, 700, "#FFFFFF"))
        body.append(lines(x + 14, 148, rows))
    for a, b in [(150, 174), (344, 368), (558, 582), (772, 796)]:
        body.append(arrow(a + 2, 177, b - 2, 177))
    body.append(arrow(996, 150, 1022, 138))
    body.append(arrow(996, 205, 1022, 214))
    body.append(rect(1024, 92, 130, 74, BLUE_L, BLUE_D))
    body.append(text(1089, 118, "Answer", 13.5, 700, INK, "middle"))
    body.append(lines(1089, 138, ["with its claims", "and links"], 12, 16, MUTED, "middle"))
    body.append(rect(1024, 182, 130, 80, PINK_L, PINK_D))
    body.append(text(1089, 208, "Refusal", 13.5, 700, INK, "middle"))
    body.append(lines(1089, 228, ["with the reasons", "from the checker"], 12, 16, MUTED, "middle"))
    # the store
    body.append(rect(368, 312, 786, 70, "#FFFFFF", GREY, 12))
    body.append(text(388, 338, "Store: SQLite, snapshot of 1 November 2026", 13.5, 700))
    body.append(
        text(
            388,
            362,
            "588 GitHub advisories   576 NVD records   CISA KEV (1,766 entries)   18 packages: 9 PyPI, 6 npm, 3 Maven",
            12.5,
            400,
            MUTED,
        )
    )
    body.append(arrow(463, 312, 463, 264))
    body.append(arrow(896, 312, 896, 264))
    body.append(text(475, 292, "records", 11.5, 400, FAINT))
    body.append(text(908, 292, "facts, read afresh", 11.5, 400, FAINT))
    # principles
    for x, row in [
        (32, ["Retrieval and the model answer.", "Code only checks and grades.", "ADR 0001"]),
        (32 + 0, []),
    ]:
        if row:
            body.append(rect(x, 312, 312, 70, "#FFFFFF", GREY_L, 12))
            body.append(lines(x + 16, 337, row[:2], 12.5, 18, INK, "start", 600))
            body.append(text(x + 16, 372, row[2], 11.5, 400, FAINT))
    body.append(rect(32, 398, 1122, 54, "#FFFFFF", GREY_L, 12))
    body.append(text(48, 420, "Fail closed.", 12.5, 700, PINK_D))
    body.append(
        text(
            124,
            420,
            "A claim that is wrong, or that code cannot check, refuses the reply. The checker never repairs a fact, because patching one would be code answering the question (ADR 0006).",
            12,
            400,
            MUTED,
        )
    )
    body.append(
        text(
            48,
            440,
            "Eight rules in all, from reading the reply the way the scorer does to requiring a passing claim behind every answer field.",
            12,
            400,
            MUTED,
        )
    )
    return frame(
        1186,
        472,
        "Figure 1. How an answer is made",
        "One pass: retrieve, answer, check. Otis does not choose its own tools or loop.",
        "".join(body),
        "Pipeline: gate, retrieve, answer, check, then an answer or a refusal, with the store feeding retrieval and the checker",
    )


# --- Figure 2: the evaluation trail ----------------------------------------------------------


def evaluation_trail():
    body = []
    # composition bar: 150 questions (docs: eval set 150, 30 lookups, 35 version, 25 multi-hop, 30 abstain, 30 disagree)
    parts = [
        ("Direct lookup", 30, BLUE),
        ("Version affected", 35, "#5C9FD1"),
        ("Multi-hop", 25, BLUE_L),
        ("Should decline", 30, PINK),
        ("Sources disagree", 30, PINK_L),
    ]
    x, scale = 32, 1122 / 150
    body.append(
        text(
            32,
            100,
            "The question set: 150 questions, each with a gold answer worked out by separate code from the raw data",
            13,
            600,
        )
    )
    for name, n, colour in parts:
        w = n * scale
        body.append(rect(x, 112, w - 3, 38, colour, "none", 6, 0))
        body.append(text(x + 10, 135, f"{name}  {n}", 12.5, 600, INK))
        x += w
    body.append(text(32, 176, "Split for tuning and scoring", 12.5, 600))
    body.append(rect(32, 184, 40 * scale - 3, 30, GREY_L, "none", 6, 0))
    body.append(text(44, 204, "Dev  40", 12.5, 600))
    body.append(rect(32 + 40 * scale, 184, 110 * scale - 3, 30, BLUE_L, "none", 6, 0))
    body.append(text(32 + 40 * scale + 12, 204, "Test  110, scored once", 12.5, 600))
    # trail
    steps = [
        (
            "1",
            "Questions and gold written first",
            "Gold comes from raw data by code that the system never uses.",
        ),
        (
            "2",
            "Tag eval-freeze-v1",
            "Questions, gold, scorer and runner frozen, with a CI check that fails if they change.",
        ),
        (
            "3",
            "Baseline on dev",
            "The model with no documents. 3 runs. The number every other row is held against.",
        ),
        (
            "4",
            "Retrieval ladder on dev",
            "Nine rungs, an adoption rule written first, and one rung adopted.",
        ),
        (
            "5",
            "Generation and checker on dev",
            "Plan fixed before code. One prompt change tried, one kept out.",
        ),
        (
            "6",
            "Tag the system, test once",
            "Tag phase5-system-v1. Five rows on 110 questions. Raw outputs committed before scoring.",
        ),
        ("7", "Red team", "56 cases and a held-out 56. Tagged before the first call."),
    ]
    y0 = 256
    for i, (n, head, sub) in enumerate(steps):
        col, row = i % 4, i // 4
        x = 32 + col * 284
        y = y0 + row * 118
        body.append(rect(x, y, 266, 104, CARD))
        body.append(f'<circle cx="{x + 26}" cy="{y + 28}" r="14" fill="{BLUE}"/>')
        body.append(text(x + 26, y + 33, n, 13, 700, INK, "middle"))
        body.append(text(x + 50, y + 33, head, 13, 700))
        body.append(lines(x + 16, y + 60, wrap(sub, 38), 12, 16))
    body.append(rect(32 + 3 * 284, y0 + 118, 266, 104, PINK_L, PINK_D))
    body.append(text(32 + 3 * 284 + 16, y0 + 118 + 30, "The test split is spent.", 13, 700, INK))
    body.append(
        lines(
            32 + 3 * 284 + 16,
            y0 + 118 + 54,
            [
                "Any later claim of improvement",
                "needs a new question set,",
                "written before the change.",
            ],
            12,
            16,
        )
    )
    body.append(
        text(
            32,
            506,
            "Scoring is deterministic code and no model judges any answer. Every result line records the commit and the git blob id of each frozen file.",
            12,
            400,
            MUTED,
        )
    )
    return frame(
        1186,
        528,
        "Figure 2. How the evaluation was kept honest",
        "Order matters: the questions, gold and scorer were fixed before any system was built or run.",
        "".join(body),
        "Question set composition, dev and test split, and the seven steps of the evaluation trail",
    )


def wrap(s, width):
    words, rows, row = s.split(), [], ""
    for word in words:
        if len(row) + len(word) + 1 > width:
            rows.append(row)
            row = word
        else:
            row = f"{row} {word}".strip()
    rows.append(row)
    return rows


# --- Figure 3: the retrieval ladder ----------------------------------------------------------


def retrieval_ladder():
    # docs/retrieval-results.md: all-evidence@10 on the 32 answerable dev questions, with 95% intervals (percent)
    rows = [
        ("R0", "Keyword search, no header", 7, 11, 39, ""),
        ("R1", "Keyword search with a header", 24, 58, 87, "adopted"),
        ("R2", "Dense search, Qwen3-Embedding-0.6B", 12, 23, 55, "740 ms"),
        ("R3", "Dense search, bge-small", 13, 26, 58, "22 ms"),
        ("R4", "R1 + R3, reciprocal rank fusion", 20, 45, 77, ""),
        ("R5", "R4, then top 30 reranked", 24, 58, 87, "11.4 s a query"),
        ("R6", "R5 with exact IDs placed first", 25, 61, 89, "28 ms, scores reused"),
        ("R7", "R1 with long records split", 24, 58, 87, ""),
        ("R8", "R1 with model-written sub-queries", 20, 45, 77, "1.7 s"),
    ]
    body = [
        text(
            32,
            96,
            "Share of the 32 answerable dev questions whose evidence is wholly in the top 10 (bar), with the 95% interval (whisker)",
            12.5,
            400,
            MUTED,
        )
    ]
    x0, x1, y0, step = 400, 960, 124, 38
    for pct in range(0, 101, 20):
        x = x0 + (x1 - x0) * pct / 100
        body.append(line(x, y0 - 12, x, y0 + step * len(rows) - 8, GREY_L))
        body.append(text(x, y0 + step * len(rows) + 10, f"{pct}%", 11.5, 400, FAINT, "middle"))
    for i, (key, name, n, lo, hi, note) in enumerate(rows):
        y = y0 + i * step
        chosen = key == "R1"
        body.append(text(32, y + 17, key, 13, 700, BLUE_D if chosen else INK))
        body.append(text(66, y + 17, name, 13, 600 if chosen else 400))
        w = (x1 - x0) * (n / 32)
        body.append(rect(x0, y, w, 24, BLUE if chosen else GREY, "none", 5, 0))
        body.append(
            line(x0 + (x1 - x0) * lo / 100, y + 12, x0 + (x1 - x0) * hi / 100, y + 12, INK, 1.4)
        )
        body.append(
            line(x0 + (x1 - x0) * lo / 100, y + 6, x0 + (x1 - x0) * lo / 100, y + 18, INK, 1.4)
        )
        body.append(
            line(x0 + (x1 - x0) * hi / 100, y + 6, x0 + (x1 - x0) * hi / 100, y + 18, INK, 1.4)
        )
        body.append(
            text(
                x0 + (x1 - x0) * max(hi, 100 * n / 32) / 100 + 8, y + 17, f"{n}/32", 12.5, 700, INK
            )
        )
        if note:
            body.append(
                text(1040, y + 17, note, 12, 600 if chosen else 400, BLUE_D if chosen else FAINT)
            )
    body.append(rect(32, y0 + step * len(rows) + 28, 1122, 62, CARD))
    body.append(
        text(
            48,
            y0 + step * len(rows) + 52,
            "Rule written before the first run: a rung is adopted only if it wins at least 4 more questions than R1, with exact McNemar p below 0.05.",
            12.5,
            400,
            MUTED,
        )
    )
    body.append(
        text(
            48,
            y0 + step * len(rows) + 74,
            "None did. R1's header is worth 17 questions over R0. Embeddings did worse than keyword search on this set, which is full of exact IDs and versions.",
            12.5,
            400,
            MUTED,
        )
    )
    return frame(
        1186,
        y0 + step * len(rows) + 120,
        "Figure 3. The retrieval ladder, on dev only",
        "Nine rungs, one adopted. Source: docs/retrieval-results.md. These are dev numbers on a small set.",
        "".join(body),
        "Bar chart of nine retrieval rungs by share of questions whose evidence is in the top 10, with R1 adopted",
    )


# --- Figure 4: test results ------------------------------------------------------------------


def bar_panel(x, y, title, sub, rows, width=540, label=200):
    out = [text(x, y, title, 14, 700), text(x, y + 20, sub, 12, 400, MUTED)]
    top, step = y + 44, 44
    x0 = x + label
    span = width - label - 120
    for pct in range(0, 101, 25):
        gx = x0 + span * pct / 100
        out.append(line(gx, top - 8, gx, top + step * len(rows) - 12, GREY_L))
        out.append(text(gx, top + step * len(rows) + 4, f"{pct}%", 11, 400, FAINT, "middle"))
    for i, (name, n, total, colour, ci, bold) in enumerate(rows):
        yy = top + i * step
        out.append(text(x, yy + 17, name, 12.5, 700 if bold else 400))
        w = span * n / total
        out.append(rect(x0, yy, w, 26, colour, "none", 5, 0))
        if ci:
            lo, hi = ci
            for gx in (x0 + span * lo / 100, x0 + span * hi / 100):
                out.append(line(gx, yy + 6, gx, yy + 20, INK, 1.4))
            out.append(line(x0 + span * lo / 100, yy + 13, x0 + span * hi / 100, yy + 13, INK, 1.4))
        out.append(
            text(
                x0 + max(w, 0) + 8 if not ci else x0 + span * ci[1] / 100 + 8,
                yy + 18,
                f"{n}/{total}  ({round(100 * n / total)}%)",
                12,
                700,
            )
        )
    return "".join(out)


def test_results():
    # docs/test-results.md, system tagged phase5-system-v1, 110 test questions, one run
    a = [
        ("Baseline, no documents", 35, 110, GREY, (24, 41), False),
        ("Structured lookups, no model", 99, 110, "#C5DFF3", None, False),
        ("System, raw reply", 75, 110, "#6FAEDC", (59, 76), False),
        ("System, checked reply", 66, 110, BLUE, (51, 69), True),
    ]
    b = [
        ("Baseline", 8, 43, GREY, None, False),
        ("Structured lookups", 37, 43, "#C5DFF3", None, False),
        ("System, raw", 31, 43, "#6FAEDC", None, False),
        ("System, checked", 24, 43, BLUE, None, True),
        ("Whole package in context", 42, 43, BLUE_D, None, False),
    ]
    body = [
        bar_panel(
            32,
            100,
            "All 110 test questions",
            "Correct answers, with the 95% interval where the results give one",
            a,
        )
    ]
    body.append(
        bar_panel(
            612,
            100,
            "The 43 questions that name a package",
            "One row reads the whole package into the prompt, so it can be set against the rest only here",
            b,
        )
    )
    notes = [
        "The system (checked) is right on 66 of 110, and on 44 of the 88 answerable questions (50%). The baseline is 13 of 88 (15%).",
        "Where the system and the baseline disagree, the system wins 35 questions and loses 4 (exact McNemar, p below 0.0001).",
        "Structured lookups score high because this set is templated: code reads the form of the question and queries the store. Real questions may be less regular.",
        "Fabricated advisory or CVE IDs: 0 of 110 in every row. The whole-package row costs $0.062 a question against $0.030 for the system (prompt caching on).",
    ]
    body.append(rect(32, 360, 1122, 130, CARD))
    for i, n in enumerate(notes):
        body.append(text(48, 388 + i * 28, n, 12.5, 400, INK if i < 2 else MUTED))
    return frame(
        1186,
        512,
        "Figure 4. Results on the test split, scored once",
        "110 questions, one run, from the tagged system. Source: docs/test-results.md.",
        "".join(body),
        "Bar charts of test results for five systems, on all 110 questions and on the 43 package-naming questions",
    )


# --- Figure 5: where the answerable questions went --------------------------------------------


def where_answers_go():
    # docs/test-results.md: the 88 answerable test questions, checked system; and R1 coverage
    segs = [
        (44, "Right", "44", BLUE, INK),
        (8, "Wrong, passed", "8", PINK_D, "#FFFFFF"),
        (9, "Right reply refused", "9", PINK, INK),
        (27, "Model declined, evidence missed", "27", GREY, INK),
    ]
    body = [
        text(32, 96, "The 88 answerable test questions, by what the checked system did", 13.5, 700)
    ]
    x, scale = 32, 1122 / 88
    for n, name, lab, colour, tc in segs:
        w = n * scale
        body.append(rect(x, 112, w - 3, 54, colour, "none", 8, 0))
        body.append(
            text(
                x + w / 2,
                146,
                lab if n < 10 else f"{lab}",
                22 if n >= 10 else 18,
                700,
                tc,
                "middle",
            )
        )
        body.append(text(x + 6, 188, name, 12, 600, INK))
        x += w
    expl = [
        (
            "Wrong, passed (8)",
            "Six incomplete lists of true advisories, one short intersection, one wrong choice between two true dates. Each stated fact was true. The checker cannot see that a list is short.",
        ),
        (
            "Right reply refused (9)",
            "Four were the model putting an advisory that does not apply into its list of IDs. Two were an extra claim on an NVD record the code cannot check. One was a verdict that needs a KEV claim, one an answer with no claim, and one a checker fault.",
        ),
    ]
    for i, (h, t) in enumerate(expl):
        x = 32 + i * 572
        body.append(rect(x, 214, 550, 112, CARD))
        body.append(text(x + 16, 240, h, 13, 700))
        body.append(lines(x + 16, 262, wrap(t, 82), 12, 16))
    body.append(
        text(
            32,
            366,
            "Retrieval is the limit. The top 10 held all the evidence for 53 of the 88 answerable questions.",
            13.5,
            700,
        )
    )
    a, b = 53, 35
    body.append(rect(32, 380, a * 1122 / 88 - 3, 46, BLUE_L, BLUE, 8))
    body.append(
        text(
            48,
            408,
            "Evidence retrieved: 53 questions. The model's raw reply was right on 52.",
            13,
            600,
        )
    )
    body.append(rect(32 + a * 1122 / 88, 380, b * 1122 / 88 - 3, 46, GREY_L, GREY, 8))
    body.append(text(32 + a * 1122 / 88 + 14, 408, "Evidence missed: 35. Right on 1.", 13, 600))
    body.append(
        text(
            32,
            452,
            "So accuracy is bounded by how often the right records reach the model, and the model does well when they do. The roadmap starts there.",
            12.5,
            400,
            MUTED,
        )
    )
    return frame(
        1186,
        478,
        "Figure 5. Where the accuracy was lost",
        "Source: docs/test-results.md. Counts are questions, from one run.",
        "".join(body),
        "Stacked bar of the 88 answerable test questions by outcome, and the effect of retrieving or missing the evidence",
    )


# --- Figure 6: the red team ------------------------------------------------------------------


def red_team():
    # docs/red-team-report.md: cases whose attacker obeyed on either run. Frozen set 2 runs, held-out set 1 run.
    classes = [
        ("A", "Instruction hidden in a record", 24, 0, 1),
        ("Aq", "Instruction typed into the question", 8, 4, 4),
        ("B1", "False fix version in prose", 4, 0, 0),
        ("B2", "False fix version in a new record", 4, 0, 3),
        ("D-leak", "Ask for the instructions", 8, 0, 0),
        ("D-off", "Ask for something off topic", 8, 0, 0),
    ]
    body = [
        rect(32, 82, 1122, 40, PINK_L, PINK_D),
        text(
            48,
            108,
            "No defence has been tested. Every run here is against the unchanged system, as tagged.",
            13.5,
            700,
            INK,
        ),
    ]
    y = 154
    body.append(text(430, y - 12, "Frozen set (2 runs a case)", 12, 700, MUTED))
    body.append(text(790, y - 12, "Held-out set (1 run a case)", 12, 700, MUTED))
    for key, name, n, a, b in classes:
        body.append(text(32, y + 16, key, 13, 700))
        body.append(text(86, y + 16, name, 12.5, 400, MUTED))
        for x0, k in [(430, a), (790, b)]:
            for j in range(n):
                cx = x0 + j * 11
                filled = j < k
                body.append(
                    rect(
                        cx,
                        y + 2,
                        9,
                        18,
                        PINK_D if filled else CARD,
                        PINK_D if filled else GREY,
                        3,
                        1.2,
                    )
                )
            body.append(
                text(
                    x0 + n * 11 + 8,
                    y + 17,
                    f"{k} of {n}",
                    12.5,
                    700 if k else 400,
                    PINK_D if k else FAINT,
                )
            )
        y += 36
    body.append(
        text(
            32,
            y + 28,
            "A filled square is a case where the reply did what the attack asked, and did not just mention it. Source: docs/red-team-report.md.",
            12,
            400,
            MUTED,
        )
    )
    notes = [
        "Instructions hidden in advisory text were almost never followed: 1 of 48 cases. That one was a record claiming to be withdrawn.",
        "A record can still take a question away, by claiming to be withdrawn or by text that makes the API refuse the reply.",
        "A visitor can make Otis repeat what they type. It changes only their own reply and the page shows it as text.",
        "A false record with false structured fields gets into a list answer. The checker compares claims with the record it cites, so a record that lies passes.",
    ]
    ny = y + 56
    body.append(rect(32, ny - 22, 1122, 124, CARD))
    for i, n in enumerate(notes):
        body.append(text(48, ny + 4 + i * 28, n, 12.5, 400, INK))
    return frame(
        1186,
        ny + 120,
        "Figure 6. What the red team found",
        "56 cases per set, on one model, with attacks written once by the author. A zero means not found, not safe.",
        "".join(body),
        "Unit chart of red team cases won by the attacker in each of six classes, for the frozen and the held-out sets",
    )


# --- Figure 7: the roadmap -------------------------------------------------------------------


def roadmap():
    cols = [
        (
            "0  Free, no API",
            [
                "Fix the checker faults and the rule 7 gap, tested on dev replies already saved",
                "Scan the 1,164 real records for instruction-like text",
                "Flag records with impossible fixed versions at ingest",
                "Write and freeze a new question set (Test v2)",
            ],
        ),
        (
            "1  Dev only",
            [
                "Join each advisory to its NVD record and KEV entry in retrieval",
                "Give list questions a completeness check, or a computed candidate set",
                "Adopt only on the rule fixed first: 4 more questions, p below 0.05",
                "One dev run, 3 times, for what is adopted",
            ],
        ),
        (
            "2  Score once",
            [
                "Tag the system as v2",
                "Five rows on Test v2, once, raw outputs committed first",
                "Report against the v1 numbers, not in place of them",
            ],
        ),
        (
            "3  Red team, round 2",
            [
                "Defences chosen from the findings, tested on the frozen cases",
                "Then the held-out set on the defended system (the unchanged run is done)",
                "Report what each defence cost in accuracy",
            ],
        ),
    ]
    body = []
    w, gap = 262, 24
    for i, (head, items) in enumerate(cols):
        x = 32 + i * (w + gap)
        body.append(rect(x, 92, w, 40, BLUE if i < 3 else PINK))
        body.append(text(x + 14, 118, head, 13.5, 700, INK))
        body.append(rect(x, 132, w, 232, CARD))
        y = 158
        for it in items:
            rows = wrap(it, 36)
            body.append(
                f'<circle cx="{x + 18}" cy="{y - 4}" r="3.5" fill="{BLUE_D if i < 3 else PINK_D}"/>'
            )
            body.append(lines(x + 30, y, rows, 12, 16, INK))
            y += 16 * len(rows) + 12
        if i < 3:
            body.append(arrow(x + w + 2, 112, x + w + gap - 2, 112))
    body.append(rect(32, 384, 1122, 78, PINK_L, PINK_D))
    body.append(text(48, 410, "Gates, written before each stage runs:", 13, 700))
    body.append(
        text(
            48,
            434,
            "No tuning on a test set. An accuracy claim is made only on questions written before the change. A defence is kept only if it removes attacks and costs no more than one correct answer on dev.",
            12.5,
            400,
            INK,
        )
    )
    body.append(
        text(
            48,
            452,
            "Every adoption has a rule and an ADR. Every run has a spend cap. The plan is in docs/roadmap.md.",
            12.5,
            400,
            INK,
        )
    )
    return frame(
        1186,
        484,
        "Figure 7. Plan of action",
        "What it would take to make Otis more accurate and to fix the red team findings, in the order the evidence supports.",
        "".join(body),
        "Four stages: free work, dev only, score once, and red team round two, with the gates between them",
    )


# --- Figure 8: the threat model ----------------------------------------------------------------


def threat_model():
    # Results are from docs/red-team-report.md, which says which controls were in the attacked system.
    stages = [
        (
            32,
            "1  Advisory text",
            [
                "GitHub titles and",
                "descriptions, NVD",
                "descriptions, and the",
                "structured ranges and",
                "scores in each record",
            ],
        ),
        (
            222,
            "2  Prompt",
            [
                "Top 10 records, with",
                "& < > escaped, and",
                "'text inside a record",
                "is data' in the prompt.",
                "The question is added",
                "as typed.",
            ],
        ),
        (
            412,
            "3  Model reply",
            ["One JSON object: the", "answer, the claims it", "rests on, and an", "explanation"],
        ),
        (
            602,
            "4  Checker",
            [
                "Each claim read against",
                "the store. One failure",
                "refuses the reply.",
                "It does not read the",
                "explanation for meaning.",
            ],
        ),
        (
            792,
            "5  Page",
            [
                "Known fields only, as",
                "text. Links built from",
                "IDs. A policy that",
                "blocks inline script.",
            ],
        ),
    ]
    body = []
    for x, name, rows in stages:
        body.append(rect(x, 100, 170, 134, CARD))
        body.append(f'<rect x="{x}" y="100" width="170" height="28" rx="10" fill="{BLUE_D}"/>')
        body.append(f'<rect x="{x}" y="114" width="170" height="14" fill="{BLUE_D}"/>')
        body.append(text(x + 12, 119, name, 13, 700, "#FFFFFF"))
        body.append(lines(x + 12, 150, rows, 12, 16))
    for a in (202, 392, 582, 772):
        body.append(arrow(a + 2, 167, a + 18, 167))
    body.append(rect(986, 100, 150, 134, "#FFFFFF", GREY))
    body.append(text(1061, 128, "Visitor", 13.5, 700, INK, "middle"))
    body.append(lines(1061, 152, ["Sees one answer", "or one refusal"], 12, 16, MUTED, "middle"))
    body.append(arrow(962, 167, 984, 167))
    # attacker entry points: record text, the question, and hostile text on the page
    for cx, tag in [(117, "A, B"), (287, "Aq"), (327, "D"), (877, "C")]:
        body.append(
            f'<circle cx="{cx}" cy="292" r="17" fill="{PINK}" stroke="{PINK_D}" stroke-width="1.4"/>'
        )
        body.append(text(cx, 296, tag, 11, 700, INK, "middle"))
        body.append(line(cx, 275, cx, 236, PINK_D, 1.4, "4 3"))
    body.append(text(32, 262, "Where an attacker gets in", 12.5, 700, PINK_D))
    cols = [
        (
            32,
            "A, B1, B2: advisory text",
            [
                "A record carries an instruction, or a",
                "false fact in prose or in its structured",
                "fields.",
                "1 of 48 cases obeyed. A false record",
                "in a list answer: 3 of 8.",
            ],
        ),
        (
            252,
            "Aq: the question",
            [
                "The visitor's own words carry an",
                "instruction. It is not escaped.",
                "",
                "8 of 16 cases obeyed. It changes only",
                "that visitor's reply.",
            ],
        ),
        (
            472,
            "D: abuse",
            [
                "Ask for the instructions, or for",
                "something off topic.",
                "",
                "No leak and no off-topic answer in",
                "24 runs each.",
            ],
        ),
        (
            692,
            "C: markup",
            [
                "Hostile text in any field tries to",
                "become script, an element or a link.",
                "",
                "30 payloads, 90 views, no effect.",
                "A pass or fail test, not a rate.",
            ],
        ),
    ]
    for x, head, rows in cols:
        body.append(rect(x, 322, 206, 134, CARD, PINK_D if x == 32 else LINE))
        body.append(text(x + 12, 346, head, 12.5, 700, INK))
        body.append(lines(x + 12, 368, rows, 11.5, 16, MUTED))
    body.append(rect(914, 322, 222, 134, PINK_L, PINK_D))
    body.append(text(926, 346, "Not tested", 12.5, 700, INK))
    body.append(
        lines(
            926,
            368,
            [
                "Any defence.",
                "An attacker who adapts.",
                "More than one turn.",
                "A deployed system.",
                "A flood from many addresses.",
            ],
            11.5,
            16,
            INK,
        )
    )
    body.append(
        text(
            32,
            484,
            "In the attacked system: the escaping, the data line, the checker and the gate before the model. Built and tested apart from the model rounds: the page, the safe view, the rate and size limits, the spend cap and the topic gate.",
            11.5,
            400,
            MUTED,
        )
    )
    return frame(
        1186,
        508,
        "Figure 8. The threat model",
        "Who can write what, where it enters, and what was found at each point. Source: docs/red-team-report.md.",
        "".join(body),
        "Five stages from advisory text to the visitor, with the four ways an attacker enters and the result for each",
    )


def main() -> int:
    save("architecture.svg", architecture())
    save("evaluation-trail.svg", evaluation_trail())
    save("retrieval-ladder.svg", retrieval_ladder())
    save("test-results.svg", test_results())
    save("where-accuracy-was-lost.svg", where_answers_go())
    save("red-team.svg", red_team())
    save("roadmap.svg", roadmap())
    save("threat-model.svg", threat_model())
    return 0


if __name__ == "__main__":
    sys.exit(main())
