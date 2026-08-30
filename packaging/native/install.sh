#!/bin/sh
set -eu

bundle_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
version='@VERSION@'
if [ "${DICOM_GUIDE_PREFIX+x}" = x ]; then
  prefix=$DICOM_GUIDE_PREFIX
elif [ -w /usr/local ] || { [ ! -e /usr/local ] && [ -w /usr ]; }; then
  prefix=/usr/local
else
  prefix="$HOME/.local"
  echo "Administrator access is unavailable; installing for this user instead."
fi
install_dir="$prefix/lib/dicom-guide/$version"
command_path="$prefix/bin/dicom-guide"

permission_root=$prefix
while [ ! -e "$permission_root" ]; do
  permission_root=$(dirname "$permission_root")
done
if [ ! -w "$permission_root" ]; then
  echo "Installing into $prefix requires administrator permission." >&2
  echo "Run: sudo sh '$bundle_dir/install.sh'" >&2
  exit 1
fi

if [ -e "$install_dir" ]; then
  echo "DICOM Guide $version is already installed at $install_dir" >&2
  exit 1
fi

mkdir -p "$prefix/lib/dicom-guide" "$prefix/bin"
cp -R "$bundle_dir/app" "$install_dir"
ln -sfn "$install_dir/dicom-guide" "$command_path"

echo "Installed DICOM Guide $version"
echo "Command: $command_path"
case ":${PATH:-}:" in
  *:"$prefix/bin":*) command_name=dicom-guide ;;
  *)
    command_name=$command_path
    echo "Tip: add $prefix/bin to PATH to run 'dicom-guide' from any terminal."
    ;;
esac
echo "Run: $command_name open '/path/to/DICOM-folder'"
