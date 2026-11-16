# Corrections

A figure I published and later found wrong is corrected in the open, here, and not edited silently. Each entry says what was wrong, since when, what the right figure is, and the commit that fixed it. The old result files are not rewritten. A new line goes beside them.

| Date found | Where it was wrong | What was wrong | Right figure | Fixed in |
|---|---|---|---|---|
| 16 Nov 2026 | README section 9 and PROGRESS.md, since 2 November 2026 | My own blind spot-check marks were described as covering 5 of the 24 replies, agreeing on 4, with "can't tell" on 19. `eval/results/spotcheck-marks-joe.json` holds 4 marks (1 right, 3 wrong) and 20 "unsure". The "right" mark (reply 1) disagrees with the scorer, so 3 of the 4 agree. | Covers 4 of the 24, agrees on 3, "can't tell" on 20. The other conclusions stand: the check is thin and the marks are weak evidence. | the commit that adds `scripts/check_claims.py` |
| 16 Nov 2026 | README section 6.5 and `docs/test-results.md`, since 2 November 2026 | The structured row's "Median / p95" was given as "under 1 ms". The saved latencies give a median of 0.2 ms and a 95th percentile of 3 ms (nearest rank, 110 questions). | 0.2 ms / 3 ms | the commit that adds `scripts/check_claims.py` |
