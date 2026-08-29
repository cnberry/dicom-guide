# ScanView offline runtime bundle

This bundle runs the ScanView DICOM viewer and local agent interface on macOS or
Linux without a runtime network connection or external DICOM-processing API.

Requirements:

- Python 3.11 or newer (`python3` by default)
- a current local browser
- enough local disk space for a private Python virtual environment

From this extracted directory:

```sh
python3 verify.py
sh install.sh
sh launch.sh '/absolute/path/to/DICOM'
sh launch.sh '/absolute/path/to/DICOM' --lesion-volume-comparison \
  '/absolute/path/to/reviewed-volume-comparison.zip'
```

Set `SCANVIEW_PYTHON=/absolute/path/to/python3` when the required interpreter is
not named `python3`. Installation uses only the included wheels with `--no-index`
and `--require-hashes`. Every launch rechecks the installed versions, embedded UI,
all 24 schemas, consultation contracts, manual ROI review/comparison, and native-
boundary display support before indexing DICOM. Launch binds the application
to loopback; DICOM bytes stay on the computer. There is no cloud fallback: missing
local capability fails closed rather than sending source or derived data elsewhere.
Keep this directory and its
`.scanview-runtime` private because local browser sessions and generated evidence may
be sensitive.

`bundle.json` and `verify.py` detect payload corruption or changes after the bundle
was built. They are not a publisher signature, code-signing identity, medical-record
authentication, or clinical validation. Obtain release bundles through a trusted
channel; signed and notarized platform distributions remain future work.
