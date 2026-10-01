"""Reality Infrastructure binding: every decision in this repo is a rule the
engine applies to logged claims, and every verdict is read back from the
engine's belief state. Mirrors venue-gate/vg/evidence.py.

Log order on every run:
  prereg        docs/PREREGISTRATION.md and docs/PREREG_KALSHI_LAG.md, sha-pinned, ltime 0
  rule_version  the pre-registered rules as predicate ASTs (data, replayable)
  capture       one per data file the measurements rest on: sha256, bytes, as_of
  assertion     one per measured decision cell with its numbers as rule-readable fields
  verdict       the strings read from the belief state, with the log root and size

  python -m pl.evidence run              -> data/evidence/pl_<runid>.ri + docs/VERDICT.md
  python -m pl.evidence replay <file>    -> re-submits every entry, re-verifies signatures and root
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RI_ROOT = os.environ.get("PL_RI_ROOT", r"C:\Users\newce\Reality-Infrastructure\reference-implementation")
if RI_ROOT not in sys.path:
    sys.path.insert(0, RI_ROOT)

from ri_core.identity import Identity, LocalAuthority  # noqa: E402
from ri_core.log import EvidenceLog  # noqa: E402
from ri_core.project import project, submit  # noqa: E402
from ri_core.provenance import ProvenanceGraph  # noqa: E402
from ri_core.rules import RuleStore  # noqa: E402
from ri_core.serialization import decode, encode  # noqa: E402

ANCHOR_ID = "prediction-lane"
ANCHOR_SEED = b"prediction-lane-evidence-v1"
ASSERTION_MASS = Decimal("0.9")
ALPHA = Decimal("0.05")
LEAGUES = ("mlb", "nba", "nhl", "nfl")
Q = Decimal("0.00000001")
EVID = ROOT / "data" / "evidence"


def _fld(n):
    return ["field", n]


def _c(v):
    return ["const", v]


# The rules, verbatim as the engine sees them. A bound rule EXCLUDES a failing
# observation; the proposition holds a belief iff at least one observation passed.
RULE_SPECS: dict[str, list] = {
    # PREREGISTRATION.md primary: model coefficient > 0 and Bonferroni-adjusted Wald p < alpha
    "lane-informative": ["and", ["gt", _fld("c_model"), _c(Decimal(0))], ["lt", _fld("p_wald_bonf"), _c(ALPHA)]],
    # PREREG_KALSHI_LAG.md primaries: 97.5% lower bounds of ROI and CLV both > 0
    "lag-primary": ["and", ["gt", _fld("roi_lo975"), _c(Decimal(0))], ["gt", _fld("clv_lo975"), _c(Decimal(0))]],
    # paper kill rules (a PASS of a kill rule means KILL)
    "paper-K1": ["and", ["ge", _fld("n_games"), _c(300)], ["lt", _fld("d_ll_ci_hi"), _c(Decimal(0))]],
    "paper-K2": ["and", ["ge", _fld("n_tickets"), _c(100)], ["lt", _fld("roi_ci_hi"), _c(Decimal(0))]],
    "paper-K3": ["and", ["ge", _fld("n_tickets"), _c(100)], ["lt", _fld("payoff_margin"), _c(Decimal(0))]],
}
BINDINGS = {"lane:": ("lane-informative", 1), "lag:": ("lag-primary", 1),
            "kill:K1": ("paper-K1", 1), "kill:K2": ("paper-K2", 1), "kill:K3": ("paper-K3", 1)}
_RESERVED = {"kind", "id", "source_id", "proposition", "payload", "ltime", "sig"}


class EvidenceError(Exception):
    pass


def q(x):
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(f) else Decimal(repr(f)).quantize(Q)


def _clean(x):
    if isinstance(x, bool) or x is None or isinstance(x, (int, str, Decimal)):
        return x
    if isinstance(x, float):
        return Decimal(repr(x)) if math.isfinite(x) else None
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    return str(x)


def ltime_of(iso: str) -> int:
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return int(t.timestamp())


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Evidence:
    def __init__(self) -> None:
        self.authority = LocalAuthority(anchor_id=ANCHOR_ID, seed=ANCHOR_SEED)
        self.log = EvidenceLog()
        self.graph = ProvenanceGraph()
        self.rules = RuleStore()
        self._issued: set[str] = set()
        self._ids: set[str] = set()
        self._props: set[str] = set()

    def _identity(self, source: str) -> Identity:
        if source not in self._issued:
            self.authority.issue_identity(source)
            self._issued.add(source)
        return Identity(identity_id=source, anchor_id=ANCHOR_ID, name=source)

    def rule(self, rule_id: str, version: int, fn_spec, ltime: int = 0) -> int:
        return self.log.append(self.rules.register(rule_id, version, fn_spec, ltime))

    def submit(self, obs_id, source, proposition, frame, mass, ltime, uncertainty, detail=None, fields=None) -> int:
        if obs_id in self._ids:
            raise EvidenceError(f"duplicate observation id {obs_id}")
        payload = {"frame": list(frame), "mass": dict(mass), "uncertaintyType": sorted(uncertainty)}
        if detail:
            payload["detail"] = _clean(detail)
        unsigned = {"kind": "observation", "id": obs_id, "source_id": source, "proposition": proposition,
                    "payload": payload, "ltime": int(ltime)}
        for k, v in (fields or {}).items():
            if k in _RESERVED:
                raise EvidenceError(f"field {k!r} collides with an observation key")
            if isinstance(v, float):
                v = Decimal(repr(v))
            if not isinstance(v, (bool, int, str, Decimal)):
                raise EvidenceError(f"field {k!r} must be Decimal/int/bool/str, got {type(v).__name__}")
            unsigned[k] = v
        sig = self.authority.sign(self._identity(source), encode(unsigned))
        obs = dict(unsigned, sig=sig)
        idx, _ = submit(obs, self.log, self.graph, self.authority)
        self._ids.add(obs_id)
        self._props.add(proposition)
        return idx

    def prereg(self, name: str, path: Path) -> int:
        sha = sha256_file(path)
        return self.submit(f"prereg:{name}", "operator", f"prereg:{name}", ("frozen",), {"frozen": Decimal(1)}, 0,
                           ["measured"], dict(doc=str(path.relative_to(ROOT)), doc_sha256=sha))

    def capture(self, name: str, path: Path, as_of: int, detail: dict | None = None) -> int:
        sha = sha256_file(path)
        return self.submit(f"capture:{name}:{sha[:16]}", "prediction-lane-pull", f"capture:{name}", ("present",),
                           {"present": Decimal(1)}, as_of, ["measured"],
                           dict(path=str(path.relative_to(ROOT)), sha256=sha, nbytes=path.stat().st_size, **(detail or {})))

    def assertion(self, obs_id: str, proposition: str, frame: tuple, label: str, ltime: int, fields: dict, detail=None) -> int:
        omega = ",".join(sorted(frame))
        return self.submit(obs_id, "prediction-lane-measure", proposition, tuple(sorted(frame)),
                           {label: ASSERTION_MASS, omega: Decimal(1) - ASSERTION_MASS}, ltime, ["estimated"], detail, fields=fields)

    def verdict(self, run_id: str, ltime: int, payload: dict) -> int:
        return self.submit(f"verdict:{run_id}", "prediction-lane-measure", f"verdict:{run_id}", ("recorded",),
                           {"recorded": Decimal(1)}, ltime, ["measured"], payload)

    def bindings(self) -> dict:
        out = {}
        for prop in self._props:
            for prefix, rv in BINDINGS.items():
                if prop.startswith(prefix):
                    out[prop] = rv
        return out

    def project(self, as_of: int) -> dict:
        return project(self.log, self.graph, self.authority, self.rules, self.bindings(), as_of)

    @staticmethod
    def decision(state: dict, proposition: str):
        node = state["propositions"].get(proposition)
        if node is None:
            return None
        just = node["justification"]
        passed = sorted(o["entity_id"][4:] for c in just["classes"] for o in c["observations"])
        excluded = sorted((e["entity_id"][4:], e.get("rule_id"), e.get("rule_version")) for e in just["excluded"])
        return dict(has_belief=node["belief"] is not None, passed=passed, excluded=excluded)

    def root(self, size=None) -> str:
        return self.log.root(size).hex()

    def __len__(self):
        return len(self.log)

    def save(self, path: Path) -> bytes:
        run = {"kind": "prediction_lane_run", "anchor_id": ANCHOR_ID,
               "log": {"kind": "log_export", "entries": [self.log.entry(i) for i in range(len(self.log))]}}
        data = encode(run)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return data

    @classmethod
    def load(cls, path: Path) -> "Evidence":
        run = decode(path.read_bytes())
        if not isinstance(run, dict) or run.get("kind") != "prediction_lane_run":
            raise EvidenceError("not a prediction_lane_run file")
        ev = cls()
        for i, entry in enumerate(run["log"]["entries"]):
            obj = decode(entry)
            if obj.get("kind") == "rule_version":
                idx = ev.log.append(ev.rules.register(obj["rule_id"], obj["version"], obj["fn_spec"], obj["ltime"]))
            elif obj.get("kind") == "observation":
                ev._identity(obj["source_id"])
                idx, _ = submit(obj, ev.log, ev.graph, ev.authority)
                ev._ids.add(obj["id"])
                ev._props.add(obj["proposition"])
            else:
                raise EvidenceError(f"entry {i}: unknown kind {obj.get('kind')!r}")
            if ev.log.entry(idx) != entry:
                raise EvidenceError(f"entry {i} did not round-trip byte-identically")
        return ev

    def entries(self):
        return [decode(self.log.entry(i)) for i in range(len(self.log))]


# ---------------------------------------------------------------- the run
def _as_of_store() -> int:
    c = sqlite3.connect(ROOT / "data" / "pl.sqlite")
    t = c.execute("SELECT max(fetched_at) FROM games").fetchone()[0]
    c.close()
    return ltime_of(t)


def run() -> dict:
    ev = Evidence()
    ev.prereg("primary", ROOT / "docs" / "PREREGISTRATION.md")
    ev.prereg("kalshi-lag", ROOT / "docs" / "PREREG_KALSHI_LAG.md")
    for rid, spec in RULE_SPECS.items():
        ev.rule(rid, 1, spec)
    as_of = _as_of_store()
    ev.capture("pl.sqlite", ROOT / "data" / "pl.sqlite", as_of)
    br = ROOT / "data" / "backtest_results.json"
    results = json.load(open(br))
    ev.capture("backtest_results.json", br, as_of)
    # --- lane assertions: one per league, close (primary) and open (secondary, same rule, Bonferroni over 4)
    for r in results:
        lg = r["league"]
        for sample, key in (("close", "primary_close"), ("open", "secondary_open")):
            pc = r[key]
            fields = dict(c_model=q(pc["c_model"]), z_c=q(pc["z_c"]), p_wald=q(pc["p_wald"]),
                          p_wald_bonf=q(min(1.0, pc["p_wald"] * len(LEAGUES))), n=int(pc["n"]),
                          d_ll=q(r["models"]["p_model"]["skill"]["d_ll"]))
            if any(v is None for v in fields.values()):
                continue
            ev.assertion(f"lane:{lg}:{sample}", f"lane:{lg}:{sample}", ("informative", "redundant"), "informative", as_of,
                         fields, dict(test_seasons=r["test_seasons"], tune_season=r["tune_season"], blend_w=pc["blend_w"]))
    # --- Kalshi lag primaries, if measured
    lag = ROOT / "data" / "kalshi_lag_results.json"
    if lag.exists():
        kh = ROOT / "data" / "kalshi_hist.sqlite"
        c = sqlite3.connect(kh)
        k_as_of = ltime_of(c.execute("SELECT max(fetched_at) FROM candle_pulls").fetchone()[0])
        n_m = c.execute("SELECT count(*) FROM markets").fetchone()[0]
        c.close()
        ev.capture("kalshi_hist.sqlite", kh, k_as_of, dict(markets=n_m))
        ev.capture("kalshi_lag_results.json", lag, k_as_of)
        L = json.load(open(lag))
        for name, pr in zip(("P1", "P2"), L["primaries"]):
            fields = dict(roi=q(pr.get("roi")), roi_lo975=q(pr.get("roi_lo975")), clv=q(pr.get("clv")),
                          clv_lo975=q(pr.get("clv_lo975")), n_bets=int(pr.get("n_bets", 0)), n_quoted=int(pr.get("n_quoted", 0)))
            if any(v is None for v in fields.values()):
                fields.update(roi=Decimal(0), roi_lo975=Decimal(-1), clv=Decimal(0), clv_lo975=Decimal(-1))
            ev.assertion(f"lag:{name}", f"lag:{name}", ("beatable", "efficient"), "beatable", k_as_of, fields,
                          dict(p=pr.get("p"), h=pr.get("h")))
    # --- paper kill rules, from the settled journal (fields only when the counts exist)
    settled = ROOT / "journal" / "settled.jsonl"
    if settled.exists():
        import numpy as np
        rows = [json.loads(l) for l in settled.read_text(encoding="utf-8").splitlines() if l.strip()]
        preds = [x for x in rows if x["kind"] == "pred" and "ll_book" in x and "ll_model" in x]
        ticks = [x for x in rows if x["kind"] == "ticket"]
        t_as_of = max((ltime_of(x["ts"]) for x in rows), default=as_of)
        d = np.array([x["ll_book"] - x["ll_model"] for x in preds]) if preds else np.array([])
        d_hi = (d.mean() + 1.96 * d.std(ddof=1) / math.sqrt(len(d))) if len(d) > 1 else 1.0
        ev.assertion("kill:K1", "kill:K1", ("kill", "live"), "kill", t_as_of,
                     dict(n_games=len(preds), d_ll_mean=q(d.mean()) if len(d) else Decimal(0), d_ll_ci_hi=q(d_hi)))
        if ticks:
            pnl = np.array([x["pnl"] for x in ticks])
            st = np.array([x["stake"] for x in ticks])
            roi = pnl.sum() / st.sum()
            per = pnl / st
            roi_hi = roi + 1.96 * per.std(ddof=1) / math.sqrt(len(per)) if len(per) > 1 else 1.0
            hit = float(np.mean(pnl > 0))
            wins, losses = pnl[pnl > 0], pnl[pnl < 0]
            payoff = (wins.mean() / abs(losses.mean())) if len(wins) and len(losses) else 1.0
            margin = payoff - 0.8 * (1 - hit) / max(hit, 1e-9)
            ev.assertion("kill:K2", "kill:K2", ("kill", "live"), "kill", t_as_of,
                         dict(n_tickets=len(ticks), roi=q(roi), roi_ci_hi=q(roi_hi)))
            ev.assertion("kill:K3", "kill:K3", ("kill", "live"), "kill", t_as_of,
                         dict(n_tickets=len(ticks), hit=q(hit), payoff=q(payoff), payoff_margin=q(margin)))
    # --- read the verdict from the belief state
    state = ev.project(as_of=2 ** 31)
    verd: dict = {"lane": {}, "lag": {}, "kill": {}}
    for lg in LEAGUES:
        for sample in ("close", "open"):
            dcs = ev.decision(state, f"lane:{lg}:{sample}")
            verd["lane"][f"{lg}:{sample}"] = "NOT_ASSERTED" if dcs is None else ("INFORMATIVE" if dcs["has_belief"] else "REDUNDANT")
    for name in ("P1", "P2"):
        dcs = ev.decision(state, f"lag:{name}")
        verd["lag"][name] = "NOT_MEASURED" if dcs is None else ("PASS" if dcs["has_belief"] else "FAIL")
    for k in ("K1", "K2", "K3"):
        dcs = ev.decision(state, f"kill:{k}")
        verd["kill"][k] = "NOT_ASSERTED" if dcs is None else ("KILL" if dcs["has_belief"] else "LIVE")
    size = len(ev)
    root = ev.root(size)
    run_id = root[:12]
    ev.verdict(run_id, as_of, dict(verdict=verd, root_at_read=root, size_at_read=size))
    path = EVID / f"pl_{run_id}.ri"
    ev.save(path)
    md = [f"# VERDICT — read from the RI belief state, run {run_id}", "",
          f"log entries {len(ev)}, root at read `{root[:16]}…`, file `{path.relative_to(ROOT)}`; "
          f"replay with `python -m pl.evidence replay {path.relative_to(ROOT)}`", "",
          "| proposition | rule | verdict |", "|---|---|---|"]
    for k, v in verd["lane"].items():
        md.append(f"| lane:{k} | lane-informative v1 | **{v}** |")
    for k, v in verd["lag"].items():
        md.append(f"| lag:{k} | lag-primary v1 | **{v}** |")
    for k, v in verd["kill"].items():
        md.append(f"| kill:{k} | paper-{k} v1 | **{v}** |")
    md += ["", "A verdict here is the engine's projection of the logged claims under the logged rules; "
           "docs/RESULTS.md and docs/KALSHI_LAG.md are the measurements those claims were read from."]
    (ROOT / "docs" / "VERDICT.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return verd


def replay(path: Path) -> None:
    ev = Evidence.load(path)
    ents = ev.entries()
    v = [e for e in ents if e.get("kind") == "observation" and e["id"].startswith("verdict:")][-1]
    size, root = v["payload"]["detail"]["size_at_read"], v["payload"]["detail"]["root_at_read"]
    rr = ev.root(int(size))
    state = ev.project(as_of=2 ** 31)
    print(f"entries {len(ev)}  signatures re-verified  root@{size} {'IDENTICAL' if rr == root else 'MISMATCH'}")
    for prop in sorted(p for p in state["propositions"] if p.split(":")[0] in ("lane", "lag", "kill")):
        d = ev.decision(state, prop)
        print(f"  {prop:16s} belief={'yes' if d['has_belief'] else 'no'} passed={d['passed']} excluded={[x[1] + 'v' + str(x[2]) for x in d['excluded']]}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "replay":
        replay(ROOT / a[1] if not Path(a[1]).is_absolute() else Path(a[1]))
    else:
        run()
