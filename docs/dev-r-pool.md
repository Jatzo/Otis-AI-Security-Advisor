# Dev-R pool count

Written by `scripts/count_dev_r_pool.py`, with no retrieval, no model and no network. See [the plan](evidence-round-plan.md), step 1, item 4.

The store holds 588 advisories with REST records. Subjects used by earlier questions: v1 test 127, v1 dev 48, Test v2 130. After the reserve split, Dev-R may use 163 advisories, plus 44 seen only by v1 dev. The reserve is not counted.

Most questions of each subtype the generator can still make on its own, with seed 20261116. The same advisory cannot serve every subtype, so a mix drawn from several will be smaller.

| Subtype | disjoint | seen_dev |
|---|---|---|
| lookup/kev_id | 0 | 401 |
| lookup/fixed_id | 172 | 222 |
| lookup/severity_id | 326 | 414 |
| lookup/map_id | 316 | 401 |
| version/verdict | 325 | 414 |
| version/set | 0 | 6 |
| multihop/a1_nvd_score | 206 | 269 |
| multihop/a2_kev_set | 0 | 1 |
| multihop/a3_kev_pick | 0 | 2 |
| multihop/b_intersect | 1 | 9 |
| multihop/c_published | 135 | 175 |
| multihop/c_score | 103 | 129 |
| disagree/fixed_differ | 0 | 4 |
| disagree/fixed_agree | 116 | 146 |
| disagree/one_silent | 46 | 48 |
| disagree/band_differ | 20 | 30 |
| disagree/band_agree | 126 | 164 |
