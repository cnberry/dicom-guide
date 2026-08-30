#!/bin/sh
set -eu

bundle_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
runtime_dir="$bundle_dir/.dicom-guide-runtime"
agent="$runtime_dir/bin/dicom-guide"
python_command=${DICOM_GUIDE_PYTHON:-python3}

if [ "$#" -lt 1 ]; then
  echo "usage: sh launch.sh DICOM_ROOT [DICOM_GUIDE_LAUNCH_OPTIONS]" >&2
  exit 2
fi
if [ -L "$runtime_dir" ] || [ ! -x "$agent" ]; then
  echo "DICOM Guide is not installed in this bundle. Run: sh install.sh" >&2
  exit 1
fi
if ! command -v "$python_command" >/dev/null 2>&1; then
  echo "The Python used to verify this bundle is unavailable." >&2
  exit 1
fi

"$python_command" "$bundle_dir/verify.py" "$bundle_dir"
"$runtime_dir/bin/python" "$bundle_dir/runtime_check.py"
exec "$agent" open "$@"
