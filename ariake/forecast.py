# -*- coding: utf-8 -*-
"""混雑予測エンジン。

考え方
------
「平常値 × 環境係数 + イベント負荷」で 0-100 のスコアを作る。

  平常値 (baseline)
      1. BestTime(Google人気時間帯) の曜日×時刻カーブ
      2. 自前の観測ログから作った中央値 (データが溜まるほど効く)
      3. config.BASELINE の事前分布
    の優先順で採用。

  環境係数
      天候 (雨/大雨/雪/猛暑) と 祝日・連休。

  イベント負荷
      会場ごとの推定来場者を「到着カーブ」「退場カーブ」に分解し、
        ・会場      → 滞在者数に比例
        ・駅 / 道路 → その時間の到着+退場の“流量”に比例
        ・商業施設  → 滞在 + 終演後の流入に比例
      として INFLUENCE の重みで各スポットへ配分する。
      これにより「終演直後の駅だけが跳ねる」挙動を再現できる。

  運行トラブル
      ゆりかもめ/りんかい線の遅延・運転見合わせは駅スコアに直接上乗せ。

出力は各スポットの時系列スコアと、根拠 (factors) / 注意時刻 (alerts) /
回避アドバイス (advice)。
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import config
import store
from util import JST, clamp, hour_floor, level_of, now_jst, parse_slot, slot_key

# 到着 / 退場カーブ (相対時間 → 全体に対する割合)
CONCERT_ARRIVE = {-2: 0.10, -1: 0.45, 0: 0.35, 1: 0.10}
CONCERT_DEPART = {0: 0.55, 1: 0.35, 2: 0.10}
EXPO_ARRIVE_SHAPE = [0.22, 0.18, 0.13, 0.10, 0.09, 0.09, 0.09, 0.10]
EXPO_DEPART_SHAPE = [0.04, 0.05, 0.07, 0.09, 0.11, 0.14, 0.27, 0.23]

LOAD_MIX = {                     # kind -> (滞在係数, 流量係数, 退場係数)
    "venue":    (1.00, 0.00, 0.00),
    "station":  (0.00, 1.00, 0.00),
    "road":     (0.00, 0.35, 0.00),
    "facility": (0.35, 0.00, 0.80),
}


def _hhmm(s: str | None, default: int) -> int:
    if not s:
        return default
    try:
        h, m = s.split(":")
        return int(h) + (1 if int(m) >= 30 else 0)
    except Exception:                                     # noqa: BLE001
        return default


def _spread(shape: list[float], start: int, hours: int) -> dict[int, float]:
    """shape を [start, start+hours) に引き伸ばして正規化した辞書にする。"""
    if hours <= 0:
        return {start: 1.0}
    vals = []
    for i in range(hours):
        idx = int(i * len(shape) / hours)
        vals.append(shape[min(idx, len(shape) - 1)])
    total = sum(vals) or 1.0
    return {start + i: v / total for i, v in enumerate(vals)}


def event_curves(ev: dict) -> tuple[dict[int, float], dict[int, float], bool]:
    """イベントの (到着カーブ, 退場カーブ, 長時間開催か) を絶対時刻で返す。"""
    open_h = _hhmm(ev.get("open_time") or ev.get("start_time"), 10)
    start_h = _hhmm(ev.get("start_time"), open_h)
    end_h = _hhmm(ev.get("end_time"), start_h + 3)
    if end_h <= start_h:
        end_h = start_h + 3
    duration = end_h - start_h
    if duration >= 5:                                     # 展示会・物販など終日型
        arrive = _spread(EXPO_ARRIVE_SHAPE, open_h, max(1, end_h - open_h))
        depart = _spread(EXPO_DEPART_SHAPE, open_h + 2, max(1, end_h - open_h))
        return arrive, depart, True
    arrive = {start_h + k: v for k, v in CONCERT_ARRIVE.items()}
    depart = {end_h + k: v for k, v in CONCERT_DEPART.items()}
    return arrive, depart, False


def _presence(arrive: dict[int, float], depart: dict[int, float], hour: int) -> float:
    a = sum(v for h, v in arrive.items() if h <= hour)
    d = sum(v for h, v in depart.items() if h <= hour)
    return max(0.0, a - d)


def _weather_factor(kind: str, wx: dict | None, spot_id: str) -> tuple[float, str | None]:
    cat = (wx or {}).get("category") or "clear"
    f = config.WEATHER_FACTOR.get(cat, config.WEATHER_FACTOR["clear"]).get(kind, 1.0)
    if cat in ("rain", "heavy", "snow") and spot_id in (
            "ariake_tennis_forest", "toyosu_market"):
        f = min(f, config.PARK_RAIN_FACTOR)
    if cat == "clear":
        return 1.0, None
    label = {"rain": "雨", "heavy": "強い雨", "snow": "雪", "hot": "猛暑"}[cat]
    return f, label


def _baseline(spot_id: str, spot: dict, dt: datetime, is_hol: bool,
              pop_base: dict, obs_base: dict) -> tuple[float, str]:
    dow, hour = dt.weekday(), dt.hour
    v = (pop_base.get(spot_id) or {}).get((dow, hour))
    if v is not None:
        return float(v), "人気時間帯データ"
    v = (obs_base.get(spot_id) or {}).get((1 if is_hol else 0, hour))
    if v is not None:
        return float(v), "自前の観測実績"
    table = config.BASELINE.get(spot["kind"], config.BASELINE["facility"])
    v = table[1 if is_hol else 0][hour] * float(spot.get("baseline_scale") or 1.0)
    return float(v), "初期値(事前分布)"


def _km(a: dict, b: dict) -> float:
    """2地点の概算距離 (km)。有明周辺の狭い範囲なので平面近似で十分。"""
    import math
    la, lo = a.get("lat"), a.get("lng")
    lb, lob = b.get("lat"), b.get("lng")
    if None in (la, lo, lb, lob):
        return 99.0
    dy = (la - lb) * 111.0
    dx = (lo - lob) * 111.0 * math.cos(math.radians((la + lb) / 2))
    return math.hypot(dx, dy)


_SPILL_CACHE: dict[tuple[str, str], float] = {}


def influence(venue: str, spot_id: str) -> tuple[float, bool]:
    """会場 → スポットの (波及率, 明示指定か)。無指定なら距離減衰で補う。"""
    explicit = config.INFLUENCE.get(venue, {})
    if spot_id in explicit:
        return explicit[spot_id], True
    spot = config.SPOTS.get(spot_id) or {}
    if spot.get("kind") != "facility":
        return 0.0, False                # 駅・道路は明示指定のみ (取り違えを防ぐ)
    key = (venue, spot_id)
    if key not in _SPILL_CACHE:
        d = _km(config.SPOTS.get(venue) or {}, spot)
        w = config.SPILLOVER_BASE * math.exp(-d / config.SPILLOVER_DECAY_KM)
        w = min(w, config.SPILLOVER_MAX) * float(spot.get("spillover_scale") or 1.0)
        _SPILL_CACHE[key] = w if w >= config.SPILLOVER_MIN else 0.0
    return _SPILL_CACHE[key], False


def soften(points: float) -> float:
    """イベント負荷のソフト飽和。小〜中規模はそのまま、超大型だけ圧縮する。"""
    knee, rng, tau = config.EVENT_SOFT_KNEE, config.EVENT_SOFT_RANGE, config.EVENT_SOFT_TAU
    if points <= knee:
        return points
    return knee + rng * (1.0 - math.exp(-(points - knee) / tau))


def _transit_penalty(transit: list[dict]) -> tuple[float, list[str]]:
    pts, notes = 0.0, []
    for t in transit:
        add = config.TRANSIT_PENALTY.get(t.get("status") or "", 0)
        if add:
            pts = max(pts, add)
            notes.append(f"{t['operator']}: {t['status']}")
    return pts, notes


def build(conn, hours: int | None = None) -> dict:
    hours = hours or config.FORECAST_HOURS
    base_dt = hour_floor(now_jst())
    slots = [base_dt + timedelta(hours=i) for i in range(hours)]

    hol = store.holiday_set(conn)
    wx = store.weather_map(conn)
    pop_base = store.popular_baseline(conn)
    obs_base = store.observed_baseline(conn)
    live = store.recent_observations(conn, ("popular_times_live", "routes"), hours=3)
    transit = [t for t in store.latest_transit(conn, 12)
               if t.get("slot", "") >= slot_key(base_dt - timedelta(hours=2))]
    t_pts, t_notes = _transit_penalty(transit)

    evs = store.events_between(
        conn, base_dt.strftime("%Y-%m-%d"),
        (base_dt + timedelta(hours=hours)).strftime("%Y-%m-%d"))
    # イベントを日付ごとに展開 (会期中の各日に同じ規模が立つ)
    by_date: dict[str, list[dict]] = {}
    for ev in evs:
        try:
            d0 = date.fromisoformat(ev["start_date"])
            d1 = date.fromisoformat(ev["end_date"])
        except ValueError:
            continue
        arrive, depart, all_day = event_curves(ev)
        ev = dict(ev, _arrive=arrive, _depart=depart, _all_day=all_day)
        d = d0
        while d <= d1 and (d - d0).days < 60:
            by_date.setdefault(d.isoformat(), []).append(ev)
            d += timedelta(days=1)

    # 同時開催の単純合計が定員を大きく超えないよう、会場・日ごとに按分圧縮する
    for dkey, evs_of_day in by_date.items():
        by_venue: dict[str, list[dict]] = {}
        for ev in evs_of_day:
            by_venue.setdefault(ev["venue"], []).append(ev)
        for venue, group in by_venue.items():
            cap = (config.SPOTS.get(venue, {}).get("capacity") or 0) \
                * config.VENUE_DAILY_CAP_RATIO
            total = sum(float(e.get("est_attendance") or 0) for e in group)
            if cap <= 0 or total <= cap or len(group) < 2:
                continue
            ratio = cap / total
            for i, ev in enumerate(group):
                scaled = dict(ev)
                scaled["est_attendance"] = float(ev.get("est_attendance") or 0) * ratio
                scaled["_co_located"] = len(group)
                group[i] = scaled
            # by_date 側の参照も差し替える
            by_date[dkey] = [e for v, g in by_venue.items() for e in g]

    out_spots: dict[str, dict] = {}
    for sid, spot in config.SPOTS.items():
        kind = spot["kind"]
        mix = LOAD_MIX.get(kind, LOAD_MIX["facility"])
        scale = float(spot.get("scale") or 5000)
        series = []
        for dt in slots:
            dkey = dt.strftime("%Y-%m-%d")
            is_hol = dt.weekday() >= 5 or dkey in hol
            base, base_src = _baseline(sid, spot, dt, is_hol, pop_base, obs_base)
            factors = [{"kind": "baseline", "label": f"平常値（{base_src}）",
                        "points": round(base, 1)}]

            wf, wlabel = _weather_factor(kind, wx.get(slot_key(dt)), sid)
            score = base * wf
            if wlabel:
                factors.append({"kind": "weather", "label": f"天候: {wlabel}",
                                "points": round(base * wf - base, 1)})
            if dkey in hol and kind in ("facility", "station", "road"):
                boost = config.HOLIDAY_BOOST
                factors.append({"kind": "holiday", "label": f"祝日（{hol[dkey]}）",
                                "points": round(score * (boost - 1), 1)})
                score *= boost

            ev_points = 0.0
            for ev in by_date.get(dkey, []):
                w, explicit = influence(ev["venue"], sid)
                if w <= 0:
                    continue
                n = float(ev.get("est_attendance") or 0)
                if n <= 0:
                    continue
                a = ev["_arrive"].get(dt.hour, 0.0)
                d = ev["_depart"].get(dt.hour, 0.0)
                pres = _presence(ev["_arrive"], ev["_depart"], dt.hour)
                load = n * (mix[0] * pres + mix[1] * (a + d) + mix[2] * d)
                pts = load * w / scale * 100.0
                if not explicit:         # 距離ベースの推測には上限をかける
                    pts = min(pts, config.SPILLOVER_MAX_POINTS)
                if pts < 0.5:
                    continue
                phase = ("退場ピーク" if d >= max(a, 0.2) else
                         "入場ピーク" if a > 0 else "開催中")
                factors.append({
                    "kind": "event", "label": f"{config.SPOTS[ev['venue']]['name']}"
                                              f"「{ev['title']}」{phase}",
                    "points": round(pts, 1), "event_id": ev["id"],
                    "attendance": int(n), "phase": phase,
                    "co_located": ev.get("_co_located"),
                })
                ev_points += pts
            score += soften(ev_points)

            if t_pts and kind in ("station", "road") and dt <= base_dt + timedelta(hours=2):
                factors.append({"kind": "transit",
                                "label": "運行トラブル: " + " / ".join(t_notes[:2]),
                                "points": round(t_pts, 1)})
                score += t_pts

            score = clamp(score)
            obs = (live.get(sid) or {}).get(slot_key(dt))
            if obs is not None and dt <= base_dt:
                score = clamp(0.45 * score + 0.55 * obs)
                factors.append({"kind": "observed", "label": "実測値で補正",
                                "points": round(obs, 1)})
            factors.sort(key=lambda f: -abs(f.get("points") or 0))
            series.append({"slot": slot_key(dt), "score": round(score, 1),
                           "level": level_of(score), "factors": factors[:5]})

        out_spots[sid] = {
            "id": sid, "name": spot["name"], "kind": kind,
            "lat": spot.get("lat"), "lng": spot.get("lng"),
            "capacity": spot.get("capacity"),
            "now": series[0], "series": series,
            "peak_today": max(
                (s for s in series if s["slot"][:10] == base_dt.strftime("%Y-%m-%d")),
                key=lambda s: s["score"], default=series[0]),
        }

    return {
        "generated_at": now_jst().isoformat(timespec="seconds"),
        "spots": out_spots,
        # 画面は3日先まで出すので、注意時刻・案内も同じ範囲を対象にする
        "alerts": build_alerts(out_spots, hours=72),
        "advice": build_advice(out_spots, hours=72),
        "transit": transit,
    }


def build_alerts(spots: dict, hours: int = 72) -> list[dict]:
    """指定時間内の混雑ピークを時刻順に並べた注意リスト。"""
    alerts = []
    for sid, s in spots.items():
        prev = 0.0
        for slot in s["series"][:hours]:
            if slot["score"] >= 70 and slot["score"] > prev:
                cause = next((f for f in slot["factors"] if f["kind"] == "event"), None)
                alerts.append({
                    "slot": slot["slot"], "spot": sid, "spot_name": s["name"],
                    "score": slot["score"], "level": slot["level"],
                    "cause": (cause or {}).get("label") or "平常の混雑",
                })
            prev = slot["score"]
    alerts.sort(key=lambda a: (a["slot"], -a["score"]))
    # 同一スポットは1時間帯だけ残す (同じ山を何度も出さない)
    seen, per_slot, out = set(), {}, []
    for a in sorted(alerts, key=lambda a: (a["slot"], -a["score"])):
        k = (a["spot"], a["slot"][:13])
        if k in seen:
            continue
        if per_slot.get(a["slot"], 0) >= 3:      # 同じ時刻に並べるのは上位3スポットまで
            continue
        seen.add(k)
        per_slot[a["slot"]] = per_slot.get(a["slot"], 0) + 1
        out.append(a)
    return out[:60]


STATIONS = ("st_tokyo_bigsight", "st_kokusai_tenjijo", "st_ariake", "st_ariake_tennis")


def build_advice(spots: dict, hours: int = 72) -> list[dict]:
    """混雑する駅について、同時刻で最も空いている駅を案内する。"""
    out = []
    avail = [s for s in STATIONS if s in spots]
    if len(avail) < 2:
        return out
    n = min(hours, len(spots[avail[0]]["series"]))
    for i in range(n):
        scored = sorted(((spots[s]["series"][i]["score"], s) for s in avail))
        worst_score, worst = scored[-1]
        best_score, best = scored[0]
        if worst_score >= 70 and worst_score - best_score >= 20:
            out.append({"slot": spots[worst]["series"][i]["slot"],
                        "worst": worst, "best": best,
                        "worst_score": worst_score, "best_score": best_score})
    # 連続する同じ組み合わせは 1 件の時間レンジにまとめる
    merged: list[dict] = []
    for a in out:
        last = merged[-1] if merged else None
        if last and last["worst"] == a["worst"] and last["best"] == a["best"] \
                and parse_slot(a["slot"]) - parse_slot(last["until"]) <= timedelta(hours=1):
            last["until"] = a["slot"]
            last["worst_score"] = max(last["worst_score"], a["worst_score"])
            continue
        merged.append(dict(a, until=a["slot"]))
    result = []
    for a in merged:
        s0, s1 = parse_slot(a["slot"]), parse_slot(a["until"]) + timedelta(hours=1)
        span = s0.strftime("%m/%d %H:%M") + "〜" + s1.strftime("%H:%M")
        result.append({
            "slot": a["slot"], "until": a["until"], "span": span,
            "text": f"{span} は {spots[a['worst']]['name']} が混雑"
                    f"（{a['worst_score']:.0f}）。{spots[a['best']]['name']}"
                    f"（{a['best_score']:.0f}）へ回ると空いています。",
        })
    return result[:20]
