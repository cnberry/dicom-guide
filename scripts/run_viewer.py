#!/usr/bin/env python3
"""Serve a built DICOM Guide bundle on loopback without any external service."""

from __future__ import annotations

import argparse
import mimetypes
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class LocalOnlyHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        print(f"dicom-guide-ui {self.command} {self.path.split('?', 1)[0]}")

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    dist = Path(__file__).resolve().parents[1] / "apps" / "viewer" / "dist"
    if not (dist / "index.html").is_file():
        parser.error("viewer bundle is missing; run `pnpm build` first")

    mimetypes.add_type("application/wasm", ".wasm")
    handler = partial(LocalOnlyHandler, directory=dist)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"DICOM Guide local UI: {url}")
    print("No external API is used. Press Ctrl-C to stop.")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
