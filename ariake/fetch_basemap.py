# -*- coding: utf-8 -*-
"""OpenStreetMap から有明周辺の地形データを取得して basemap.json を作る。

これまで地図の下地は緯度経度グリッドだけで、海岸線も運河も建物も無かった。
想像で描くと地図として嘘になるので、実際の地理データを取ってきて使う。

取得するもの:
  water     : 運河・水面のポリゴン (有明は埋立地で、島の間が運河)
  coastline : 海岸線 (線として描く)
  parks     : 公園・緑地
  buildings : 建物の輪郭 (これが入ると一気に街に見える)
  roads     : 道路 (幹線とそれ以外)
  rail      : 鉄道 (ゆりかもめ・りんかい線)

出典表記が必要: © OpenStreetMap contributors (ODbL)

実行はネットワークのある環境で:
    python ariake/fetch_basemap.py
GitHub Actions の ariake-basemap ワークフローから手動実行できる。
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config                                             # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir,
                   "designs", "basemap.json")
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
MARGIN = 0.006          # 監視地点の外側にどれだけ余白を取るか (度)
PRECISION = 5           # 座標の丸め桁 (5桁 ≒ 1m)
MIN_BUILDING_PTS = 3


def bbox() -> tuple[float, float, float, float]:
    lats = [s["lat"] for s in config.SPOTS.values() if s.get("lat")]
    lngs = [s["lng"] for s in config.SPOTS.values() if s.get("lng")]
    return (min(lats) - MARGIN, min(lngs) - MARGIN,
            max(lats) + MARGIN, max(lngs) + MARGIN)


def query(b: tuple[float, float, float, float]) -> str:
    s, w, n, e = b
    box = f"{s},{w},{n},{e}"
    return f"""
[out:json][timeout:180];
(
  way["natural"="coastline"]({box});
  way["natural"="water"]({box});
  way["waterway"="riverbank"]({box});
  way["landuse"="basin"]({box});
  way["leisure"="park"]({box});
  way["landuse"~"^(grass|forest|recreation_ground)$"]({box});
  way["leisure"="pitch"]({box});
  way["building"]({box});
  way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|secondary|tertiary|residential|unclassified)$"]({box});
  way["railway"~"^(rail|light_rail|monorail|subway)$"]({box});
);
out geom;
"""


def fetch(q: str) -> dict:
    import requests
    last = None
    for url in ENDPOINTS:
        try:
            print(f"  Overpass に問い合わせ: {url}", flush=True)
            r = requests.post(url, data={"data": q}, timeout=240,
                              headers={"User-Agent": "AriakeCongestionMonitor/1.0"})
            if r.status_code == 200:
                return r.json()
            print(f"  ! {r.status_code} {r.text[:200]}", flush=True)
            last = f"{r.status_code}"
        except Exception as e:                            # noqa: BLE001
            print(f"  ! 失敗: {e}", flush=True)
            last = str(e)
    raise SystemExit(f"Overpass から取得できませんでした: {last}")


def line(geom: list[dict]) -> list[list[float]]:
    """[[lng, lat], ...] に変換し、丸めと重複点の除去をする。"""
    out: list[list[float]] = []
    for p in geom:
        c = [round(p["lon"], PRECISION), round(p["lat"], PRECISION)]
        if not out or out[-1] != c:
            out.append(c)
    return out


def build_land(out):
    """海岸線から陸地のポリゴンを組み立てる。
    OSM の海岸線は「進行方向の左が陸」という規則で引かれているので、
    表示範囲の枠で切ってから枠の縁を反時計回りにたどって閉じると、
    符号が正の環＝陸、負の環＝水域になる。
    これをやらないと運河や埋立地の形が描けず、地図にならない。"""
    minLo, minLa, maxLo, maxLa = out["bbox"]
    # 少しだけ広げた矩形で閉じる (画面外の継ぎ目を見せないため)
    m = 0.0008
    X0, Y0, X1, Y1 = minLo-m, minLa-m, maxLo+m, maxLa+m

    def inside(p): return X0 <= p[0] <= X1 and Y0 <= p[1] <= Y1

    def clipseg(a, b):
        """a-b を矩形で切る。返り値は (残った線分) or None。Liang-Barsky。"""
        x0,y0 = a; x1,y1 = b
        dx, dy = x1-x0, y1-y0
        t0, t1 = 0.0, 1.0
        for p,q in ((-dx, x0-X0),(dx, X1-x0),(-dy, y0-Y0),(dy, Y1-y0)):
            if p == 0:
                if q < 0: return None
            else:
                r = q/p
                if p < 0:
                    if r > t1: return None
                    if r > t0: t0 = r
                else:
                    if r < t0: return None
                    if r < t1: t1 = r
        return ([x0+t0*dx, y0+t0*dy], [x0+t1*dx, y0+t1*dy])

    def clip_way(w):
        """開いた折れ線を矩形で切り、矩形内の部分折れ線の配列にする。"""
        out, cur = [], []
        for i in range(len(w)-1):
            s = clipseg(w[i], w[i+1])
            if not s:
                if cur: out.append(cur); cur = []
                continue
            a, b = s
            if not cur: cur = [a]
            elif abs(cur[-1][0]-a[0]) > 1e-9 or abs(cur[-1][1]-a[1]) > 1e-9:
                out.append(cur); cur = [a]
            cur.append(b)
        if cur: out.append(cur)
        return [c for c in out if len(c) >= 2]

    def area(r):
        s = 0
        for i in range(len(r)):
            x0,y0 = r[i]; x1,y1 = r[(i+1) % len(r)]
            s += x0*y1 - x1*y0
        return s/2

    closed, open_ = [], []
    for w in out["coastline"]:
        if w[0] == w[-1]:
            if any(inside(p) for p in w): closed.append(w)
        else:
            open_ += clip_way(w)

    # 端点が一致するものを繋ぐ
    def key(p): return (round(p[0],7), round(p[1],7))
    chains = list(open_)
    merged = True
    while merged:
        merged = False
        ends = {}
        for i,c in enumerate(chains): ends.setdefault(key(c[0]), []).append(i)
        for i,c in enumerate(chains):
            for j in ends.get(key(c[-1]), []):
                if j != i and chains[j] is not None and chains[i] is not None:
                    chains[i] = c + chains[j][1:]
                    chains[j] = None
                    merged = True
                    break
            if merged: break
        chains = [c for c in chains if c is not None]
        # 閉じたものを分離
        for c in list(chains):
            if len(c) > 2 and key(c[0]) == key(c[-1]):
                closed.append(c[:-1]); chains.remove(c)

    # 矩形の周上パラメータ (反時計回り: 右下→右上→左上→左下)
    def param(p):
        x,y = p
        if abs(x-X1) < 1e-6: return 0 + (y-Y0)/(Y1-Y0)          # 右辺 上向き
        if abs(y-Y1) < 1e-6: return 1 + (X1-x)/(X1-X0)          # 上辺 左向き
        if abs(x-X0) < 1e-6: return 2 + (Y1-y)/(Y1-Y0)          # 左辺 下向き
        return 3 + (x-X0)/(X1-X0)                                # 下辺 右向き
    def corner_pts(a, b):
        """周上パラメータ a から b へ反時計回りに進む途中の角。"""
        cs = [(0.0,[X1,Y0]), (1.0,[X1,Y1]), (2.0,[X0,Y1]), (3.0,[X0,Y0])]
        res = []
        span = (b - a) % 4
        for cp, pt in cs:
            off = (cp - a) % 4
            if 1e-9 < off < span - 1e-9: res.append((off, pt))
        res.sort()
        return [p for _, p in res]

    rings = []
    used = set()
    for i in range(len(chains)):
        if i in used: continue
        ring = []
        cur = i
        for _ in range(len(chains)+1):
            used.add(cur)
            ring += chains[cur]
            pe = param(chains[cur][-1])
            # 海岸線は「左が陸」。終点から矩形周を反時計回りに進んで次の始点へ。
            best, bd = None, 9
            for j in range(len(chains)):
                off = (param(chains[j][0]) - pe) % 4
                if off < bd: bd, best = off, j
            if best is None: break
            ring += corner_pts(pe, param(chains[best][0]))
            if best == i: break
            cur = best
        rings.append(ring)

    land = [r for r in rings if area(r) > 0] + [c for c in closed if area(c) > 0]
    holes = [r for r in rings if area(r) < 0] + [c for c in closed if area(c) < 0]
    out["land"] = [[[round(x,5), round(y,5)] for x,y in r] for r in land]
    out["land_holes"] = [[[round(x,5), round(y,5)] for x,y in r] for r in holes]


def main() -> None:
    b = bbox()
    print(f"範囲: 南{b[0]:.4f} 西{b[1]:.4f} 北{b[2]:.4f} 東{b[3]:.4f}", flush=True)
    data = fetch(query(b))
    els = data.get("elements", [])
    print(f"  要素 {len(els)} 件", flush=True)

    out = {"bbox": [b[1], b[0], b[3], b[2]],   # [西, 南, 東, 北]
           "water": [], "coastline": [], "parks": [], "buildings": [],
           "roads_major": [], "roads_minor": [], "rail": [],
           "attribution": "© OpenStreetMap contributors"}

    MAJOR = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "secondary"}
    for el in els:
        if el.get("type") != "way" or not el.get("geometry"):
            continue
        t = el.get("tags", {}) or {}
        pts = line(el["geometry"])
        if len(pts) < 2:
            continue
        if t.get("natural") == "coastline":
            out["coastline"].append(pts)
        elif t.get("natural") == "water" or t.get("waterway") == "riverbank" \
                or t.get("landuse") == "basin":
            if len(pts) >= MIN_BUILDING_PTS:
                out["water"].append(pts)
        elif t.get("leisure") in ("park", "pitch") or \
                t.get("landuse") in ("grass", "forest", "recreation_ground"):
            if len(pts) >= MIN_BUILDING_PTS:
                out["parks"].append(pts)
        elif "building" in t:
            if len(pts) >= MIN_BUILDING_PTS:
                out["buildings"].append(pts)
        elif "highway" in t:
            key = "roads_major" if t["highway"] in MAJOR else "roads_minor"
            out[key].append(pts)
        elif "railway" in t:
            out["rail"].append(pts)

    build_land(out)

    with open(os.path.normpath(OUT), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    size = os.path.getsize(os.path.normpath(OUT)) / 1024
    print(f"basemap.json 書き出し: {size:.0f} KB", flush=True)
    for k in ("land", "water", "coastline", "parks", "buildings", "roads_major",
              "roads_minor", "rail"):
        print(f"  {k}: {len(out[k])}", flush=True)


if __name__ == "__main__":
    main()
