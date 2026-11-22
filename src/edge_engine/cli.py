"""Command line: `edge-engine list | play <module> | stats`."""

from __future__ import annotations

import argparse
import time
from collections.abc import Sequence
from pathlib import Path

from .loop import run_session
from .modules import REGISTRY, get_module
from .storage import DEFAULT_DB, Store
from .terminal import TerminalUI


def _cmd_list(args: argparse.Namespace) -> int:
    for name, cls in sorted(REGISTRY.items()):
        print(f"{name:12} {cls.title}")
    return 0


def _cmd_play(args: argparse.Namespace) -> int:
    module = get_module(args.module)
    seed = args.seed if args.seed is not None else time.time_ns() % (1 << 32)
    config = {}
    if args.rounds is not None:
        config["rounds"] = args.rounds
    ui = TerminalUI()
    print(f"{module.title}  (seed {seed}; replay with --seed {seed})")
    store = None if args.no_log else Store(args.db)
    try:
        res = run_session(
            module, seed, ask=ui.ask, config=config, reveal=ui.reveal, show=ui.show, store=store
        )
    finally:
        if store is not None:
            store.close()
    n = len(res.turns)
    status = "finished" if res.completed else "stopped early"
    print(f"\nSession {status}: {n} answers, {res.points:.2f} points out of {n}.")
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    if not Path(args.db).exists():
        print("No history yet.")
        return 0
    with Store(args.db) as store:
        rows = store.category_stats(args.module)
    if not rows:
        print("No answers logged yet.")
        return 0
    print(f"{'module':10} {'category':18} {'n':>5} {'correct':>8} {'points':>7} {'avg s':>7}")
    for r in rows:
        acc = "-" if r.accuracy is None else f"{r.accuracy:.0%}"
        print(
            f"{r.module:10} {r.category:18} {r.n:5d} {acc:>8} "
            f"{r.mean_points:7.2f} {r.mean_seconds:7.1f}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="edge-engine", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list the modules").set_defaults(func=_cmd_list)

    play = sub.add_parser("play", help="play a module")
    play.add_argument("module", choices=sorted(REGISTRY))
    play.add_argument("--seed", type=int, help="seed for a replayable session")
    play.add_argument("--rounds", type=int, help="number of rounds")
    play.add_argument("--db", default=DEFAULT_DB, help=f"history file (default {DEFAULT_DB})")
    play.add_argument("--no-log", action="store_true", help="do not save answers")
    play.set_defaults(func=_cmd_play)

    stats = sub.add_parser("stats", help="per-category stats, slowest first")
    stats.add_argument("--module", help="only this module")
    stats.add_argument("--db", default=DEFAULT_DB, help=f"history file (default {DEFAULT_DB})")
    stats.set_defaults(func=_cmd_stats)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
