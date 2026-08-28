# ScanView Agent

Read-only catalog, compatibility scoring, and loopback API for local DICOM studies.
It excludes direct patient-name/ID tags from its output by design, but its manifests
remain sensitive medical information and are **not de-identified**.

```bash
python -m pip install -e '.[test]'
scanview-agent manifest '/path/to/copied/DICOM' --output manifest.json
scanview-agent candidates manifest.json
scanview-agent serve '/path/to/copied/DICOM'
```

The server prints a random bearer token and only binds to `127.0.0.1`. It has no
write or delete endpoint.
