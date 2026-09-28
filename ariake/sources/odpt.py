# -*- coding: utf-8 -*-
"""公共交通オープンデータセンター (ODPT) から運行情報を取得。

無料。https://developer.odpt.org/ で登録してアクセストークンを取得し、
環境変数 ODPT_TOKEN に設定する (GitHub Actions なら Secrets)。

ゆりかもめ・りんかい線は有明エリアの生命線なので、遅延/運転見合わせが
起きた時点で駅の混雑スコアに上乗せする (forecast 側で反映)。
"""

from __future__ import annotations

import os

import config
import store
from util import fetch_json, now_jst, slot_key

BASE = "https://api.odpt.org/api/v4"
TOKEN_ENV = "ODPT_TOKEN"


def _classify(text: str) -> str:
    for key in ("運転見合わせ", "運休", "直通運転中止", "遅延"):
        if key in text:
            return key
    return "平常"


def collect(conn) -> dict:
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        return {"ok": False, "skipped": True,
                "warning": f"{TOKEN_ENV} 未設定のため運行情報をスキップ "
                           "(developer.odpt.org で無料取得)"}
    slot = slot_key(now_jst())
    n, statuses = 0, []
    for op in config.ODPT_OPERATORS:
        data = fetch_json(f"{BASE}/odpt:TrainInformation", params={
            "odpt:operator": op["operator"], "acl:consumerKey": token})
        if not isinstance(data, list):
            continue
        want = set(op.get("railways") or [])
        for item in data:
            railway = item.get("odpt:railway", "")
            if want and railway not in want:
                continue
            text = (item.get("odpt:trainInformationText", {}) or {})
            text = text.get("ja") if isinstance(text, dict) else str(text)
            text = (text or "").strip()
            status = _classify(text)
            store.upsert_transit(conn, slot, op["label"], railway.split(":")[-1],
                                 status, text[:200])
            statuses.append({"operator": op["label"], "status": status, "text": text[:120]})
            n += 1
    conn.commit()
    return {"ok": n > 0, "records": n, "statuses": statuses}
