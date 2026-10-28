# 33 instances, 177 agents, 667 messages, 141 interfaces

## Volume by round (all instances)
| round | messages | directed | interfaces | comm-only steps | edit steps | test steps | other steps | submit-only steps |
|---|---|---|---|---|---|---|---|---|
| 1 | 184 | 90 | 72 | 296 | 196 | 32 | 321 | 99 |
| 2 | 109 | 55 | 53 | 79 | 106 | 92 | 83 | 164 |
| 3 | 77 | 63 | 5 | 45 | 40 | 113 | 47 | 171 |
| 4 | 82 | 57 | 6 | 53 | 24 | 74 | 33 | 177 |
| 5 | 66 | 48 | 0 | 45 | 13 | 79 | 28 | 176 |
| 6 | 39 | 30 | 0 | 29 | 17 | 41 | 16 | 179 |
| 7 | 32 | 19 | 1 | 26 | 8 | 22 | 16 | 178 |
| 8 | 34 | 24 | 3 | 30 | 7 | 18 | 10 | 176 |
| 9 | 23 | 19 | 1 | 18 | 2 | 17 | 8 | 177 |
| 10 | 21 | 14 | 0 | 14 | 1 | 13 | 7 | 177 |

50% of all messages sent by end of round 3; 90% by end of round 8.

## Length: median 353 chars, p90 599, max 1721; total 256,563 chars (~64,140 tokens)

## Content mix (share of messages carrying each tag; a message can carry several)
- interface_announce: 32%
- request: 54%
- confirm_ack: 36%
- status_done: 9%
- test_report: 6%
- correction: 9%
- problem_scope: 7%
- upstream_recall: 9%
- plan_assignment: 13%
- no tag at all: 15%

## Novelty
- messages containing at least one code identifier: 97%
- of those, messages whose identifiers were ALL already on the board (restatement): 60%
- messages with no code identifier (pure coordination/ack): 3%

## Per instance
| instance | agents | msgs | msgs/agent | interfaces | chars | resolved |
|---|---|---|---|---|---|---|
| ansible__ansible-395e5e20fab9ca | 3 | 21 | 7.0 | 3 | 7,507 | True |
| ansible__ansible-3b823d908e8a5d | 6 | 18 | 3.0 | 1 | 6,823 | True |
| ansible__ansible-42355d181a11b5 | 5 | 28 | 5.6 | 3 | 12,409 | False |
| ansible__ansible-5640093f1ca63f | 4 | 31 | 7.8 | 2 | 13,882 | True |
| ansible__ansible-8127abbc298cab | 6 | 13 | 2.2 | 4 | 5,005 | True |
| ansible__ansible-949c503f2ef4b2 | 4 | 15 | 3.8 | 2 | 7,058 | True |
| ansible__ansible-a02e22e902a69a | 4 | 15 | 3.8 | 5 | 5,665 | True |
| ansible__ansible-a26c325bd8f6e2 | 4 | 6 | 1.5 | 3 | 1,087 | True |
| ansible__ansible-b748edea457a45 | 4 | 21 | 5.2 | 1 | 10,079 | True |
| ansible__ansible-b8025ac1601463 | 4 | 9 | 2.2 | 3 | 2,307 | True |
| ansible__ansible-cb94c0cc550df9 | 4 | 18 | 4.5 | 3 | 4,877 | True |
| ansible__ansible-d58e69c82d7edd | 3 | 6 | 2.0 | 3 | 1,460 | True |
| ansible__ansible-e40889e7112ae0 | 4 | 10 | 2.5 | 8 | 4,233 | True |
| internetarchive__openlibrary-1b | 4 | 14 | 3.5 | 9 | 6,400 | True |
| internetarchive__openlibrary-25 | 4 | 12 | 3.0 | 9 | 4,506 | True |
| internetarchive__openlibrary-30 | 6 | 41 | 6.8 | 3 | 25,160 | True |
| internetarchive__openlibrary-4b | 8 | 32 | 4.0 | 4 | 12,663 | False |
| internetarchive__openlibrary-63 | 6 | 23 | 3.8 | 8 | 8,634 | False |
| internetarchive__openlibrary-6f | 6 | 19 | 3.2 | 12 | 7,611 | True |
| internetarchive__openlibrary-72 | 4 | 13 | 3.2 | 1 | 3,882 | True |
| internetarchive__openlibrary-77 | 7 | 12 | 1.7 | 4 | 4,968 | True |
| internetarchive__openlibrary-7b | 8 | 26 | 3.2 | 6 | 8,502 | False |
| internetarchive__openlibrary-7f | 13 | 42 | 3.2 | 6 | 16,044 | True |
| internetarchive__openlibrary-b1 | 5 | 18 | 3.6 | 5 | 5,933 | True |
| internetarchive__openlibrary-c5 | 11 | 34 | 3.1 | 4 | 9,315 | True |
| internetarchive__openlibrary-d1 | 9 | 32 | 3.6 | 9 | 12,429 | True |
| internetarchive__openlibrary-d4 | 3 | 9 | 3.0 | 6 | 2,464 | True |
| qutebrowser__qutebrowser-0d2afd | 4 | 12 | 3.0 | 1 | 3,571 | True |
| qutebrowser__qutebrowser-1943fa | 5 | 44 | 8.8 | 2 | 13,350 | True |
| qutebrowser__qutebrowser-46e683 | 5 | 10 | 2.0 | 1 | 3,120 | True |
| qutebrowser__qutebrowser-a84ecf | 4 | 15 | 3.8 | 4 | 4,496 | True |
| qutebrowser__qutebrowser-e5340c | 7 | 31 | 4.4 | 5 | 10,011 | True |
| qutebrowser__qutebrowser-e57b6e | 3 | 17 | 5.7 | 1 | 11,112 | True |
