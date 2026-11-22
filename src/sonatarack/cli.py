"""CLI entrypoint for SonataRack."""

from __future__ import annotations

import argparse
from pathlib import Path
import webbrowser

import uvicorn

from .app import create_app
from .storage import default_data_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sonatarack", description="Polyphonic Synthesizer & Euclidean Sequencer Studio")
    sub = parser.add_subparsers(dest="cmd", required=True)
    srv = sub.add_parser("serve", help="Run SonataRack Studio server")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=11450)
    srv.add_argument("--db", default=str(default_data_dir() / "studio.db"))
    srv.add_argument("--open", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd == "serve":
        if args.open:
            webbrowser.open(f"http://{args.host}:{args.port}")
        app = create_app(db_path=Path(args.db))
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
