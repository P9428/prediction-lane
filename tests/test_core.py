from __future__ import annotations

import math
import re
from datetime import UTC, datetime

from pl import core


def test_utc_now_is_iso_seconds_utc():
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00", core.utc_now())


def test_epoch_accepts_z_offset_and_naive():
    want = int(datetime(2026, 10, 2, 0, 15, tzinfo=UTC).timestamp())
    assert core.epoch("2026-10-02T00:15:00Z") == want
    assert core.epoch("2026-10-02T00:15:00+00:00") == want
    assert core.epoch("2026-10-02T00:15:00") == want
    assert core.epoch("2026-10-01T20:15:00-04:00") == want


def test_to_float_and_finite():
    assert core.to_float("1.5") == 1.5
    assert core.to_float(None) is None
    assert core.to_float("x") is None
    assert core.finite(float("nan")) is None
    assert core.finite(float("inf")) is None
    assert core.finite("0.25") == 0.25


def test_fmt():
    assert core.fmt(None) == "nan"
    assert core.fmt(math.nan) == "nan"
    assert core.fmt(1 / 3) == "0.3333"
    assert core.fmt(2, 1) == "2.0"
    assert core.fmt("0.5", 2) == "0.50"


def test_jsonl_roundtrip_and_missing_file(tmp_path):
    p = tmp_path / "j" / "rows.jsonl"
    assert core.read_jsonl(p) == []
    core.append_jsonl(p, {"a": 1, "x": float("nan")})
    core.append_jsonl(p, {"b": [1, 2]})
    rows = core.read_jsonl(p)
    assert rows[0]["a"] == 1 and math.isnan(rows[0]["x"]) and rows[1] == {"b": [1, 2]}
    assert p.read_text(encoding="utf-8").count("\n") == 2


def test_configure_logging_is_idempotent():
    core.configure_logging()
    core.configure_logging()
    assert len(core.log.handlers) == 1
