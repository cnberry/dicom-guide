# ScanView Agent

Source-read-only catalog, compatibility scoring, and loopback API for local DICOM
studies.
It excludes direct patient-name/ID tags from its output by design, but its manifests
remain sensitive medical information and are **not de-identified**.

```bash
python -m pip install -e '.[test]'
scanview-agent manifest '/path/to/copied/DICOM' --output manifest.json
scanview-agent candidates manifest.json
scanview-agent serve '/path/to/copied/DICOM'
scanview-agent launch '/path/to/copied/DICOM'
scanview-agent validate-measurements '/path/to/scanview-measurements.json'
scanview-agent validate-key-image '/path/to/scanview-key-image.zip'
scanview-agent assemble-visit-packet baseline-key-image.zip followup-key-image.zip \
  --output scanview-visit-packet.zip
scanview-agent validate-visit-packet scanview-visit-packet.zip
scanview-agent compare-measurements baseline.json followup.json \
  --baseline-id 'bidirectional:baseline-id' \
  --followup-id 'bidirectional:followup-id' \
  --lesion-label 'Target lesion A' \
  --output comparison.json
scanview-agent validate-comparison comparison.json
```

Use `scripts/build_release.py` from the repository root to produce a self-contained
wheel with the built UI under `scanview_agent/ui`. A regular agent-only wheel stays
lightweight. `launch` serves an embedded or explicitly supplied `--ui-dist` bundle
and the API from one loopback origin. It establishes an
HttpOnly browser session, while agents continue to use the printed bearer token.
The server has no source-write or delete endpoint. The unified viewer's one local
POST accepts only the two derived key-image bundles, assembles and revalidates the
visit packet in memory, returns it with `no-store`, and creates no server-side
patient file. Measurement validation returns only validity, schema,
review state, count, and errors; it does not echo source identifiers, coordinates,
or values. Comparison requires explicit tracking IDs from distinct source series and
trusted millimeter results. It emits source-linked numeric change, missing context,
and clinician questions with an empty interpretation list and `unreviewed` state.
An optional working lesion label is normalized and bounded but never treated as proof
of lesion identity. Comparison validation omits that label, IDs, coordinates, and
numeric values from its privacy-minimized summary.
Visit-packet assembly also stays local. It accepts only validated key-image v2
archives with one matching opaque patient context, distinct dated studies/series,
explicit ordering, and one modality. It creates a static review page plus an
integrity-linked agent manifest and does not perform lesion matching, registration,
response scoring, or interpretation.
