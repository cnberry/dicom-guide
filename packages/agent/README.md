# DICOM Guide local service

The Python package indexes a local DICOM folder, serves the DICOM Guide UI and protected
source instances on loopback, and validates viewer-control commands.

Normal users install a self-contained release from the repository root. For an
editable contributor install, build the web UI and install `packages/agent[test]`
with your preferred Python environment manager.

The browser URL needs no login. Installed agent commands discover an owner-only local
session credential automatically. DICOM bytes are read-only and stay local.

For the supported API, see [`docs/AGENT-API.md`](../../docs/AGENT-API.md). The CLI
also contains experimental evidence, comparison, segmentation, and registration
commands; inspect `dicom-guide --help` before using them.
