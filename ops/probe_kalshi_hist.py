import json
import time

import requests

s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 prediction-lane/0.1"
B = "https://api.elections.kalshi.com/trade-api/v2"

for ser in ("KXMLBGAME", "KXNHLGAME", "KXNBAGAME", "KXNFLGAME"):
    n, cur, first, last = 0, "", None, None
    t = time.time()
    while True:
        j = s.get(f"{B}/markets", params=dict(limit=1000, status="settled", series_ticker=ser, cursor=cur), timeout=60).json()
        ms = j.get("markets", [])
        n += len(ms)
        if ms:
            first = first or ms[0]
            last = ms[-1]
        cur = j.get("cursor") or ""
        if not cur or n > 20000:
            break
    print(ser, "settled markets", n, f"{time.time()-t:.1f}s")
    if first:
        print("  newest", first["ticker"], first.get("open_time"), first.get("close_time"), first.get("result"), first.get("volume_fp"))
        print("  oldest", last["ticker"], last.get("open_time"), last.get("close_time"), last.get("result"))

# candlesticks for one settled MLB market
j = s.get(f"{B}/markets", params=dict(limit=5, status="settled", series_ticker="KXMLBGAME"), timeout=60).json()
m = j["markets"][0]
tk = m["ticker"]
print("sample", tk, m.get("open_time"), m.get("close_time"), m.get("result"), m.get("expected_expiration_time"))
import datetime as dt
o = int(dt.datetime.fromisoformat(m["open_time"].replace("Z", "+00:00")).timestamp())
c = int(dt.datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).timestamp())
for per in (60, 1440):
    r = s.get(f"{B}/series/KXMLBGAME/markets/{tk}/candlesticks", params=dict(start_ts=o - 3600, end_ts=c + 3600, period_interval=per), timeout=60)
    print("candles", per, r.status_code, len(r.text))
    if r.status_code == 200:
        cs = r.json().get("candlesticks", [])
        print("  n", len(cs))
        for x in cs[:2] + cs[-2:]:
            print("  ", json.dumps(x)[:400])
r = s.get(f"{B}/markets/trades", params=dict(ticker=tk, limit=1000), timeout=60)
print("trades", r.status_code, len(r.json().get("trades", [])), json.dumps(r.json().get("trades", [])[:2])[:500])
