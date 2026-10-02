from __future__ import annotations

from pathlib import Path

import pytest

from pl import paper


def espn_event(event_id: str, start: str, home: tuple[str, str], away: tuple[str, str], score: tuple[int, int] | None = None,
               status: str | None = None, season_type: int = 2) -> dict:
    """Minimal ESPN scoreboard event: (id, abbr) per side, optional final score."""
    final = score is not None
    name = status or ("STATUS_FINAL" if final else "STATUS_SCHEDULED")
    comp = [dict(homeAway="home", team=dict(id=home[0], abbreviation=home[1]), score=str(score[0]) if final else None),
            dict(homeAway="away", team=dict(id=away[0], abbreviation=away[1]), score=str(score[1]) if final else None)]
    return dict(id=event_id, date=start, season=dict(year=2026, type=season_type),
                competitions=[dict(status=dict(type=dict(name=name, completed=final)), competitors=comp)])


@pytest.fixture
def journal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every journal path and the status page at a scratch directory."""
    for name in ("PRED", "TICK", "SETTLED", "SNAP"):
        monkeypatch.setattr(paper, name, tmp_path / f"{name.lower()}.jsonl")
    monkeypatch.setattr(paper, "STATUS_MD", tmp_path / "PAPER_STATUS.md")
    return tmp_path


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record back-off sleeps instead of waiting."""
    slept: list[float] = []
    monkeypatch.setattr("pl.http.time.sleep", slept.append)
    return slept
