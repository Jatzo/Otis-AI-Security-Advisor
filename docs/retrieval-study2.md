# Retrieval study 2 on Dev-R

Written by `scripts/retrieval_study2.py`, with no model and no network. See [the plan](evidence-round-plan.md), step 2. A cell is questions where every needed record was in the list, over questions in the group. R1@20 is candidate R11.

243 questions, 231 on advisories no earlier question used and 12 on advisories only v1 dev used (held out, no claim). Primary stratum without the held-out ones: 179 (rule 1 needs 140). R10 scoped 1 of them (it needs 40 to be judged) and 44 questions in all.

## Tests against the controls

| Candidate | against | n | control | candidate | gained | lost | net | needed net | p |
|---|---|---|---|---|---|---|---|---|---|
| R9 | R1@10 | 179 | 96 | 179 | 83 | 0 | 83 | 9.0 | 0.0000 |
| R11 | R1@10 | 179 | 96 | 99 | 3 | 0 | 3 | 9.0 | 0.2500 |

Holm: {'R9': True, 'R11': False}. Do no harm: {'R9': True, 'R11': True}. Passes rules 1 to 3: {'R9': True, 'R11': False}. Leading candidate: R9.

## Against R1 at 10 on the whole primary stratum (the common yardstick)

| List | candidate hits | control hits | gained | lost | net |
|---|---|---|---|---|---|
| R9 | 179 | 96 | 83 | 0 | 83 |
| R11 | 99 | 96 | 3 | 0 | 3 |
| R10 | 96 | 96 | 0 | 0 | 0 |
| R9x | 179 | 96 | 83 | 0 | 83 |
| R1@15 | 99 | 96 | 3 | 0 | 3 |
| R1@25 | 100 | 96 | 4 | 0 | 4 |

## Prompt size, as a share of R1 at 10 (characters of the user message)

{'R1@10': 1.0, 'R1@15': 2.052, 'R1@20': 2.788, 'R1@25': 3.549, 'R9': 0.627, 'R9x': 1.717, 'R10': 1.098}. Ceilings for the dev generation check: {'R9': 1.3, 'R10': 2.0, 'R11': 2.0}.

## Where the hits are

### Primary stratum by subtype

| Group | n | R1@10 | R1@15 | R1@20 | R1@25 | R9 | R9x | R10 |
|---|---|---|---|---|---|---|---|---|
| a1_nvd_score | 35 | 0/35 | 0/35 | 0/35 | 0/35 | 35/35 | 35/35 | 0/35 |
| b_intersect | 1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| band_agree | 25 | 11/25 | 11/25 | 11/25 | 11/25 | 25/25 | 25/25 | 11/25 |
| band_differ | 18 | 10/18 | 10/18 | 10/18 | 10/18 | 18/18 | 18/18 | 10/18 |
| c_published | 25 | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 |
| c_score | 25 | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 |
| fixed_agree | 25 | 11/25 | 13/25 | 13/25 | 14/25 | 25/25 | 25/25 | 11/25 |
| one_silent | 25 | 13/25 | 14/25 | 14/25 | 14/25 | 25/25 | 25/25 | 13/25 |

### All fresh questions by type

| Group | n | R1@10 | R1@15 | R1@20 | R1@25 | R9 | R9x | R10 |
|---|---|---|---|---|---|---|---|---|
| disagree | 93 | 45/93 | 48/93 | 48/93 | 49/93 | 93/93 | 93/93 | 45/93 |
| lookup | 28 | 28/28 | 28/28 | 28/28 | 28/28 | 28/28 | 28/28 | 28/28 |
| multihop | 86 | 51/86 | 51/86 | 51/86 | 51/86 | 86/86 | 86/86 | 51/86 |
| version | 24 | 24/24 | 24/24 | 24/24 | 24/24 | 24/24 | 24/24 | 24/24 |

### All fresh questions by whether the question names an ID

| Group | n | R1@10 | R1@15 | R1@20 | R1@25 | R9 | R9x | R10 |
|---|---|---|---|---|---|---|---|---|
| False | 1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| True | 230 | 147/230 | 150/230 | 150/230 | 151/230 | 230/230 | 230/230 | 147/230 |

### Held out (seen_dev), no claim

| Group | n | R1@10 | R1@15 | R1@20 | R1@25 | R9 | R9x | R10 |
|---|---|---|---|---|---|---|---|---|
| disagree/fixed_differ | 3 | 1/3 | 1/3 | 1/3 | 1/3 | 3/3 | 3/3 | 1/3 |
| multihop/a3_kev_pick | 2 | 0/2 | 0/2 | 0/2 | 1/2 | 2/2 | 2/2 | 0/2 |
| multihop/b_intersect | 1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| version/set | 6 | 5/6 | 5/6 | 5/6 | 5/6 | 3/6 | 5/6 | 5/6 |
