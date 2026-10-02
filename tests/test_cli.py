from __future__ import annotations

import subprocess
import sys

import pytest

from pl import __main__ as cli
from pl.core import ROOT


def test_usage_lists_every_command(capsys):
    cli.main([])
    out = capsys.readouterr().out
    assert all(k in out for k in cli.COMMANDS)


def test_unknown_command_exits():
    with pytest.raises(SystemExit, match="unknown command"):
        cli.main(["nope"])


def test_dispatch_passes_argv_to_module_main(monkeypatch):
    seen = {}
    monkeypatch.setitem(cli.COMMANDS, "paper", ("pl.paper", ""))
    monkeypatch.setattr("pl.paper.main", lambda argv: seen.setdefault("argv", argv))
    cli.main(["paper", "status"])
    assert seen["argv"] == ["status"]


@pytest.mark.parametrize("args", [["-m", "pl", "--help"], ["-m", "pl", "paper", "--help"], ["-m", "pl.paper", "--help"],
                                  ["-m", "pl", "evidence", "--help"], ["-m", "pl", "sources", "--help"], ["-m", "pl", "lag", "--help"]])
def test_help_runs_without_side_effects(args):
    r = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert "usage" in r.stdout.lower()
