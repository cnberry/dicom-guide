# Release notes

## DICOM Guide 0.16.0

DICOM Guide 0.16.0 makes changing local studies safer and more predictable, keeps
agent control responsive when the viewer is in the background, and carries the
project identity into the viewer itself.

### Highlights

- Change scan folders through the local service without browser upload warnings or
  browser-side study copies. The existing study stays usable while the replacement is
  indexed, and the folder control shows a clear waiting state.
- Keep the selected folder after refresh and restore 3-plane mode when the newly
  selected series supports multiplanar reconstruction.
- Tear down old rendering state before a source swap, preventing the crashes seen
  during repeated folder changes.
- Keep viewer control connected in background tabs using local long polling instead
  of relying on throttled browser timers.
- Improve first-run installation with a reversible per-user fallback when
  `/usr/local` is not writable, and provide correct patient-space geometry for
  eligible 3-plane views.
- Use the DICOM Guide thumbnail as both the website icon and the compact viewer
  toolbar icon.

### Privacy and compatibility

Folder selection, indexing, DICOM decoding, and rendering remain local. Source DICOM
files remain read-only, and the packaged viewer does not send scan paths, metadata,
or pixels to an external service. This release provides self-contained packages for
macOS Apple silicon, macOS Intel, Linux x86_64, and Windows x86_64.
