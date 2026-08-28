from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .catalog import build_catalog
from .comparison import suggest_pairs
from .server import serve


def _write_json(value: object, output: Path | None) -> None:
    payload = json.dumps(value, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
        try:
            temporary.write_text(payload)
            temporary.chmod(0o600)
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
    else:
        print(payload, end="")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="scanview-agent")
    commands = root.add_subparsers(dest="command", required=True)

    manifest = commands.add_parser("manifest", help="Create a PHI-minimized local DICOM catalog")
    manifest.add_argument("root", type=Path)
    manifest.add_argument("--output", "-o", type=Path)
    manifest.add_argument("--no-hashes", action="store_true", help="Skip slower source SHA-256 hashing")
    manifest.add_argument("--include-relative-paths", action="store_true")

    candidates = commands.add_parser("candidates", help="Suggest, but never approve, series pairs")
    candidates.add_argument("manifest", type=Path)
    candidates.add_argument("--output", "-o", type=Path)

    api = commands.add_parser("serve", help="Run the read-only loopback agent API")
    api.add_argument("root", type=Path)
    api.add_argument("--port", type=int, default=8765)
    api.add_argument("--token")
    api.add_argument("--no-hashes", action="store_true")
    return root


def main() -> None:
    args = parser().parse_args()
    if args.command == "manifest":
        catalog, _ = build_catalog(
            args.root,
            include_hashes=not args.no_hashes,
            include_relative_paths=args.include_relative_paths,
            progress=lambda count: print(f"Indexed {count} files…", file=sys.stderr, flush=True),
        )
        _write_json(catalog, args.output)
    elif args.command == "candidates":
        catalog = json.loads(args.manifest.read_text())
        _write_json(suggest_pairs(catalog), args.output)
    elif args.command == "serve":
        catalog, registry = build_catalog(args.root, include_hashes=not args.no_hashes)
        serve(catalog, registry, port=args.port, token=args.token)


if __name__ == "__main__":
    main()
