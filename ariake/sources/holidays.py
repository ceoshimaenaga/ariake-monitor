# -*- coding: utf-8 -*-
"""日本の祝日 (holidays-jp / 内閣府データ由来・無料・キー不要)。"""

from __future__ import annotations

from util import fetch_json
import store

URL = "https://holidays-jp.github.io/api/v1/date.json"


def collect(conn) -> dict:
    data = fetch_json(URL)
    if not isinstance(data, dict) or not data:
        return {"ok": False, "warning": "祝日APIの取得に失敗"}
    for date, name in data.items():
        store.upsert_holiday(conn, date, name)
    conn.commit()
    return {"ok": True, "days": len(data)}
