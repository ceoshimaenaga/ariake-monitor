# -*- coding: utf-8 -*-
"""有明エリア混雑モニター 収集＋予測＋書き出し。

使い方:
    pip install -r requirements.txt
    python ariake/collect.py            # ariake.json を更新

環境変数 (未設定なら該当ソースだけスキップし、残りで動く):
    ODPT_TOKEN            公共交通オープンデータ (無料登録)
    BESTTIME_API_KEY      混雑実測/人気時間帯 (有料)
    GOOGLE_MAPS_API_KEY   道路所要時間による道路混雑 (従量課金)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config                                             # noqa: E402
import forecast                                           # noqa: E402
import store                                              # noqa: E402
from util import now_jst, slot_key                         # noqa: E402
from sources import events as src_events                   # noqa: E402
from sources import holidays as src_holidays                # noqa: E402
from sources import jma as src_jma                          # noqa: E402
from sources import odpt as src_odpt                        # noqa: E402
from sources import popular_times as src_popular            # noqa: E402
from sources import routes as src_routes                    # noqa: E402

SOURCES = [
    ("祝日カレンダー", src_holidays),
    ("気象庁 予報", src_jma),
    ("イベントスケジュール", src_events),
    ("運行情報 (ODPT)", src_odpt),
    ("混雑実測 (人気時間帯)", src_popular),
    ("道路混雑 (Routes API)", src_routes),
]

DETAIL_HOURS = 72          # 時間単位で詳細を出す範囲
OUT_PATH = os.environ.get("ARIAKE_JSON", "ariake.json")


def main() -> None:
    print("=== 有明エリア混雑モニター 収集開始 ===", flush=True)
    conn = store.connect()
    status, warnings = {}, []
    for label, mod in SOURCES:
        print(f"[{label}]", flush=True)
        try:
            res = mod.collect(conn)
        except Exception as e:                            # noqa: BLE001
            res = {"ok": False, "warning": f"{label} で例外: {e}"}
        status[label] = res
        for w in ([res.get("warning")] if res.get("warning") else []) + \
                 list(res.get("warnings") or []):
            warnings.append(w)
        print(f"  -> {json.dumps(res, ensure_ascii=False)[:200]}", flush=True)

    print("[予測]", flush=True)
    fc = forecast.build(conn)
    made_at = int(now_jst().timestamp())
    store.save_forecast(conn, made_at, [
        (s["series"][0]["slot"], sid, s["series"][0]["score"], s["series"][0]["factors"])
        for sid, s in fc["spots"].items()
    ])
    conn.commit()

    data = export(conn, fc, status, warnings)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    size = os.path.getsize(OUT_PATH) / 1024
    print(f"  {OUT_PATH} 書き出し: {size:.0f} KB / "
          f"スポット {len(data['spots'])} 件 / イベント {len(data['events'])} 件",
          flush=True)
    conn.close()
    print("=== 完了 ===", flush=True)


def export(conn, fc: dict, status: dict, warnings: list[str]) -> dict:
    today = now_jst().date()
    evs = store.events_between(conn, today.isoformat(),
                               (today + timedelta(days=14)).isoformat())
    events = [{
        "id": e["id"], "venue": e["venue"],
        "venue_name": config.SPOTS.get(e["venue"], {}).get("name", e["venue"]),
        "title": e["title"], "url": e["url"],
        "start_date": e["start_date"], "end_date": e["end_date"],
        "open_time": e["open_time"], "start_time": e["start_time"],
        "end_time": e["end_time"], "est_attendance": e["est_attendance"],
        "scale_label": e["scale_label"], "source": e["source"],
    } for e in evs]
    events.sort(key=lambda e: (e["start_date"], e["start_time"] or "", -(e["est_attendance"] or 0)))

    spots = {}
    for sid, s in fc["spots"].items():
        detail = s["series"][:DETAIL_HOURS]
        daily: dict[str, dict] = {}
        for slot in s["series"]:
            d = slot["slot"][:10]
            cur = daily.setdefault(d, {"date": d, "max": 0.0, "avg": 0.0, "n": 0,
                                       "peak_slot": slot["slot"]})
            if slot["score"] > cur["max"]:
                cur["max"] = slot["score"]
                cur["peak_slot"] = slot["slot"]
            cur["avg"] += slot["score"]
            cur["n"] += 1
        for cur in daily.values():
            cur["avg"] = round(cur["avg"] / max(1, cur["n"]), 1)
            cur.pop("n")
            cur["level"] = __import__("util").level_of(cur["max"])
        spots[sid] = {
            **{k: s[k] for k in ("id", "name", "kind", "lat", "lng", "capacity")},
            "now": s["now"],
            "peak_today": s["peak_today"],
            # level はスコアから引けるのでJSONには載せない (サイズ削減)
            "series": [{"slot": x["slot"], "score": x["score"],
                        "factors": [{"kind": f["kind"], "label": f["label"],
                                     "points": f["points"]}
                                    for f in x["factors"][:2]]} for x in detail],
            "daily": [daily[k] for k in sorted(daily)],
        }

    return {
        "generated_at": fc["generated_at"],
        "has_data": bool(events) or bool(spots),
        "spots": spots,
        "spot_order": list(config.SPOTS.keys()),
        "events": events,
        "alerts": fc["alerts"],
        "advice": fc["advice"],
        "transit": fc["transit"],
        "source_status": {k: {kk: vv for kk, vv in v.items() if kk != "statuses"}
                          for k, v in status.items()},
        "warnings": warnings,
        "attribution": [
            "天気: 気象庁 (https://www.jma.go.jp/)",
            "祝日: holidays-jp (内閣府公表データ由来)",
            "鉄道運行情報: 公共交通オープンデータセンター (ODPT)",
            "混雑指標: BestTime.app (Google 人気時間帯由来) ※設定時のみ",
            "道路所要時間: Google Routes API ※設定時のみ",
            "イベント情報: 各会場公式サイト",
        ],
    }


if __name__ == "__main__":
    main()
