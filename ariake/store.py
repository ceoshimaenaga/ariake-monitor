# -*- coding: utf-8 -*-
"""SQLite 永続化層 (ariake.db)。

観測値を貯め続けることで、baseline (スポット×曜日×時刻の平常値) が
実データに置き換わり、予測精度が上がっていく設計。
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta

from util import JST, now_jst, slot_key

DB_PATH = os.environ.get("ARIAKE_DB", "ariake.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id            TEXT PRIMARY KEY,
  venue         TEXT NOT NULL,
  title         TEXT NOT NULL,
  url           TEXT,
  start_date    TEXT NOT NULL,          -- YYYY-MM-DD (JST)
  end_date      TEXT NOT NULL,
  open_time     TEXT,                   -- HH:MM 開場
  start_time    TEXT,                   -- HH:MM 開演/開場(展示会は開場)
  end_time      TEXT,                   -- HH:MM 終演/閉場
  est_attendance INTEGER,               -- 1日あたり推定来場者
  scale_label   TEXT,
  hall          TEXT,
  source        TEXT NOT NULL,
  fetched_at    INTEGER NOT NULL,
  raw           TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(start_date, end_date);

CREATE TABLE IF NOT EXISTS observations (
  spot       TEXT NOT NULL,
  slot       TEXT NOT NULL,             -- YYYY-MM-DDTHH:00+09:00
  source     TEXT NOT NULL,             -- popular_times / routes / odpt / manual ...
  score      REAL NOT NULL,             -- 0-100 に正規化した混雑スコア
  raw_value  REAL,
  unit       TEXT,
  fetched_at INTEGER NOT NULL,
  PRIMARY KEY (spot, slot, source)
);
CREATE INDEX IF NOT EXISTS idx_obs_slot ON observations(slot);

CREATE TABLE IF NOT EXISTS weather (
  slot       TEXT PRIMARY KEY,
  category   TEXT,                      -- clear / rain / heavy / snow / hot
  pop        INTEGER,                   -- 降水確率 %
  temp_max   REAL,
  temp_min   REAL,
  text       TEXT,
  fetched_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS transit (
  slot       TEXT NOT NULL,
  operator   TEXT NOT NULL,
  railway    TEXT,
  status     TEXT,                      -- 平常 / 遅延 / 運転見合わせ ...
  text       TEXT,
  fetched_at INTEGER NOT NULL,
  PRIMARY KEY (slot, operator, railway)
);

CREATE TABLE IF NOT EXISTS forecasts (
  made_at   INTEGER NOT NULL,
  slot      TEXT NOT NULL,
  spot      TEXT NOT NULL,
  score     REAL NOT NULL,
  factors   TEXT,
  PRIMARY KEY (made_at, slot, spot)
);

CREATE TABLE IF NOT EXISTS holidays (
  date TEXT PRIMARY KEY,
  name TEXT
);

CREATE TABLE IF NOT EXISTS popular_baseline (
  spot       TEXT NOT NULL,
  dow        INTEGER NOT NULL,         -- 0=月 … 6=日
  hour       INTEGER NOT NULL,
  score      REAL NOT NULL,            -- 0-100 (Google人気時間帯相当)
  source     TEXT NOT NULL,
  fetched_at INTEGER NOT NULL,
  PRIMARY KEY (spot, dow, hour, source)
);

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT
);
"""


def connect(path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def event_id(venue: str, title: str, start_date: str) -> str:
    h = hashlib.sha1(f"{venue}|{title}|{start_date}".encode("utf-8"))
    return h.hexdigest()[:16]


def upsert_event(conn: sqlite3.Connection, ev: dict) -> None:
    ev = dict(ev)
    ev.setdefault("end_date", ev["start_date"])
    eid = event_id(ev["venue"], ev["title"], ev["start_date"])
    conn.execute(
        """INSERT INTO events (id, venue, title, url, start_date, end_date,
             open_time, start_time, end_time, est_attendance, scale_label,
             hall, source, fetched_at, raw)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
             end_date=excluded.end_date,
             url=COALESCE(excluded.url, events.url),
             open_time=COALESCE(excluded.open_time, events.open_time),
             start_time=COALESCE(excluded.start_time, events.start_time),
             end_time=COALESCE(excluded.end_time, events.end_time),
             est_attendance=excluded.est_attendance,
             scale_label=excluded.scale_label,
             hall=COALESCE(excluded.hall, events.hall),
             fetched_at=excluded.fetched_at,
             raw=COALESCE(excluded.raw, events.raw)""",
        (eid, ev["venue"], ev["title"], ev.get("url"), ev["start_date"],
         ev["end_date"], ev.get("open_time"), ev.get("start_time"),
         ev.get("end_time"), ev.get("est_attendance"), ev.get("scale_label"),
         ev.get("hall"), ev["source"], int(now_jst().timestamp()),
         json.dumps(ev.get("raw"), ensure_ascii=False) if ev.get("raw") else None),
    )


def events_between(conn: sqlite3.Connection, d_from: str, d_to: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM events WHERE end_date >= ? AND start_date <= ? "
        "ORDER BY start_date, start_time",
        (d_from, d_to),
    ).fetchall()
    return [dict(r) for r in rows]


def upsert_observation(conn, spot: str, slot: str, source: str,
                       score: float, raw_value=None, unit=None) -> None:
    conn.execute(
        """INSERT INTO observations (spot, slot, source, score, raw_value, unit, fetched_at)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(spot, slot, source) DO UPDATE SET
             score=excluded.score, raw_value=excluded.raw_value,
             unit=excluded.unit, fetched_at=excluded.fetched_at""",
        (spot, slot, source, float(score),
         None if raw_value is None else float(raw_value), unit,
         int(now_jst().timestamp())),
    )


def upsert_weather(conn, slot: str, category: str, pop=None,
                   temp_max=None, temp_min=None, text=None) -> None:
    conn.execute(
        """INSERT INTO weather (slot, category, pop, temp_max, temp_min, text, fetched_at)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(slot) DO UPDATE SET
             category=excluded.category, pop=excluded.pop,
             temp_max=excluded.temp_max, temp_min=excluded.temp_min,
             text=excluded.text, fetched_at=excluded.fetched_at""",
        (slot, category, pop, temp_max, temp_min, text, int(now_jst().timestamp())),
    )


def weather_map(conn) -> dict[str, dict]:
    return {r["slot"]: dict(r) for r in conn.execute("SELECT * FROM weather")}


def upsert_transit(conn, slot: str, operator: str, railway: str,
                   status: str, text: str) -> None:
    conn.execute(
        """INSERT INTO transit (slot, operator, railway, status, text, fetched_at)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(slot, operator, railway) DO UPDATE SET
             status=excluded.status, text=excluded.text,
             fetched_at=excluded.fetched_at""",
        (slot, operator, railway or "", status, text, int(now_jst().timestamp())),
    )


def latest_transit(conn, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM transit ORDER BY slot DESC, operator LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def upsert_holiday(conn, date: str, name: str) -> None:
    conn.execute("INSERT OR REPLACE INTO holidays (date, name) VALUES (?,?)",
                 (date, name))


def holiday_set(conn) -> dict[str, str]:
    return {r["date"]: r["name"] for r in conn.execute("SELECT date, name FROM holidays")}


def save_forecast(conn, made_at: int, rows: list[tuple[str, str, float, dict]]) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO forecasts (made_at, slot, spot, score, factors) "
        "VALUES (?,?,?,?,?)",
        [(made_at, slot, spot, score, json.dumps(f, ensure_ascii=False))
         for slot, spot, score, f in rows],
    )


def observed_baseline(conn, days: int = 120) -> dict[str, dict[tuple[int, int], float]]:
    """観測値から spot × (平日/休日, 時刻) の中央値を作る。

    サンプルが 3件未満のマスは返さない (config.BASELINE を使わせる)。
    """
    since = (now_jst() - timedelta(days=days)).strftime("%Y-%m-%d")
    hol = set(holiday_set(conn))
    buckets: dict[str, dict[tuple[int, int], list[float]]] = {}
    for r in conn.execute(
        "SELECT spot, slot, AVG(score) s FROM observations "
        "WHERE slot >= ? GROUP BY spot, slot", (since,)
    ):
        dt = datetime.fromisoformat(r["slot"])
        date = dt.strftime("%Y-%m-%d")
        is_hol = 1 if (dt.weekday() >= 5 or date in hol) else 0
        buckets.setdefault(r["spot"], {}).setdefault((is_hol, dt.hour), []).append(r["s"])
    out: dict[str, dict[tuple[int, int], float]] = {}
    for spot, b in buckets.items():
        for key, vals in b.items():
            if len(vals) >= 3:
                vals.sort()
                out.setdefault(spot, {})[key] = vals[len(vals) // 2]
    return out


def upsert_popular_baseline(conn, spot: str, dow: int, hour: int,
                           score: float, source: str) -> None:
    conn.execute(
        """INSERT INTO popular_baseline (spot, dow, hour, score, source, fetched_at)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(spot, dow, hour, source) DO UPDATE SET
             score=excluded.score, fetched_at=excluded.fetched_at""",
        (spot, int(dow), int(hour), float(score), source, int(now_jst().timestamp())),
    )


def popular_baseline(conn) -> dict[str, dict[tuple[int, int], float]]:
    """{spot: {(dow, hour): score}} を返す (人気時間帯ベースの平常値)。"""
    out: dict[str, dict[tuple[int, int], float]] = {}
    for r in conn.execute("SELECT spot, dow, hour, AVG(score) s FROM popular_baseline "
                          "GROUP BY spot, dow, hour"):
        out.setdefault(r["spot"], {})[(r["dow"], r["hour"])] = r["s"]
    return out


def recent_observations(conn, sources: tuple[str, ...], hours: int = 6) -> dict:
    """直近の実測値 {spot: {slot: score}} (現況表示・当該時刻の補正用)。"""
    since = slot_key(now_jst() - timedelta(hours=hours))
    out: dict[str, dict[str, float]] = {}
    q = ("SELECT spot, slot, AVG(score) s FROM observations WHERE slot >= ? AND source IN "
         f"({','.join('?' * len(sources))}) GROUP BY spot, slot")
    for r in conn.execute(q, (since, *sources)):
        out.setdefault(r["spot"], {})[r["slot"]] = r["s"]
    return out


def get_meta(conn, key: str, default=None):
    r = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def set_meta(conn, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)", (key, str(value)))
