# -*- coding: utf-8 -*-
"""共通ユーティリティ (JST時刻・HTTP取得・スコア変換)。"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9), "JST")

UA = ("Mozilla/5.0 (compatible; AriakeCongestionMonitor/1.0; "
      "+https://github.com/ceoshimaenaga/atami-monitor)")

# 収集は「相手サイトに迷惑をかけない」ことを最優先にする。
HTTP_TIMEOUT = 20
HTTP_SLEEP = 1.2          # 同一ホスト連続アクセスの間隔(秒)
_last_hit: dict[str, float] = {}


def now_jst() -> datetime:
    return datetime.now(JST)


def hour_floor(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def slot_key(dt: datetime) -> str:
    """予測・観測の時間スロットキー (JST 1時間単位)。"""
    return hour_floor(dt).strftime("%Y-%m-%dT%H:00+09:00")


def parse_slot(key: str) -> datetime:
    return datetime.fromisoformat(key)


def fetch(url: str, *, params=None, headers=None, timeout: int = HTTP_TIMEOUT):
    """GET して requests.Response を返す。失敗時は None (収集は止めない)。"""
    import requests
    from urllib.parse import urlparse

    host = urlparse(url).netloc
    wait = HTTP_SLEEP - (time.time() - _last_hit.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    hdrs = {"User-Agent": UA, "Accept-Language": "ja,en;q=0.8"}
    if headers:
        hdrs.update(headers)
    try:
        r = requests.get(url, params=params, headers=hdrs, timeout=timeout)
        _last_hit[host] = time.time()
        if r.status_code >= 400:
            print(f"  ! {r.status_code} {url}", flush=True)
            return None
        r.encoding = r.apparent_encoding or r.encoding
        return r
    except Exception as e:                                  # noqa: BLE001
        _last_hit[host] = time.time()
        print(f"  ! fetch失敗 {url}: {e}", flush=True)
        return None


def fetch_json(url: str, *, params=None, headers=None):
    r = fetch(url, params=params, headers=headers)
    if r is None:
        return None
    try:
        return r.json()
    except Exception as e:                                  # noqa: BLE001
        print(f"  ! JSON解析失敗 {url}: {e}", flush=True)
        return None


def soup(html: str):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "html.parser")


def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


LEVELS = [
    (0, 20, "すいている", "#3fb950"),
    (20, 40, "ふつう", "#7bc96f"),
    (40, 60, "やや混雑", "#d9a441"),
    (60, 80, "混雑", "#e8823c"),
    (80, 101, "非常に混雑", "#f85149"),
]


def level_of(score: float) -> dict:
    """0-100 のスコアを 5段階の混雑レベルに落とす。"""
    s = clamp(score)
    for lo, hi, label, color in LEVELS:
        if lo <= s < hi:
            return {"rank": LEVELS.index((lo, hi, label, color)) + 1,
                    "label": label, "color": color}
    return {"rank": 5, "label": "非常に混雑", "color": "#f85149"}
