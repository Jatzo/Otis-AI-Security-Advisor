# Replay demo: saved answers on a static page

This is a replay, published at https://jatzo.github.io/Otis-AI-Security-Advisor/demo/. No model is called, nothing is fetched and nothing you do on the page is sent anywhere. It replaces the live demo that [demo-plan.md](demo-plan.md) described, which needs money for the model and a server, and Otis is a portfolio project and not a product.

## Run it

```powershell
python -m http.server -d docs/demo
```

Then open `http://localhost:8000`. The page loads `data.json` with `fetch`, so it needs a server and will not work from a file path. `#dg-003` after the address opens one question.

To rebuild the data file, which needs the local store:

```powershell
python scripts/build_replay.py
```

## What it shows

The 40 dev questions, answered by run 1 of the 3 saved dev runs (2 November 2026, `claude-sonnet-5-5`, $1.18 for the 40 calls). For each question:

- the gold answer the question is scored against;
- the model's own reply, as a visitor would be shown it, and whether the frozen scorer marks it right or wrong;
- what the Phase 5 checker did with it (tag `phase5-system-v1`), with each claim and the rule that refused it, if one did;
- the same replies run through the Phase 6 checker (tag `phase6-system-v1`), with no new model call. It says when the result is the same as the Phase 5 checker's;
- the 10 records the model was shown, each with a link built from its ID, a header and a short excerpt;
- the cost and time of the call.

Run 1 scores 31 of 40 for the model alone, 27 for the Phase 5 checker and 30 for the Phase 6 checker. Wrong and refused answers are shown as they happened.

## What it does not show

- **Dev questions only.** These are the dev questions, the set the system was tuned on. The test results are in [test-results.md](test-results.md). The Phase 6 figure comes from fixing faults seen on dev and test rows, so it is a repair figure ([checker-fixes.md](checker-fixes.md)).
- **Saved answers only.** A question you type is not answered. The page holds the 40 saved questions, and one run of the three.
- **Cut records.** Each is cut to a header and a short excerpt, with a link to the source. The advisory text is CC BY 4.0 from the GitHub Advisory Database, with that change, and NVD and CISA data carry the notices the page footer gives.
- **A replay, not a live service.** It is published on GitHub Pages from the `docs` folder of `main` ([ADR 0015](adr/0015-publish-the-replay-demo-on-github-pages.md)), and no model sits behind it. Nothing you type is answered.

## How it was kept safe

All text goes in with `textContent`, every class comes from a fixed table, and the only links are built in the page from an advisory or CVE ID to two fixed addresses. The page carries a Content-Security-Policy in a meta tag with no inline script. `tests/test_replay_demo.py` checks, with no model call:

- the data file's shape, that it holds the 40 dev questions and no test or Test v2 question, and that it is under 2 MB;
- that its totals and every checked reply match the saved results files;
- that hostile text (30 payloads) in every field of the data, in a real browser, makes no element, attribute or link the page did not make and runs no script, and that all 40 real questions render the same way;
- that the build script cannot reach a model, a key or an `.env` file, and that rebuilding from the local store reproduces the committed file and opens neither an `.env` file nor any test-split file. That last test skips where the store is not present, which includes CI.

Files: `docs/demo/` (the page and `data.json`), `scripts/build_replay.py`, `tests/test_replay_demo.py`, `tests/replay_harness.html`.
