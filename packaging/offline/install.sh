#!/bin/sh
set -eu

bundle_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
python_command=${DICOM_GUIDE_PYTHON:-python3}
runtime_dir="$bundle_dir/.dicom-guide-runtime"

if ! command -v "$python_command" >/dev/null 2>&1; then
  echo "DICOM Guide requires Python 3.11 or newer. Set DICOM_GUIDE_PYTHON to its executable." >&2
  exit 1
fi

"$python_command" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || {
  echo "DICOM Guide requires Python 3.11 or newer." >&2
  exit 1
}

"$python_command" "$bundle_dir/verify.py" "$bundle_dir"

if [ -e "$runtime_dir" ] || [ -L "$runtime_dir" ]; then
  echo "A DICOM Guide runtime already exists in this bundle; use it or extract a fresh bundle." >&2
  exit 1
fi

umask 077
"$python_command" -m venv "$runtime_dir"
"$runtime_dir/bin/python" -m pip install \
  --no-index \
  --disable-pip-version-check \
  --no-input \
  --require-hashes \
  --find-links "$bundle_dir/wheels" \
  --requirement "$bundle_dir/requirements.lock"

"$runtime_dir/bin/python" "$bundle_dir/runtime_check.py"

echo "Launch with: sh '$bundle_dir/launch.sh' '/absolute/path/to/DICOM'"
