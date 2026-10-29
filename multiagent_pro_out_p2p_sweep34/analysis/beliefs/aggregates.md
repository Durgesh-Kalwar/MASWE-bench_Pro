# Belief analysis aggregates (14 belief-enabled problems)

Belief updates accepted: 510; notes shown back in the next round: 1147/1147

## 1. Shared facts (78): {'correct_initially': 46, 'aligned_during_run': 20, 'persistent_disagreement_or_uncertainty': 1, 'stable_incorrect_agreement': 0, 'correct_then_unsupported_reversal': 11}
## 2. Exchanges (170): uptake {'already_held': 33, 'incorporated_missing': 72, 'corrected_incorrect': 25, 'not_incorporated': 27, 'adopted_incorrect_or_stale': 10, 'uncertain': 3}; action {'fits': 75, 'no_action_needed': 90, 'understood_not_implemented': 1, 'not_updated': 3, 'uncertain': 1}; sender consistent 152, inconsistent 8
## 3. Retention traces (77): {'never_received': 0, 'received_not_incorporated': 11, 'incorporated_then_contradicted_or_lost': 37, 'retained_not_implemented': 1, 'justified_update': 28}

## Matching no-belief runs (descriptive; one run per problem per arm)

| problem | topology | redundancy p2p / beliefs | answered-then-forgotten p2p / beliefs | conversations p2p / beliefs | successful access p2p / beliefs | disclosures p2p / beliefs |
|---|---|---|---|---|---|---|
| ansible__ansible-395e5e20fab9ca | star | 0.167 / 0.105 | 1/17 / 1/14 | 24 / 19 | 6 / 0 | 0 / 2 |
| ansible__ansible-3b823d908e8a5d | star | 0.368 / 0.488 | 2/15 / 5/22 | 19 / 43 | 27 / 32 | 0 / 4 |
| ansible__ansible-42355d181a11b5 | chain | 0.29 / 0.194 | 4/27 / 0/27 | 31 / 36 | 1 / 0 | 0 / 2 |
| ansible__ansible-5640093f1ca63f | star | 0.333 / 0.13 | 2/16 / 0/13 | 33 / 23 | 3 / 12 | 0 / 2 |
| ansible__ansible-949c503f2ef4b2 | mesh | 0.235 / 0.125 | 0/7 / 0/18 | 17 / 16 | 0 / 1 | 0 / 0 |
| ansible__ansible-a02e22e902a69a | star | 0.2 / 0.348 | 0/12 / 0/18 | 20 / 23 | 0 / 0 | 0 / 0 |
| ansible__ansible-a26c325bd8f6e2 | star | 0.222 / 0.208 | 1/4 / 1/12 | 9 / 24 | 0 / 0 | 0 / 0 |
| ansible__ansible-b748edea457a45 | star | 0.318 / 0.217 | 5/14 / 2/13 | 22 / 23 | 0 / 0 | 0 / 0 |
| ansible__ansible-b8025ac1601463 | star | 0.167 / 0.214 | 4/7 / 0/16 | 12 / 28 | 0 / 0 | 0 / 0 |
| ansible__ansible-cb94c0cc550df9 | star | 0.286 / 0.217 | 7/12 / 4/11 | 21 / 23 | 1 / 1 | 0 / 1 |
| ansible__ansible-d58e69c82d7edd | star | 0.222 / 0.304 | 4/5 / 2/16 | 9 / 23 | 0 / 0 | 0 / 0 |
| ansible__ansible-e40889e7112ae0 | star | 0.056 / 0.206 | 0/4 / 0/22 | 18 / 34 | 0 / 1 | 0 / 0 |
| internetarchive__openlibrary-1b | star | 0.13 / 0.344 | 1/10 / 2/15 | 23 / 32 | 12 / 9 | 1 / 2 |
| internetarchive__openlibrary-25 | mesh | 0.286 / 0.172 | 1/9 / 0/19 | 21 / 29 | 3 / 1 | 0 / 1 |

Answered then forgotten, pooled: P2P 32/159 requests (20%); beliefs 17/236 (7%).