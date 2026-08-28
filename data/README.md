# Patient data boundary

No DICOM, manifests derived from patient DICOM, registrations, measurements,
key-image or visit-packet ZIPs/PNGs/sidecars, or screenshots belong in this
repository. Keep original scans in the separately managed local data directory and
treat generated catalogs and derivatives as sensitive medical information.

Only synthetic fixtures may be committed, and tests currently generate them at
runtime in temporary directories.
