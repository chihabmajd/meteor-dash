"""Entry point:  python -m meteordash [--config PATH] [--check]"""
import argparse
import json
import sys

from . import config as cfgmod
from .server import serve, snapshot


def main(argv=None):
    ap = argparse.ArgumentParser(prog="meteordash",
                                 description="laptop telemetry + health HUD")
    ap.add_argument("--config", help="path to config.toml (else auto-discovered)")
    ap.add_argument("--check", action="store_true",
                    help="print a one-shot JSON snapshot and exit (no server)")
    ap.add_argument("--port", type=int, help="override server port")
    args = ap.parse_args(argv)

    cfg = cfgmod.load(args.config)
    if args.port:
        cfg["server"]["port"] = args.port

    if args.check:
        json.dump(snapshot(cfg), sys.stdout, indent=2, default=str)
        print()
        return 0

    try:
        serve(cfg)
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# modules/__init__ marker is created alongside; see modules/__init__.py
