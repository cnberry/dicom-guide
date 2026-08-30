DICOM Guide @VERSION@

Install into the standard /usr/local prefix:

    sh install.sh

If /usr/local is not writable, the installer will ask you to rerun that command
with sudo. Set DICOM_GUIDE_PREFIX only when managing a different system prefix.

Then open a local DICOM folder:

    dicom-guide open '/path/to/DICOM-folder'

The folder can be the top level copied from an imaging disc or portal download.
DICOM Guide searches nested folders; filenames do not need .dcm extensions.

All DICOM parsing and display remain on this computer. No Python, Node.js,
account, or external processing API is required by this packaged application.

macOS: this build is ad-hoc signed but not Apple-notarized. If Gatekeeper blocks the
first launch, approve DICOM Guide with Open Anyway in Privacy & Security settings.
