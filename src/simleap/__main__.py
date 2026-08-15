"""python -m simleap ..."""

from __future__ import annotations

import argparse


def main() -> None:
    ap = argparse.ArgumentParser(prog="simleap", description="SimLeap analysis console")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_ui = sub.add_parser("ui", help="serve the local web console")
    p_ui.add_argument("--port", type=int, default=8000)
    p_ui.add_argument("--host", default="127.0.0.1")

    p_check = sub.add_parser("check", help="run the sanity checks")

    args = ap.parse_args()

    if args.cmd == "ui":
        import uvicorn

        uvicorn.run("simleap.ui.app:app", factory=False, host=args.host, port=args.port, reload=False)
    elif args.cmd == "check":
        from simleap.check import main as check_main

        check_main()


if __name__ == "__main__":
    main()
