# ScanView Agent

The Python package indexes a local DICOM folder, serves the ScanView UI and protected
source instances on loopback, and validates viewer-control commands.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e 'packages/agent[test]'
pnpm build
.venv/bin/scanview-agent launch '/path/to/DICOM-folder'
```

The browser URL needs no login. Agent endpoints require the bearer token printed by
the launcher. DICOM bytes are read-only and stay local.

For the supported API, see [`docs/AGENT-API.md`](../../docs/AGENT-API.md). The CLI
also contains experimental evidence, comparison, segmentation, and registration
commands; inspect `scanview-agent --help` before using them.
