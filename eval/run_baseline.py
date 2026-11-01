"""Asks the bare model (no retrieval, no tools) every question in one split and keeps each reply.

The model, effort and token limit are fixed here, before the freeze, so the baseline cannot be
tuned after seeing a score. Dev is the default split. Test needs --allow-test and is run once.
Real calls only run when the frozen files match the freeze tag, so the claim that the rules
were written before any results were seen can be checked from the git history.

Usage:
    python eval/run_baseline.py --dry-run
    python eval/run_baseline.py --split dev --runs 3 --max-spend 8
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import anthropic

EVAL = Path(__file__).resolve().parent
ROOT = EVAL.parent
MODEL = "claude-sonnet-5-5"
EFFORT = "high"  # the model's own default, so the baseline is not a deliberately weak one
MAX_TOKENS = 16000
ATTEMPTS = 3
# Dollars per million tokens, stored on every result line so a later price change cannot
# rewrite what an old run cost.
PRICE = {"input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write": 2.50}
FREEZE_TAG = "eval-freeze-v1"
HASHED = (
    "task.md", "baseline_prompt.md", "run_baseline.py", "score.py", "rules.md",
    "answer_schema.json", "questions.jsonl", "gold.jsonl", "id_snapshot.json",
)  # fmt: skip
RETRYABLE = (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError)


def system_prompt() -> str:
    return (EVAL / "task.md").read_text(encoding="utf-8") + (EVAL / "baseline_prompt.md").read_text(
        encoding="utf-8"
    )


def build_request(question_text: str, system: str) -> dict:
    """No temperature, no prefill, no fallback model: the baseline is one model, as it came."""
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": EFFORT},
        "messages": [{"role": "user", "content": question_text}],
    }


def cost_of(usage: dict) -> float:
    return (
        usage["input"] * PRICE["input"]
        + usage["output"] * PRICE["output"]
        + usage["cache_read"] * PRICE["cache_read"]
        + usage["cache_write"] * PRICE["cache_write"]
    ) / 1_000_000


def worst_case_call(system: str, question_text: str) -> float:
    """The most one call can cost: every input token at the full price (four characters a
    token is generous) and the whole output limit spent."""
    tokens_in = (len(system) + len(question_text)) // 3
    return (tokens_in * PRICE["input"] + MAX_TOKENS * PRICE["output"]) / 1_000_000


def read_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip


def frozen_problem(tag: str, run_git: Callable = git) -> str | None:
    """Says why a real run must not start, or None. The tag must exist and nothing frozen may
    differ from it, in the working tree or as an untracked file."""
    if run_git("rev-parse", "-q", "--verify", f"refs/tags/{tag}").returncode != 0:
        return f"The tag {tag} does not exist yet. Tag the freeze first, then run the baseline."
    skip = ["--", "eval", ":(exclude)eval/results", ":(exclude)eval/errata.jsonl"]
    if run_git("diff", "--quiet", tag, *skip).returncode != 0:
        return f"A frozen file under eval/ differs from {tag}. Restore it, or tag a new freeze."
    untracked = run_git("ls-files", "--others", "--exclude-standard", *skip[1:]).stdout.strip()
    if untracked:
        return f"Untracked files under eval/ are not in {tag}: {untracked.splitlines()[0]}"
    return None


def provenance(run_git: Callable = git) -> dict:
    commit = run_git("rev-parse", "HEAD").stdout.strip()
    hashes = {
        name: hashlib.sha256((EVAL / name).read_bytes()).hexdigest()
        for name in HASHED
        if (EVAL / name).exists()
    }
    return {"commit": commit, "hashes": hashes}


def read_key() -> str | None:
    """ANTHROPIC_API_KEY from the environment or from .env. Never printed."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    env_file = ROOT / ".env"
    if env_file.exists():
        # utf-8-sig, because PowerShell and Notepad can write a byte-order mark.
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "ANTHROPIC_API_KEY" and value.strip():
                return value.strip().strip("\"'")
    return None


def ask(client, request: dict, sleep: Callable = time.sleep) -> tuple[object, int, float]:
    """One reply, retrying only what is worth retrying. Returns the reply, the attempts used and
    the seconds the successful attempt took. The SDK's own retries are off so every attempt is
    counted here."""
    for attempt in range(1, ATTEMPTS + 1):
        started = time.monotonic()
        try:
            reply = client.messages.create(**request)
        except RETRYABLE:
            if attempt == ATTEMPTS:
                raise
            sleep(2**attempt)
        else:
            return reply, attempt, time.monotonic() - started
    raise AssertionError("unreachable")


def result_line(question: dict, run: int, reply, attempts: int, seconds: float, proof: dict):
    usage = {
        "input": reply.usage.input_tokens or 0,
        "output": reply.usage.output_tokens or 0,
        "cache_read": getattr(reply.usage, "cache_read_input_tokens", 0) or 0,
        "cache_write": getattr(reply.usage, "cache_creation_input_tokens", 0) or 0,
    }
    details = getattr(reply, "stop_details", None)
    return {
        "id": question["id"], "run": run, "split": question["split"],
        "text": "".join(b.text for b in reply.content if b.type == "text"),
        "stop_reason": reply.stop_reason,
        "stop_category": getattr(details, "category", None) if details else None,
        "usage": usage, "price": PRICE, "cost_usd": cost_of(usage),
        "latency_s": round(seconds, 3), "attempts": attempts,
        "request_id": getattr(reply, "_request_id", None), "model": reply.model,
        "requested_model": MODEL, "effort": EFFORT, "max_tokens": MAX_TOKENS, **proof,
    }  # fmt: skip


def run_split(
    questions: list[dict], results: Path, client, runs: int, max_spend: float, proof: dict,
    say: Callable = print,
) -> str:  # fmt: skip
    """Asks every question not yet answered in each run. Stops, with the reason, before a call
    that could take the total over the cap. Each line is written as soon as it arrives, so a
    crash loses nothing and a resume spends nothing twice."""
    system = system_prompt()
    done = read_lines(results)
    spent = sum(x["cost_usd"] for x in done)
    answered = {(x["run"], x["id"]) for x in done}
    for run in range(1, runs + 1):
        for question in questions:
            if (run, question["id"]) in answered:
                continue
            if spent + worst_case_call(system, question["question"]) > max_spend:
                return (
                    f"Stopped at run {run}, {question['id']}: "
                    f"${spent:.2f} spent, cap ${max_spend:.2f}."
                )
            reply, attempts, seconds = ask(client, build_request(question["question"], system))
            line = result_line(question, run, reply, attempts, seconds, proof)
            spent += line["cost_usd"]
            with results.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(line, sort_keys=True) + "\n")
            say(f"run {run} {question['id']} {line['stop_reason']} ${spent:.2f}")
    return f"Done. ${spent:.2f} spent in total."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument(
        "--max-spend", type=float, help="dollars, counting earlier runs in the file"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the first request; call nothing"
    )
    parser.add_argument("--allow-test", action="store_true", help="test is scored once per system")
    parser.add_argument("--freeze-tag", default=FREEZE_TAG)
    args = parser.parse_args()

    questions = [q for q in read_lines(EVAL / "questions.jsonl") if q["split"] == args.split]
    results = EVAL / "results" / f"baseline-{args.split}.jsonl"
    system = system_prompt()

    if args.dry_run:
        request = build_request(questions[0]["question"], system)
        print(json.dumps({**request, "system": f"[{len(system)} characters]"}, indent=1))
        print(f"\n{system}")
        likely_in = len(questions) * (len(system) + 200) // 3
        worst = len(questions) * worst_case_call(system, questions[0]["question"])
        print(f"About {likely_in} input tokens a run. Worst case for one run: ${worst:.2f}.")
        return 0

    if args.split == "test":
        if not args.allow_test or args.runs != 1:
            print("Test is scored once per system: use --allow-test and a single run.")
            return 1
        if len({x["id"] for x in read_lines(results)}) == len(questions):
            print("Every test question already has a baseline reply. Test is scored once.")
            return 1
    if args.max_spend is None:
        print("Give --max-spend in dollars. The cap is not optional.")
        return 1
    problem = frozen_problem(args.freeze_tag)
    if problem:
        print(problem)
        return 1
    key = read_key()
    if not key:
        print("No ANTHROPIC_API_KEY. Add it to .env (gitignored), then run again.")
        return 1

    client = anthropic.Anthropic(api_key=key, max_retries=0)
    results.parent.mkdir(parents=True, exist_ok=True)
    print(run_split(questions, results, client, args.runs, args.max_spend, provenance()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
