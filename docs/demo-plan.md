# Phase 7 plan: the public demo

> **Superseded on 3 November 2026.** Otis is a portfolio project and not a product, so the live deployment, the spend caps and the container below are not planned. Step 1 (the real store and client wiring) was built and is tested. The write-up comes first, as the [README](../README.md) and [roadmap](roadmap.md) set out. The reviewer's points are kept here because they apply if a demo is ever deployed.

Written before any of it is built. PROGRESS.md sets the target: a demo on a Hugging Face Docker Space that shows the answer, the evidence and each check, with the caps live. PLAN.md adds that the demo must be clickable, rate-limited, show text as escaped text only, and report cost and latency.

## What exists, and what does not

Exists and tested without a server: the page (`src/advisor/web/page/`), the safe view (`view.py`), the limits and spend cap (`limits.py`), the handler that applies them (`ask.py`), and the security headers (`headers.py`). The handler takes its retrieval and model client as arguments, so it has never run against the real store.

Does not exist:

1. The wiring from the handler to the real store and a real client (retrieval over `data/advisor.db`, a client with a timeout, a startup that fails loudly).
2. A server that speaks HTTP, serves the page and sets the headers on every response.
3. The evidence and the per-claim checks in what the page shows. Today `view()` returns the answer fields only.
4. A container image, and a place to put the data it needs.
5. Cost and latency in the response, so the PLAN.md production signals are visible.
6. Anything on Hugging Face: an account, a Space, a secret for the model key.

## The decisions that are yours

Each needs your answer before the step that depends on it. None blocks step 1.

1. **Server packages.** PROGRESS.md recorded FastAPI. It adds `fastapi` and `uvicorn` (and `starlette`, `pydantic` already present) to the runtime dependencies. I would pin exact versions at least two weeks old, as for `anthropic`, and update `uv.lock`. The alternative is the standard library's `ThreadingHTTPServer`: no dependency, more code to get right (header handling, body limits), and a weaker answer to an interviewer. I recommend FastAPI.
2. **Where the data lives.** `data/advisor.db` (2.9 MB) is gitignored. The Space needs it. I would put it in the Space repository only, built by a deploy script from the local store, with `data/ATTRIBUTION.md` beside it for the CC BY 4.0 notice. The alternative is to rebuild it in the image from the sources, which needs a slow NVD fetch at build time.
3. **The model key and its limit.** The key goes in as a Space secret and never in the image or the repository. Set a monthly spend limit on that key in the Anthropic console as well, since the in-process $3 daily cap resets if the process restarts. Both are yours to do.
4. **The Hugging Face side.** An account, a Space created as Docker with port 7860, the secret, and the push. I cannot do any of that and will not handle the credentials. I will prepare the repository contents and the commands.
5. **What is logged.** I propose counts, status and cost per request, and never the question text, so the demo keeps no record of what visitors typed.

## Files

New: `src/advisor/web/service.py` (real wiring), `src/advisor/web/server.py` (the HTTP app), `Dockerfile` and `.dockerignore`, `scripts/build_space.py` (assembles the Space repository), `docs/adr/0009-` (the server and where the data lives), `tests/test_web_service.py`, `tests/test_web_server.py`.

Changed: `src/advisor/web/view.py` (evidence and per-claim checks), `src/advisor/web/ask.py` (cost and latency in the response, claims passed through), `src/advisor/web/page/*` (the evidence panel and the checks, in the Otis design), `pyproject.toml` and `uv.lock` (decision 1), `README.md` (the demo link and the deployment note), `PROGRESS.md`.

Not changed: anything under `eval/`, the tagged system code (`src/advisor/generation`, `src/advisor/retrieval`, `eval/task.md`), or the red team files. The demo runs the system exactly as tagged.

## Steps, smallest first

1. **Real wiring** (no new dependency, no decision needed). `service.py` builds the units from the store, builds the keyword index once at startup, and returns the handler's dependencies with a real `retrieve` (the top 10 by the adopted rung R1), a model client with a 60 second timeout and no retries, and the facts. Startup refuses to run without the store or the key. Tested with the small test store and a stand-in client, including many requests at once.
2. **Evidence and checks in the view.** `view()` and the handler also return the records the model was shown (ID, source, a one-line header, a link built from the ID) and each claim with its pass, fail or unverifiable status, so the page can show what was read and what was checked. Tested like the rest of the view, and added to the render tests so hostile text in a record cannot become markup.
3. **The server and the page** (needs decision 1). A FastAPI app with the headers on every response, the page served from the package, a body size limit, and the address taken from the connection or from the one trusted proxy hop. Tested through the framework's test client.
4. **Cost and latency** in the response and the page footer.
5. **The container and the Space repository** (needs decisions 2 to 4). A Dockerfile that runs as a non-root user on port 7860, `scripts/build_space.py`, and a local `docker build` and run before anything is pushed. ADR 0009.
6. **Deploy, and check the caps live.** Push to the Space, set the secret, then try the limits against the public address: the per-address limit, the daily cap, an oversize body, and an off-topic question. Record what happened.

## Things I do not know yet

- Whether the Hugging Face proxy sets `X-Forwarded-For` in a way the limiter can trust, and with how many hops. Until that is checked on the live Space, `trusted_hops` stays 0, which means every visitor looks like the proxy and shares one limit. Step 6 settles this.
- How long the first request takes, and the index build at startup, on the Space's hardware. Phase 5 measured a median of about 4.6 seconds per call from here.
- Whether the Space's free tier sleeps the container, which would reset the in-memory limiter and the daily cap on wake.

## What this demo will not claim

It runs the system as tagged. Round 1 of the red team found that a visitor can make Otis repeat text they typed, and that a poisoned record can take a question away. Neither has a defence in the demo, and the page and the README will say so, with a link to the red team report.

## Amendments

Version 2, after a read-only critique. These change the plan above where they differ from it.

**New decision 0: credit and budget.** About $0.74 of credit is left and a demo needs money to answer questions. Before step 6, buy credit and set the demo's monthly budget, then work the daily cap out from it and read it from an environment variable (the $3 in `limits.py` is only a default). The critique says Anthropic console spend limits are set per workspace and not per key, and that you have a monthly ceiling of £25 shared with other work. I have not checked either, so please confirm both. If it is per workspace, the demo gets its own workspace, key and limit.

**Step 1 changes (done in this commit).**
- Reserving every attempt means a request holds about $0.50 until it settles, so a $3 daily cap allows only about six questions in flight at once, and the seventh gets the "as many as it can today" message even though the cap is not spent. Step 3 gives a busy server its own message and the tests cover both.
- Retries are inside the spend cap's blind spot: `answer.ask` makes up to `ATTEMPTS` (3) paid attempts, and a timeout counts as a retryable connection error, so one request can cost three times its reservation and run for about three minutes. The handler now reserves `ATTEMPTS` times the worst case for each request.
- A shared SQLite connection failed under 40 simultaneous requests ("bad parameter or other API misuse"), and the keyword index only works on the thread that built it. Both are fixed in `service.py` without touching the tagged system: facts use one read-only connection per thread, and retrieval runs on one worker thread.
- The timeout should come from the measured latency, not a guess. Phase 5 measured a median of 4.6 seconds a call here; the 99th percentile still has to be read from the saved results before step 3 fixes the number.

**Step 3, the server, adds:**
- `uvicorn --workers 1 --no-proxy-headers --no-access-log`, stated in the Dockerfile and in ADR 0009. The limiter and the cap are in memory, so more than one worker would multiply them. `client_address` is the only code that reads the forwarded header.
- Refuse a request when `Content-Length` is over 8 KiB and stream with a running cap for a body with no length, so the whole body is never read before the size check. Take raw bytes and not a framework model, because the framework's 422 errors echo the input. Turn off the generated docs and schema routes.
- Write the endpoint as a plain `def`, not `async def`, so a slow call does not block the server. Add a small semaphore around model calls so slow calls cannot use every thread while the page and the health route still need serving. Add a health route.
- Headers on every response, including static files, 404s and 500s, with a test on each. `frame-ancestors 'none'` would blank the Space's page, because Hugging Face shows the app in a frame. Decide whether to allow `https://huggingface.co` or to link only the `*.hf.space` address. Fonts, if the design uses any, are hosted by us, with `font-src 'self'`.
- `httpx` is already installed and is added as a dev dependency for the test client, with `fastapi` and `uvicorn` in decision 1.

**Step 5, the container, adds:**
- `answer.py` finds `eval/task.md` and `.env` from its own location. The image copies the source tree and runs from it, and does not install the package. At startup the demo hashes the system prompt against the tagged one and refuses to start if it differs, and the page shows the commit it is running.
- `.dockerignore` and `build_space.py` are allowlists, so `.env`, `data/raw` and everything else never get in. gitleaks runs over the Space repository before every push, because that repository is public too.

**Logging.** No access log. Log status, cost and latency only, never the question or the reply, and keep the stack trace out of the log when it could carry reply text. Find out who can read a Space's logs.

**The page.** The CC BY 4.0 attribution goes in the page footer as well as in `data/ATTRIBUTION.md`. The page and the README say that the first request after a sleep is slow and resets the limits. Cost and latency are defined for a reply with no model call as zero and the time taken.

**Step 6.** The live check of the daily cap uses a tiny value (about $0.10), so it does not spend real money. Private Space first, to settle the proxy hop count before anyone else can reach it.

**Also.** A first bug found during the build goes in `docs/debug-log.md`, with a regression test.
