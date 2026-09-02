# Native releases

DICOM Guide releases contain self-contained applications for Linux x86_64, macOS
Intel and Apple silicon, and Windows x86_64. The packaged applications include the
viewer and Python runtime; they do not require Node.js, Python, or a network connection
at runtime. User-facing changes are summarized in the
[release notes](RELEASE_NOTES.md).

## Verify a download

Every published archive has an adjacent `.sha256` file. A release also includes one
`SHA256SUMS` manifest and a portable Sigstore bundle named
`dicom-guide-v<version>-provenance.sigstore.json`.

Verify that the archive was built by this repository's release workflow:

```bash
python -m pip install "sigstore==4.5.0"
python -m sigstore verify github SHA256SUMS \
  --bundle dicom-guide-v<version>-provenance.sigstore.json \
  --cert-identity \
    "https://github.com/cnberry/dicom-guide/.github/workflows/release.yml@refs/heads/main" \
  --repository cnberry/dicom-guide
```

Then verify the downloaded bytes against the adjacent checksum. On macOS or Linux:

```bash
shasum -a 256 -c <downloaded-archive>.sha256
```

The verified SLSA statement authenticates the source repository, workflow, commit,
and `SHA256SUMS` digest. The manifest then authenticates all four archive digests. It
does not replace operating-system publisher signing: macOS builds remain ad-hoc
signed rather than Apple-notarized, and Windows builds are not currently
Authenticode-signed.

## Publish a release

The `Native release` workflow always builds and smoke-tests all four supported
packages. Pull requests and a manual run with no release tag produce temporary Actions
artifacts only.

To publish after the version change is merged:

1. Open **Actions → Native release → Run workflow**.
2. Select `main` and enter the exact project version prefixed with `v`, such as
   `v0.16.0`.
3. Wait for every platform build and smoke test to pass.

The release job rejects a tag that differs from `packages/agent/pyproject.toml`, an
incomplete platform set, extra files, malformed checksum sidecars, or a checksum
mismatch. It then creates the tag at the tested `main` commit, signs one provenance
statement covering the checksum manifest with GitHub Actions OIDC and public Sigstore
transparency services, verifies the bundle before upload, and publishes all assets in
one GitHub release. Pushing the exact version tag remains an equivalent automation
entry point; verify those bundles with a certificate identity ending in
`@refs/tags/v<version>` instead of `@refs/heads/main`.

Repository owners should also enable GitHub's immutable releases setting. When it is
enabled, the same draft-upload-publish flow locks the tag and assets and GitHub adds a
release-level attestation after publication.
