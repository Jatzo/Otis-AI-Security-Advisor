# Debug log

Non-trivial bugs: what broke, how it was found, the fix, and the regression test that now guards it.

## 2026-11-01: the secret-scan self-test died before it scanned anything

**What broke.** `scripts/check_secret_scan.sh` plants a fake GitHub token and fails unless gitleaks reports it. It exited with code 141 every time, whether the scanner found the token or not. In CI that would have shown as a failed job for the wrong reason, and the scan could never have been proved to work.

**How it was found.** Before the first push, the script was run against two stand-in scanners on PATH: one that reports any token-shaped string, one that reports nothing. Both runs exited 141, where 0 and 1 were expected.

**Cause.** The token was generated with `tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 36`. Once `head` has its 36 characters it closes the pipe, and `tr` is killed by SIGPIPE (128 + 13 = 141). Under `set -o pipefail` that counts as the pipeline failing, and `set -e` stopped the script on the line that only builds the fake token.

**Fix.** The token is now built in a plain bash loop with no pipe.

**Regression test.** `tests/test_secret_scan_check.py` runs the script with stand-in scanners and checks it passes only when the token is found. A later review found the same class of fault one step on: gitleaks exits 1 for a leak and for a crash alike, so a crash would have counted as a catch. The script now asks gitleaks for exit code 99 on a leak, and a third stand-in that crashes with exit 1 must make it fail.

## 2026-11-01: the first data report counted some pairs twice

**What broke.** The first run of the data report on the real snapshot said there were 576 (advisory, CVE) pairs, then listed their shapes: 275, 199, 141, 94 and 66. Those add up to 775. A table of 576 things cannot have 775 rows' worth of counts.

**How it was found.** By adding up the column. The report's numbers had not been hand-checked against anything yet, and the sum was the first thing that could be checked without a second source.

**Cause.** The "a v4 score is present" line was counted into the same table as the v3 shapes, but v4 is a second question about the same pairs, not another kind of pair. A pair with a v3 score on one side and a v4 score on the other was counted twice.

**Fix.** The shapes are now exclusive and add up to the pair count. CVSS v4 has its own table, which also shows that NVD scores none of these CVEs with v4 itself.

**Regression test.** `test_an_advisory_naming_two_cves_makes_two_pairs` now asserts that the shape counts sum to the number of pairs. It fails against the old code and passes against the fix.

## 2026-11-01: the same record hashed differently on Windows and on CI

**What broke.** Every raw record was saved with Windows line endings (CRLF), and the manifest stored a hash of those bytes. Git stores the files with plain line endings (LF), so on the Linux CI runner the committed sample would hash differently from the manifest. The sample's "byte for byte" test would have failed on the first push, and a snapshot name would have depended on whose machine made it.

**How it was found.** In the review of the finished change, by opening a sample file as bytes: 109 CRLF pairs and no bare LF. The test had passed locally only because the files on disk were still CRLF.

**Cause.** `Path.write_text` translates `\n` to the platform's line ending. It was meant to be a harmless default and it changed the bytes that were being hashed.

**Fix.** Records, fetch logs and the manifest are written with `newline="\n"`. The 1,170 existing raw files were converted, and checked to equal what the new code writes. `.gitattributes` marks `data/sample/**` and `data/manifest.json` as `-text`, so git does not convert them on any machine. A second tool then did the same thing: the pre-commit end-of-file fixer added a closing newline to every JSON file on the first commit attempt, which would have changed their hashes again. Records, logs, the manifest and the sample summary now end with a newline. The manifest, store, report and sample were rebuilt, so the snapshot name is `2d04b933ea7b`.

**Regression tests.** `test_records_and_fetch_logs_are_written_with_unix_line_endings` fails against the old code on Windows. On Linux it cannot fail, so the byte-for-byte sample test is the check that runs on CI. `test_every_file_ends_with_a_newline_so_the_pre_commit_fixer_changes_nothing` fails against the code that omitted the newline.
