#!/usr/bin/env python
"""Run the UNMODIFIED Pro evaluator on Modal, shimming the removed Sandbox FS API.

`swe_bench_pro_eval.py` reads and writes files inside a Modal Sandbox with the legacy
`sandbox.open(path, mode)` handle API. Modal deprecated that on 2026-03-09 and has since
removed it SERVER-side, so every Modal evaluation now dies with:

    ConflictError('The legacy Sandbox filesystem API is no longer supported.
                   See https://modal.com/docs/guide/migrate-sandbox-filesystem ...')

Because the removal is server-side, pinning an older `modal` client does not help. The
replacement is the path-oriented `sandbox.filesystem.read_text/write_text` API, where each
call is one complete operation instead of a stateful handle.

This module restores `Sandbox.open` as a thin file-like wrapper over the new API, then calls
the evaluator's own `main()`. The evaluator is imported, never edited: the entryscript it
builds, the container it starts, and above all its scoring rule (an instance passes only if
`fail_to_pass | pass_to_pass` is a subset of the tests that PASSED) are used verbatim, so a
verdict from here is the same verdict the harness would give with a working Modal.

Usage (identical flags to swe_bench_pro_eval.py, minus --use_local_docker):

    python multiagent_pro/metrics/run_eval_modal.py \
        --raw_sample_path sampled_pro/raw_sample.jsonl \
        --patch_path multiagent_pro_out/prune_check/patches.json \
        --output_dir multiagent_pro_out/prune_check/eval_out \
        --scripts_dir run_scripts --num_workers 4 --dockerhub_username jefzda
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))


class _ShimFile:
    """Minimal file-like object over `sandbox.filesystem`.

    Only the surface the evaluator actually uses is implemented — `read()`, `write()` and
    the context-manager protocol. Writes are buffered and flushed once on close, because the
    new API takes the whole payload in a single call; reads fetch the whole file up front.
    """

    def __init__(self, sandbox, path, mode):
        self._fs = sandbox.filesystem
        self._path = path
        self._mode = mode
        self._buf = []
        self._data = None
        if "r" in mode:
            self._data = (self._fs.read_bytes(path) if "b" in mode
                          else self._fs.read_text(path))

    def read(self, *_):
        return self._data

    def write(self, data):
        self._buf.append(data)
        return len(data)

    def close(self):
        if "w" in self._mode and self._buf:
            if "b" in self._mode:
                self._fs.write_bytes(b"".join(self._buf), self._path)
            else:
                self._fs.write_text("".join(self._buf), self._path)
            self._buf = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def install_shim():
    """Re-attach `Sandbox.open` using the supported filesystem API. No-op if Modal still
    provides a working `open` (so this keeps working if Modal ever restores it)."""
    import modal
    sandbox_cls = modal.Sandbox

    def _open(self, path, mode="r"):
        return _ShimFile(self, path, mode)

    sandbox_cls.open = _open
    return sandbox_cls


def main():
    install_shim()
    import swe_bench_pro_eval          # imported AFTER the shim so its calls hit the wrapper
    swe_bench_pro_eval.main()


if __name__ == "__main__":
    main()
