# Coordination metrics: 2 instances

| instance | n_agents | resolved | cost | messages | directed | dup_rate | contact_recall | directed_precision | iface_checks | iface_agreement | publish_coverage | requests | answered_rate | mean_latency_rounds | mean_first_submit | settled_rate | idle_share | delivered_rate | retained_next_round | uptake_rate | coord_score |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ansible__ansible-395e5e20fab9ca | 3 | True | 4.74 | 23 | 16 | 0.00 | 1.00 | 0.75 | 0 | - | 0.00 | 7 | 1.00 | 1.43 | 1.70 | 0.67 | 0.03 | 1.00 | 0.00 | 0.86 | 91 |
| internetarchive__openlibrary-1b | 4 | True | 9.11 | 28 | 6 | 0.00 | 1.00 | 1.00 | 4 | 1.00 | 0.75 | 7 | 1.00 | 1.00 | 2.00 | 0.00 | 0.10 | 1.00 | 0.01 | 0.54 | 76 |
| **mean** | 3.50 | 2/2 | 6.92 | 25.50 | 11.00 | 0.00 | 1.00 | 0.88 | 2.00 | 1.00 | 0.38 | 7.00 | 1.00 | 1.21 | 1.85 | 0.34 | 0.07 | 1.00 | 0.01 | 0.70 | 83.50 |

## Interface mismatches (consumer call vs definer's final signature)


## Published-vs-final signature drift


## Realized dependency edges (consumer -> definer: names)

- ansible__ansible-395e5e20fab9ca: agent_2->agent_1: IteratingStates, FailedStates, <import ansible.executor.play_iterator>; agent_3->agent_1: IteratingStates, FailedStates, <import ansible.executor.play_iterator>
- internetarchive__openlibrary-1b: agent_2->agent_3: expand_record, threshold_match, <import openlibrary.catalog.merge.merge_marc>; agent_3->agent_2: threshold_match; agent_3->agent_4: build_titles

## Convergence per agent (first_submit / last_edit / post-submit edit rounds / idle rounds)

- ansible__ansible-395e5e20fab9ca: agent_1 2/2/[]/0; agent_2 1/6/[6]/0; agent_3 2/1/[]/1
- internetarchive__openlibrary-1b: agent_1 2/4/[3, 4]/1; agent_2 1/8/[2, 3, 4, 5, 6, 8]/0; agent_3 2/8/[4, 8]/1; agent_4 3/9/[9]/2