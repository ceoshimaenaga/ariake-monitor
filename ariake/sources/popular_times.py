# -*- coding: utf-8 -*-
"""混雑実測・人気時間帯 (BestTime.app 経由)。

【重要】Google Maps の「混雑する時間帯 (Popular Times)」は
Places API では提供されておらず、Google Maps のページを直接スクレイピング
するのは利用規約違反。そのため、Google 由来の混雑指標を正規に再配布して
いる BestTime.app の API を使う (有料・キーは環境変数)。

  BESTTIME_API_KEY : BestTime.app の private key
キー未設定なら黙ってスキップし、予測は config.BASELINE で動く。

課金対策
--------
クレジット課金なので、呼び出しは config.BESTTIME で厳密に制御する。
  ・対象時間帯 (既定 11〜21時) の、指定間隔 (既定2時間おき) のみ live を引く
  ・平常カーブ (forecast) は週1回だけ取り直す
  ・月間リクエスト数に上限を設け、超えたら自動停止する
実際の消費数は ariake.json の source_status で確認できる。
"""

from __future__ import annotations

import os

import config
import store
from util import fetch_json, now_jst, slot_key

FORECAST_URL = "https://besttime.app/api/v1/forecasts"
LIVE_URL = "https://besttime.app/api/v1/forecasts/live"
KEY_ENV = "BESTTIME_API_KEY"

_CREDIT_KEY = "besttime_credits"          # "YYYY-MM:件数" 形式で meta に保存
_FORECAST_KEY = "besttime_forecast_date"
_LAST_LIVE_KEY = "besttime_last_live_slot"


def targets() -> list[tuple[str, dict]]:
    """live/forecast の対象スポット (駅・道路は除外)。"""
    kinds = config.BESTTIME["kinds"]
    return [(sid, s) for sid, s in config.SPOTS.items()
            if s.get("besttime", True) and s.get("place_query")
            and s.get("kind") in kinds]


def _credits_used(conn) -> int:
    month = now_jst().strftime("%Y-%m")
    raw = store.get_meta(conn, _CREDIT_KEY, "")
    if raw and raw.split(":", 1)[0] == month:
        try:
            return int(raw.split(":", 1)[1])
        except ValueError:
            pass
    return 0


def _add_credits(conn, n: int) -> None:
    month = now_jst().strftime("%Y-%m")
    store.set_meta(conn, _CREDIT_KEY, f"{month}:{_credits_used(conn) + n}")


def _in_window(dt) -> bool:
    lo, hi = config.BESTTIME["hours"]
    step = max(1, int(config.BESTTIME["interval_hours"]))
    return lo <= dt.hour <= hi and (dt.hour - lo) % step == 0


def _query(spot: dict) -> dict:
    return {"venue_name": spot["place_query"],
            "venue_address": spot.get("place_address") or "東京都江東区有明"}


def collect_baseline(conn, key: str, budget: int) -> dict:
    """曜日×時刻の平常混雑カーブを取得して popular_baseline に保存。"""
    days, used = 0, 0
    for sid, spot in targets():
        if used >= budget:
            break
        data = fetch_json(FORECAST_URL, params={"api_key_private": key, **_query(spot)})
        used += 1
        analysis = ((data or {}).get("analysis") or []) if isinstance(data, dict) else []
        for day in analysis:
            dow = (day.get("day_info") or {}).get("day_int")
            raw = day.get("day_raw")
            if dow is None or not isinstance(raw, list) or len(raw) < 24:
                continue
            for hour, v in enumerate(raw[:24]):
                try:
                    store.upsert_popular_baseline(conn, sid, int(dow), hour,
                                                  float(v), "besttime")
                except (TypeError, ValueError):
                    continue
            days += 1
    _add_credits(conn, used)
    conn.commit()
    return {"forecast_calls": used, "baseline_days": days}


def collect_live(conn, key: str, budget: int) -> dict:
    """いまの混雑度 (live busyness) を観測値として保存。"""
    slot, got, used = slot_key(now_jst()), 0, 0
    for sid, spot in targets():
        if used >= budget:
            break
        data = fetch_json(LIVE_URL, params={"api_key_private": key, **_query(spot)})
        used += 1
        a = (data or {}).get("analysis") if isinstance(data, dict) else None
        if not isinstance(a, dict):
            continue
        v = a.get("venue_live_busyness")
        if v is None:
            v = a.get("venue_forecasted_busyness")
        if v is None:
            continue
        store.upsert_observation(conn, sid, slot, "popular_times_live",
                                 float(v), float(v), "busyness%")
        got += 1
    _add_credits(conn, used)
    conn.commit()
    return {"live_calls": used, "live_saved": got}


def collect(conn) -> dict:
    key = os.environ.get(KEY_ENV, "").strip()
    n_targets = len(targets())
    if not key:
        return {"ok": False, "skipped": True, "targets": n_targets,
                "warning": f"{KEY_ENV} 未設定のため混雑実測をスキップ "
                           "(Google Maps の人気時間帯は公式APIで提供されないため、"
                           "BestTime.app 等の有料APIが必要)"}

    now = now_jst()
    cap = int(config.BESTTIME["monthly_credit_cap"])
    used = _credits_used(conn)
    out = {"ok": True, "targets": n_targets, "credits_this_month": used,
           "monthly_cap": cap}
    if used >= cap:
        out.update(ok=False, skipped=True,
                   warning=f"BestTime の月間上限 {cap} 件に達したため停止中 "
                           f"(config.BESTTIME['monthly_credit_cap'] で変更可)")
        return out

    # 平常カーブ: forecast_every_days 日おきに取り直す
    every = int(config.BESTTIME["forecast_every_days"])
    last = store.get_meta(conn, _FORECAST_KEY)
    due = True
    if last:
        try:
            due = (now.date() - __import__("datetime").date.fromisoformat(last)).days >= every
        except ValueError:
            due = True
    if due:
        out.update(collect_baseline(conn, key, cap - _credits_used(conn)))
        store.set_meta(conn, _FORECAST_KEY, now.strftime("%Y-%m-%d"))

    # ライブ混雑: 対象時間帯の指定間隔のみ。
    # 同じ時間内に2回走っても1回しか引かない (二重課金の防止)。
    if _in_window(now):
        slot = slot_key(now)
        if store.get_meta(conn, _LAST_LIVE_KEY) == slot:
            out["live_skipped"] = f"この時間帯 ({slot[11:16]}) は取得済み"
        else:
            out.update(collect_live(conn, key, cap - _credits_used(conn)))
            store.set_meta(conn, _LAST_LIVE_KEY, slot)
    else:
        lo, hi = config.BESTTIME["hours"]
        out["live_skipped"] = (f"対象時間外 (取得は {lo}〜{hi}時の"
                               f"{config.BESTTIME['interval_hours']}時間おき)")
    out["credits_this_month"] = _credits_used(conn)
    conn.commit()
    return out
