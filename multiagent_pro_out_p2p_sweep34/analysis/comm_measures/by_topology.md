# Six measures by topology

Pooled over runs (numerators and denominators summed). Topology labels are the primary label; uncertain labels are counted under their primary label and listed in summary.csv.

## all (48 runs)

| topology | runs | conversations | directedness | relevance | coverage | redundancy | response fulfillment | messages to resolution |
|---|---|---|---|---|---|---|---|---|
| star | 30 | 676 | 0.649 (439/676) | 0.772 (522/676) | 1.0 (67/67) | 0.251 (170/676; harness 152, agent 18; partly 142) | 0.975 (356/365; partly 5, incorrect 1, unanswered 3) | median of run medians 0; links: 62 initially settled, 3 via communication, 2 unresolved, 0 uncertain |
| chain | 4 | 103 | 0.67 (69/103) | 0.854 (88/103) | 0.917 (11/12) | 0.282 (29/103; harness 28, agent 1; partly 24) | 0.924 (73/79; partly 4, incorrect 1, unanswered 1) | median of run medians 0.0; links: 10 initially settled, 2 via communication, 0 unresolved, 0 uncertain |
| tree | 2 | 84 | 0.655 (55/84) | 0.893 (75/84) | 1.0 (12/12) | 0.476 (40/84; harness 35, agent 5; partly 8) | 1.0 (60/60; partly 0, incorrect 0, unanswered 0) | median of run medians 0.0; links: 11 initially settled, 1 via communication, 0 unresolved, 0 uncertain |
| mesh | 9 | 274 | 0.803 (220/274) | 0.88 (241/274) | 1.0 (63/63) | 0.252 (69/274; harness 61, agent 8; partly 51) | 0.96 (169/176; partly 3, incorrect 3, unanswered 1) | median of run medians 0; links: 40 initially settled, 22 via communication, 1 unresolved, 0 uncertain |
| disconnected | 3 | 68 | 0.588 (40/68) | 0.676 (46/68) | 0.778 (7/9) | 0.221 (15/68; harness 8, agent 7; partly 16) | 0.95 (19/20; partly 1, incorrect 0, unanswered 0) | median of run medians 0.0; links: 8 initially settled, 1 via communication, 0 unresolved, 0 uncertain |
| **overall** | 48 | 1205 | 0.683 (823/1205) | 0.807 (972/1205) | 0.982 (160/163) | 0.268 (323/1205; harness 284, agent 39; partly 241) | 0.967 (677/700; partly 13, incorrect 5, unanswered 5) | median of run medians 0; links: 131 initially settled, 29 via communication, 3 unresolved, 0 uncertain |

## p2p (33 runs)

| topology | runs | conversations | directedness | relevance | coverage | redundancy | response fulfillment | messages to resolution |
|---|---|---|---|---|---|---|---|---|
| star | 18 | 360 | 0.628 (226/360) | 0.728 (262/360) | 1.0 (41/41) | 0.239 (86/360; harness 75, agent 11; partly 82) | 0.978 (180/184; partly 2, incorrect 0, unanswered 2) | median of run medians 0.0; links: 38 initially settled, 1 via communication, 2 unresolved, 0 uncertain |
| chain | 3 | 67 | 0.642 (43/67) | 0.791 (53/67) | 0.889 (8/9) | 0.328 (22/67; harness 21, agent 1; partly 15) | 0.942 (49/52; partly 2, incorrect 0, unanswered 1) | median of run medians 0; links: 7 initially settled, 2 via communication, 0 unresolved, 0 uncertain |
| tree | 2 | 84 | 0.655 (55/84) | 0.893 (75/84) | 1.0 (12/12) | 0.476 (40/84; harness 35, agent 5; partly 8) | 1.0 (60/60; partly 0, incorrect 0, unanswered 0) | median of run medians 0.0; links: 11 initially settled, 1 via communication, 0 unresolved, 0 uncertain |
| mesh | 7 | 229 | 0.777 (178/229) | 0.865 (198/229) | 1.0 (55/55) | 0.271 (62/229; harness 55, agent 7; partly 42) | 0.957 (134/140; partly 3, incorrect 3, unanswered 0) | median of run medians 0; links: 36 initially settled, 18 via communication, 1 unresolved, 0 uncertain |
| disconnected | 3 | 68 | 0.588 (40/68) | 0.676 (46/68) | 0.778 (7/9) | 0.221 (15/68; harness 8, agent 7; partly 16) | 0.95 (19/20; partly 1, incorrect 0, unanswered 0) | median of run medians 0.0; links: 8 initially settled, 1 via communication, 0 unresolved, 0 uncertain |
| **overall** | 33 | 808 | 0.671 (542/808) | 0.785 (634/808) | 0.976 (123/126) | 0.278 (225/808; harness 194, agent 31; partly 163) | 0.969 (442/456; partly 8, incorrect 3, unanswered 3) | median of run medians 0.0; links: 100 initially settled, 23 via communication, 3 unresolved, 0 uncertain |

## p2p_beliefs (14 runs)

| topology | runs | conversations | directedness | relevance | coverage | redundancy | response fulfillment | messages to resolution |
|---|---|---|---|---|---|---|---|---|
| star | 11 | 295 | 0.654 (193/295) | 0.81 (239/295) | 1.0 (24/24) | 0.271 (80/295; harness 73, agent 7; partly 55) | 0.976 (163/167; partly 3, incorrect 0, unanswered 1) | median of run medians 0; links: 22 initially settled, 2 via communication, 0 unresolved, 0 uncertain |
| chain | 1 | 36 | 0.722 (26/36) | 0.972 (35/36) | 1.0 (3/3) | 0.194 (7/36; harness 7, agent 0; partly 9) | 0.889 (24/27; partly 2, incorrect 1, unanswered 0) | median of run medians 0; links: 3 initially settled, 0 via communication, 0 unresolved, 0 uncertain |
| mesh | 2 | 45 | 0.933 (42/45) | 0.956 (43/45) | 1.0 (8/8) | 0.156 (7/45; harness 6, agent 1; partly 9) | 0.972 (35/36; partly 0, incorrect 0, unanswered 1) | median of run medians 0.5; links: 4 initially settled, 4 via communication, 0 unresolved, 0 uncertain |
| **overall** | 14 | 376 | 0.694 (261/376) | 0.843 (317/376) | 1.0 (35/35) | 0.25 (94/376; harness 86, agent 8; partly 73) | 0.965 (222/230; partly 5, incorrect 1, unanswered 2) | median of run medians 0.0; links: 29 initially settled, 6 via communication, 0 unresolved, 0 uncertain |

## p2p_nointerface (1 runs)

| topology | runs | conversations | directedness | relevance | coverage | redundancy | response fulfillment | messages to resolution |
|---|---|---|---|---|---|---|---|---|
| star | 1 | 21 | 0.952 (20/21) | 1.0 (21/21) | 1.0 (2/2) | 0.19 (4/21; harness 4, agent 0; partly 5) | 0.929 (13/14; partly 0, incorrect 1, unanswered 0) | median of run medians 0.0; links: 2 initially settled, 0 via communication, 0 unresolved, 0 uncertain |
| **overall** | 1 | 21 | 0.952 (20/21) | 1.0 (21/21) | 1.0 (2/2) | 0.19 (4/21; harness 4, agent 0; partly 5) | 0.929 (13/14; partly 0, incorrect 1, unanswered 0) | median of run medians 0.0; links: 2 initially settled, 0 via communication, 0 unresolved, 0 uncertain |
