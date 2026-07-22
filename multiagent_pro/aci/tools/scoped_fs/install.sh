#!/usr/bin/env bash
# Put this bundle's self-contained lib on PYTHONPATH so the scoped_* bins can `import scoped`.
bundle_dir=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
export PYTHONPATH="$bundle_dir/lib":$PYTHONPATH
