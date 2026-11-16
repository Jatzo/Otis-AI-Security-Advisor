# R1 misses and package sizes

Written by `scripts/describe_retrieval.py` from files already saved, with no retrieval, no model and no network. See [the plan](evidence-round-plan.md), step 1, items 5 and 6. It is descriptive. It led to a post hoc plan amendment (R1 at depth 20 added as a candidate), and it counts as a look in [the ledger](ledger.md).

Answerable questions only: 32 on v1 dev and 88 on v1 test. Each cell is questions where all the needed records were in the list, over questions in the group. A miss is the difference.

### By question type

| Group | dev top 10 | dev top 20 | test top 10 | test top 20 |
|---|---|---|---|---|
| disagree | 5/8 | 5/8 | 6/22 | 6/22 |
| lookup | 8/8 | 8/8 | 20/22 | 22/22 |
| multihop | 2/7 | 3/7 | 9/18 | 11/18 |
| version | 9/9 | 9/9 | 18/26 | 24/26 |

### By how many records the answer needs

| Group | dev top 10 | dev top 20 | test top 10 | test top 20 |
|---|---|---|---|---|
| 1 | 14/14 | 14/14 | 37/42 | 41/42 |
| 2 | 8/13 | 8/13 | 14/34 | 14/34 |
| 3 | 2/4 | 3/4 | 1/2 | 2/2 |
| 4 or more | 0/1 | 0/1 | 1/10 | 6/10 |

### By whether the question names an ID

| Group | dev top 10 | dev top 20 | test top 10 | test top 20 |
|---|---|---|---|---|
| False | 8/11 | 9/11 | 19/31 | 26/31 |
| True | 16/21 | 16/21 | 34/57 | 37/57 |

### By whether the question names exactly one package

| Group | dev top 10 | dev top 20 | test top 10 | test top 20 |
|---|---|---|---|---|
| False | 10/15 | 10/15 | 22/44 | 24/44 |
| True | 14/17 | 15/17 | 31/44 | 39/44 |

### What R10 could change

R10 would scope 61 of 120 answerable questions (the ones that name exactly one package). The other 59 would get R1's top 10 unchanged. On the scoped questions R1's top 10 holds all the needed records for 45/61 and its top 20 for 54/61.

The match is on the package name as written in the corpus, so wordings such as 'Log4j Core', 'Spring MVC' or 'Struts 2' are not counted. The share of questions that name a package is a floor, and R10 will scope fewer free-form questions than this.

## Package sizes

Advisories per package in the published corpus. The cap for R10 is 20 records.

| Package | Advisories | Fits in the cap |
|---|---|---|
| django | 162 | no |
| pillow | 116 | no |
| org.apache.struts:struts2-core | 60 | no |
| aiohttp | 55 | no |
| axios | 55 | no |
| org.springframework:spring-webmvc | 27 | no |
| cryptography | 24 | no |
| urllib3 | 22 | no |
| org.apache.logging.log4j:log4j-core | 12 | yes |
| lodash | 10 | yes |
| jinja2 | 10 | yes |
| requests | 8 | yes |
| ws | 7 | yes |
| flask | 5 | yes |
| express | 5 | yes |
| pyyaml | 4 | yes |
| jsonwebtoken | 4 | yes |
| minimist | 2 | yes |

Median 11, largest 162. 10 of 18 packages fit in 20 records. The rest cannot be held whole, so for those R10 is R1's ranking filtered to the package, and a completeness check could not be satisfied.
