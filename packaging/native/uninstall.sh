#!/bin/sh
set -eu

version='@VERSION@'
if [ "${DICOM_GUIDE_PREFIX+x}" = x ]; then
  prefix=$DICOM_GUIDE_PREFIX
elif [ -L "$HOME/.local/bin/dicom-guide" ] && [ -d "$HOME/.local/lib/dicom-guide/$version" ]; then
  prefix="$HOME/.local"
elif [ -L /usr/local/bin/dicom-guide ] && [ -d "/usr/local/lib/dicom-guide/$version" ]; then
  prefix=/usr/local
else
  prefix="$HOME/.local"
fi
install_dir="$prefix/lib/dicom-guide/$version"
command_path="$prefix/bin/dicom-guide"

permission_root=$prefix
while [ ! -e "$permission_root" ]; do
  permission_root=$(dirname "$permission_root")
done
if [ ! -w "$permission_root" ]; then
  echo "Removing DICOM Guide from $prefix requires administrator permission." >&2
  echo "Run: sudo sh '$0'" >&2
  exit 1
fi

if [ -L "$command_path" ] && [ "$(readlink "$command_path")" = "$install_dir/dicom-guide" ]; then
  rm "$command_path"
fi
if [ -d "$install_dir" ]; then
  rm -r "$install_dir"
  echo "Removed DICOM Guide $version from $prefix"
else
  echo "DICOM Guide $version is not installed at $install_dir"
fi
