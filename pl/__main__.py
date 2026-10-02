"""One entry point: `python -m pl <command> [args]`. Each command is a module's
`main(argv)`; the per-module `python -m pl.<module>` forms keep working."""
from __future__ import annotations

import sys
from importlib import import_module

COMMANDS = {
    "pull": ("pl.pull", "ESPN history -> data/pl.sqlite"),
    "backtest": ("pl.backtest", "walk-forward evaluation -> docs/RESULTS.md"),
    "paper": ("pl.paper", "tickets | settle | status | snapshot | clv"),
    "evidence": ("pl.evidence", "run | replay <file>: RI verdict -> docs/VERDICT.md"),
    "lag": ("pl.lag_test", "venue lead-lag test -> docs/<VENUE>_LAG.md"),
    "kalshi-hist": ("pl.kalshi_hist", "Kalshi settled markets + candles -> data/kalshi_hist.sqlite"),
    "poly-hist": ("pl.poly_hist", "Polymarket closed markets + prices -> data/poly_hist.sqlite"),
    "sources": ("pl.sources", "raw pulls with sha256 manifest; --doc renders docs/SOURCES.md"),
    "probe": ("pl.probe", "sources | kalshi: reachability probes"),
}


def usage() -> str:
    width = max(map(len, COMMANDS))
    return "usage: python -m pl <command> [args]\n\n" + "\n".join(f"  {k:<{width}}  {d}" for k, (_, d) in COMMANDS.items()) + "\n"


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(usage(), end="")
        return
    cmd, rest = argv[0], argv[1:]
    if cmd not in COMMANDS:
        sys.exit(f"unknown command {cmd!r}\n\n{usage()}")
    mod = import_module(COMMANDS[cmd][0])
    entry = getattr(mod, "cli", None) or mod.main
    entry(rest)


if __name__ == "__main__":
    main()
