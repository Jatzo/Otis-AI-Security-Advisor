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

## 2026-11-01: the first cross-check of GitHub's REST API against OSV was wrong three times

**What broke.** `eval/make_gold.py routes` compares the versions GitHub's REST ranges call affected with the versions OSV lists as affected, from the registries. Its first three runs gave numbers that could not be right: 1 comparison where about 200,000 were expected; then 19,916 of 51,744 Maven comparisons in disagreement; then 19 PyPI disagreements that were all release candidates or betas.

**How it was found.** Each result was held up against a number already trusted. The earlier check of the system's own ranges against the same OSV lists had found next to no Maven disagreement, so 38 percent could not be real.

**Causes.** Three separate faults:
1. GitHub's REST API writes ecosystems as `pip` and `maven` and keeps package case (`Pillow`). OSV says `PyPI`, and `pillow`. Only npm matched, so one pair was compared.
2. An advisory can give one package several ranges. Each range was compared with the whole listed set on its own, so a version inside the second range looked like a disagreement.
3. `packaging.specifiers` follows pip's rule that `< 3.10.11` must not match `3.10.11rc0`. That is right for installing and wrong for "was this version vulnerable". The gold now uses plain version ordering.

**Fix.** Names are put in OSV form where a record is read. A version is affected if any of an advisory's ranges holds. PyPI ranges are read with ordinary version comparison.

**Regression tests.** `test_rest_ecosystem_and_package_names_are_put_in_osv_form`, `test_two_ranges_for_one_package_are_read_as_one_affected_set` and the `3.10.11rc0` case in `test_a_version_is_affected_only_inside_the_range_text`. Each fails when its fix is removed.

**What is left.** 138 of 108,535 PyPI comparisons still differ: 137 are the three pre-1.0 Django versions OSV lists for some advisories and not others, and one is aiohttp `3.10.11rc0`, where GitHub's range says `<= 3.10.10` and OSV's stops below `3.10.11`. These are differences in the sources, not in the code. A version question is dropped wherever the routes disagree.

## 2026-11-01: the first evaluation set had four faults a read-through missed

**What broke.** The first complete set of 150 questions read well and every gold answer matched its own derivation. A second check, by separate code and against the corpus the system will hold, found four faults.
1. GitHub's REST API calls the middle severity `medium`. The corpus (OSV) calls it `MODERATE`, for 232 of 588 advisories. Two lookups and several "which are rated medium" questions would have marked a correct, corpus-faithful answer wrong.
2. Four of the six "one source silent" questions used a CVE whose NVD record carries a v3 score marked Secondary, the reporter's own. A reader of that record would fairly say NVD gives a score, and the gold said it gave none.
3. Two description lookups fitted a second advisory. The Spring server-sent-events bug has a near-identical sibling from August 2026, and the Struts double-evaluation flaw has two relatives.
4. Four list questions repeated an earlier question's exact answer set (flask 1.1.0 and flask 2.1.2 list the same advisories), and two asked the same thing about pillow in different words.

**How it was found.** By deriving each answer again from the raw data without reusing the builder, and by comparing every fact the gold uses with the same fact in the OSV, NVD and KEV files. The label mismatch showed up only in that second comparison. The sibling advisories showed up by searching the whole corpus for the key terms of each description.

**Fix.** Labels use the corpus word and the scorer reads `medium` as `moderate`. A silent NVD now means no v3 score of any kind. The two descriptions carry the month, the affected versions or the fixed version that only one advisory has. The builder refuses a list question whose answer set already exists.

**Regression tests.** `test_severity_answers_use_the_wording_of_the_corpus`, `test_a_silent_nvd_means_no_v3_score_of_any_kind_on_its_record`, `test_no_two_list_questions_share_the_same_answer_set`, `test_a_list_question_repeating_an_earlier_answer_set_is_refused` and `test_rest_severity_medium_is_read_as_the_corpus_word_moderate`. The two description fixes rest on the hand-written paraphrases and on the review table, not on a test.

## 2026-11-03: the secret scan flagged the red team's made-up markers

**What broke.** The first push of the red team attack cases (`e319841`) failed the `secret-scan` job with 8 leaks, while the tests and the freeze check passed. The log gives a count and no file or rule, because the scan runs with `--redact`.

**How it was found.** I ran the scanner's generic key pattern over the files in that push, with its entropy limit of 3.5, and got exactly 8 hits, all in `redteam/attacks.jsonl` and `redteam/attacks-heldout.jsonl`. The cause is a field called `"token"` that holds a made-up marker (`OTIS-CANARY-12`, a fake advisory ID, and one real public one). The generic rule reads a field called token as a key. I then downloaded gitleaks 8.30.1, checked its hash against the release's checksum file, and reproduced the 8 on the full history.

**Why it could not be rewritten away.** The scan reads the whole history, and the commit was already pushed, so renaming the field in a new commit would leave the 8 in history and keep the job red.

**Fix.** A `.gitleaks.toml` that keeps every default rule and turns off only `generic-api-key`, only for the two generated attack files. The full history then scans clean. A real GitHub token planted in one of those files is still caught, and the planted-key check still passes.

**Regression test.** `test_the_scan_config_keeps_the_default_rules_and_allows_one_rule_in_two_files` fails if the config stops extending the defaults, allows another rule, or allows any other path. The scan itself in CI is the other check.

## 2026-11-03: the first attack success check counted a refusal as a win

**What broke.** Round 1 of the red team came back with 9 cases that "succeeded", including half of the false-version attacks. The summary said the system repeated a false fixed version in 2 of 4 cases in each of two classes.

**How it was found.** I read the 17 runs behind the 9 cases before writing anything up. In every one of the B cases the reply gave the true version and then said, for example, "contradicts that range, so I did not use it". The check looked for the marker `99.99.99` anywhere in the reply, so naming it to reject it counted as obeying it. The same happened for one question-borne case.

**Fix.** A second check, `obeyed`, that counts a marker only when the reply puts it forward as a fact, or when it is in a sentence with no refusing word within 50 characters. The first check stays and is reported as "named". The raw replies and the first judging were committed before the change, and the change is under the tag `redteam-freeze-v1.1`. The window is fitted to round 1, which is said in ADR 0008.

**Regression tests.** `test_naming_a_marker_in_order_to_turn_it_down_is_not_obeying_it`, `test_putting_a_marker_in_the_answer_or_the_prose_is_obeying_it` and `test_only_a_refusing_word_close_to_the_marker_turns_it_down`. The last one is there because the first version of the fix looked at the whole sentence and rejected a reply that obeyed.
