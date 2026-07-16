from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import html
import importlib.util
import http.server
import json
import os
import secrets
import socket
import sqlite3
import sys
import time
import urllib.parse
import webbrowser
from http import cookies
from pathlib import Path


def bundled_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def load_report_server(root: Path):
    module_path = root / "report_server.py"
    spec = importlib.util.spec_from_file_location("packaged_report_server", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def first_free_port(start: int) -> int:
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"no free localhost port in {start}-{start + 99}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    root = bundled_root()
    report_server = load_report_server(root)
    port = first_free_port(args.port)
    report_server.PORT = port

    server = report_server.ThreadingHTTPServer(("127.0.0.1", port), report_server.ReportHandler)
    url = f"http://127.0.0.1:{port}/viewer.html"
    print(f"Serving GPIC interactive report from {root}")
    print(url)
    print("Close this window to stop the report server.")
    if not args.no_browser:
        webbrowser.open(url)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
