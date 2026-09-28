# -*- coding: utf-8 -*-
"""道路混雑を Google Routes API の所要時間から代理観測する。

Places API には混雑情報が無いが、Routes API は交通状況込みの所要時間を
返すので「平常時所要時間との比」を道路混雑スコアにできる。
環境変数 GOOGLE_MAPS_API_KEY が必要 (従量課金・無料枠あり)。
"""

from __future__ import annotations

import os

import config
import store
from util import now_jst, slot_key

URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
KEY_ENV = "GOOGLE_MAPS_API_KEY"


def _latlng(s: str) -> dict:
    lat, lng = (float(x) for x in s.split(","))
    return {"location": {"latLng": {"latitude": lat, "longitude": lng}}}


def collect(conn) -> dict:
    import requests

    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        return {"ok": False, "skipped": True,
                "warning": f"{KEY_ENV} 未設定のため道路混雑をスキップ"}
    slot, got = slot_key(now_jst()), 0
    for sid, spot in config.SPOTS.items():
        route = spot.get("route")
        if not route:
            continue
        try:
            r = requests.post(URL, timeout=20, headers={
                "X-Goog-Api-Key": key,
                "X-Goog-FieldMask": "routes.duration,routes.staticDuration",
                "Content-Type": "application/json",
            }, json={
                "origin": _latlng(route["origin"]),
                "destination": _latlng(route["destination"]),
                "travelMode": "DRIVE",
                "routingPreference": "TRAFFIC_AWARE",
            })
            if r.status_code >= 400:
                print(f"  ! Routes API {r.status_code}: {r.text[:160]}", flush=True)
                continue
            routes = r.json().get("routes") or []
            if not routes:
                continue
            dur = int(str(routes[0]["duration"]).rstrip("s")) / 60.0
            free = float(route.get("free_flow_min") or 0) or (
                int(str(routes[0].get("staticDuration", "0s")).rstrip("s")) / 60.0)
            if free <= 0:
                continue
            ratio = dur / free
            score = min(100.0, max(0.0, (ratio - 1.0) * 125.0))
            store.upsert_observation(conn, sid, slot, "routes", score, ratio, "ratio")
            got += 1
        except Exception as e:                            # noqa: BLE001
            print(f"  ! Routes API 失敗: {e}", flush=True)
    conn.commit()
    return {"ok": got > 0, "routes": got}
