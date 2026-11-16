# Dev-R pool count

Written by `scripts/count_dev_r_pool.py`, with no retrieval, no model and no network. See [the plan](evidence-round-plan.md), step 1, item 4.

The store holds 588 advisories with REST records. Subjects used by earlier questions: v1 test 127, v1 dev 48, Test v2 130.

Most questions of each subtype the generator can still make on its own, with seed 20261116. The same advisory cannot serve every subtype, so a mix drawn from several will be smaller.

| Subtype | disjoint | seen_dev |
|---|---|---|
| lookup/kev_id | 0 | 707 |
| lookup/fixed_id | 340 | 390 |
| lookup/severity_id | 634 | 722 |
| lookup/map_id | 622 | 707 |
| version/verdict | 634 | 722 |
| version/set | 0 | 6 |
| multihop/a1_nvd_score | 398 | 461 |
| multihop/a2_kev_set | 0 | 1 |
| multihop/a3_kev_pick | 0 | 2 |
| multihop/b_intersect | 1 | 13 |
| multihop/c_published | 278 | 320 |
| multihop/c_score | 213 | 238 |
| disagree/fixed_differ | 4 | 8 |
| disagree/fixed_agree | 226 | 256 |
| disagree/one_silent | 82 | 84 |
| disagree/band_differ | 44 | 54 |
| disagree/band_agree | 250 | 288 |
