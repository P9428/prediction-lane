"""Shared infrastructure. Every module imports paths, time, coercion, the
append-only JSONL journal, logging and number formatting from here; nothing
below is declared twice anywhere else in the package."""
from __future__ import annotations

import json
import logging
import math
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOCS = ROOT / "docs"
JOURNAL = ROOT / "journal"

LEAGUES = ("mlb", "nba", "nhl", "nfl")

log = logging.getLogger("pl")


def configure_logging(level: int = logging.INFO) -> None:
    """Idempotent: one stderr handler so stdout stays a clean report stream
    (the ops scripts grep it)."""
    if log.handlers:
        return
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S"))
    log.addHandler(h)
    log.setLevel(level)


# ---------------------------------------------------------------- time
def utc_now() -> str:
    """ISO-8601 UTC to the second: the journal's timestamp format."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def epoch(iso: str) -> int:
    """ISO-8601 (with or without Z / offset) -> unix seconds; naive is UTC."""
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return int(t.timestamp())


# ---------------------------------------------------------------- numbers
def to_float(x: Any) -> float | None:
    """Lenient numeric coercion for API payloads: None on anything unparseable."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def finite(x: Any) -> float | None:
    """float(x) when finite, else None. Keeps NaN out of the journal."""
    f = to_float(x)
    return f if f is not None and math.isfinite(f) else None


def fmt(x: Any, nd: int = 4) -> str:
    """Fixed-point for the markdown reports; 'nan' for None / non-finite."""
    f = to_float(x)
    return "nan" if f is None or not math.isfinite(f) else f"{f:.{nd}f}"


# ---------------------------------------------------------------- files
def read_jsonl(path: Path) -> list[dict]:
    return list(iter_jsonl(path))


def iter_jsonl(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=float) + "\n")


def load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(path: Path, obj: Any, **kw: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, **kw)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
