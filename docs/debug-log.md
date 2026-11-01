# Debug log

Non-trivial bugs: what broke, how it was found, the fix, and the regression test that now guards it.

## 2026-11-01: the secret-scan self-test died before it scanned anything

**What broke.** `scripts/check_secret_scan.sh` plants a fake GitHub token and fails unless gitleaks reports it. It exited with code 141 every time, whether the scanner found the token or not. In CI that would have shown as a failed job for the wrong reason, and the scan could never have been proved to work.

**How it was found.** Before the first push, the script was run against two stand-in scanners on PATH: one that reports any token-shaped string, one that reports nothing. Both runs exited 141, where 0 and 1 were expected.

**Cause.** The token was generated with `tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 36`. Once `head` has its 36 characters it closes the pipe, and `tr` is killed by SIGPIPE (128 + 13 = 141). Under `set -o pipefail` that counts as the pipeline failing, and `set -e` stopped the script on the line that only builds the fake token.

**Fix.** The token is now built in a plain bash loop with no pipe.

**Regression test.** `tests/test_secret_scan_check.py` runs the script with stand-in scanners and checks it passes only when the token is found. A later review found the same class of fault one step on: gitleaks exits 1 for a leak and for a crash alike, so a crash would have counted as a catch. The script now asks gitleaks for exit code 99 on a leak, and a third stand-in that crashes with exit 1 must make it fail.
