# -*- coding: utf-8 -*-
"""気象庁 予報 JSON (無料・APIキー不要) から東京地方の天候を取得。

出典: https://www.jma.go.jp/bosai/forecast/data/forecast/130000.json
      (気象庁ホームページの利用規約に従い出典明記のうえ利用)
"""

from __future__ import annotations

from datetime import datetime, timedelta

from util import JST, fetch_json, slot_key
import store

URL = "https://www.jma.go.jp/bosai/forecast/data/forecast/130000.json"
AREA_TOKYO = "130010"        # 東京地方


def _category(code: str | None, pop: int | None, tmax: float | None) -> str:
    c = (code or "")[:1]
    heavy = (pop or 0) >= 70
    if c == "4":
        return "snow"
    if c == "3":
        return "heavy" if heavy else "rain"
    if (pop or 0) >= 50:
        return "rain"
    if tmax is not None and tmax >= 33:
        return "hot"
    return "clear"


def collect(conn) -> dict:
    data = fetch_json(URL)
    if not data:
        return {"ok": False, "warning": "気象庁JSONの取得に失敗"}

    codes: dict[str, str] = {}      # date -> weatherCode
    texts: dict[str, str] = {}
    pops: dict[str, int] = {}
    tmax: dict[str, float] = {}
    tmin: dict[str, float] = {}

    for block in data:
        for ts in block.get("timeSeries", []):
            times = [t[:10] for t in ts.get("timeDefines", [])]
            for area in ts.get("areas", []):
                code = (area.get("area") or {}).get("code", "")
                if area.get("weatherCodes"):
                    if code != AREA_TOKYO:
                        continue
                    for d, wc in zip(times, area["weatherCodes"]):
                        codes.setdefault(d, wc)
                    for d, w in zip(times, area.get("weathers") or []):
                        texts.setdefault(d, " ".join(w.split()))
                if area.get("pops"):
                    if code not in (AREA_TOKYO, "130011", "130012"):
                        continue
                    for d, p in zip(times, area["pops"]):
                        try:
                            pops[d] = max(pops.get(d, 0), int(p))
                        except (TypeError, ValueError):
                            pass
                for key, dst in (("tempsMax", tmax), ("tempsMin", tmin)):
                    if area.get(key):
                        for d, v in zip(times, area[key]):
                            try:
                                dst.setdefault(d, float(v))
                            except (TypeError, ValueError):
                                pass
                # 週間予報(temps)は2値/日なので最大最小を拾う
                if area.get("temps"):
                    for d, v in zip(times, area["temps"]):
                        try:
                            f = float(v)
                        except (TypeError, ValueError):
                            continue
                        tmax[d] = max(tmax.get(d, f), f)
                        tmin[d] = min(tmin.get(d, f), f)

    dates = sorted(set(codes) | set(pops) | set(tmax))
    n = 0
    for d in dates:
        cat = _category(codes.get(d), pops.get(d), tmax.get(d))
        base = datetime.fromisoformat(d + "T00:00:00+09:00").astimezone(JST)
        for h in range(24):
            store.upsert_weather(conn, slot_key(base + timedelta(hours=h)), cat,
                                 pops.get(d), tmax.get(d), tmin.get(d),
                                 texts.get(d))
            n += 1
    conn.commit()
    return {"ok": True, "slots": n, "days": len(dates)}
