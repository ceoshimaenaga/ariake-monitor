"""各スポットの実際の位置を OpenStreetMap から取り、config.py の座標と突き合わせる。

config.py の緯度経度は手入力の4桁 (緯度で約11m、経度で約9m の刻み) なので、
地図を拡大すると建物とマーカーがずれる。ここで実測値と比べて、ずれている
ものを見つけ、貼り付けられる形で出力する。

    python ariake/locate.py          # ずれを一覧する
    python ariake/locate.py --patch  # config.py の座標を実測値で書き換える

名前で引き当てられなかったものは触らない (誤った場所に動かさないため)。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ariake.config import SPOTS  # noqa: E402

OVERPASS = "https://overpass-api.de/api/interpreter"
CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")

# 有明・豊洲・お台場を含む範囲 (南, 西, 北, 東)
BBOX = (35.6050, 139.7600, 35.6700, 139.8150)

# OSM 上の名前が config と違うもの、名前だけでは引けないものを補う。
# 値は (OSM で探す名前, 種別の絞り込み) 。None は名前をそのまま使う。
ALIASES: dict[str, str] = {
    "bigsight": "東京ビッグサイト",
    "shiki_ariake": "有明四季劇場",
    "izumi_spa": "泉天空の湯 有明ガーデン",
    "aeon_ariake": "イオンスタイル有明ガーデン",
    "aeon_shinonome": "イオン東雲店",
    "toyosu_market": "豊洲市場",
    "lalaport_toyosu": "アーバンドック ららぽーと豊洲",
    "kidzania": "キッザニア東京",
    "teamlab_planets": "チームラボプラネッツ TOKYO DMM",
    "miraikan": "日本科学未来館",
    "fujitv": "フジテレビジョン",
    "aquacity": "アクアシティお台場",
    "decks": "デックス東京ビーチ",
    "cruise_terminal": "東京国際クルーズターミナル",
    "odaiba_beach": "お台場海浜公園",
    "shiokaze": "潮風公園",
    "toyosu_gururi": "豊洲ぐるり公園",
    "ganken_ariake": "がん研究会有明病院",
    "ariake_sports": "有明スポーツセンター",
    "ariake_tennis_forest": "有明テニスの森公園",
    "st_tokyo_bigsight": "東京ビッグサイト",
    "st_kokusai_tenjijo": "国際展示場",
    "st_ariake": "有明",
    "st_ariake_tennis": "有明テニスの森",
}


def query() -> str:
    """範囲内の「名前が付いているもの」を一度に全部取る。

    名前ごとに正規表現で引くと Overpass 側が重くなって時間切れになるので、
    問い合わせは1回だけにして、名前の突き合わせは手元でやる。
    """
    s, w, n, e = BBOX
    box = f"({s},{w},{n},{e})"
    return (
        "[out:json][timeout:180];("
        f'way["name"]{box};'
        f'relation["name"]{box};'
        f'node["name"]["railway"="station"]{box};'
        f'node["name"]["amenity"]{box};'
        f'node["name"]["shop"]{box};'
        f'node["name"]["leisure"]{box};'
        f'node["name"]["tourism"]{box};'
        ");out center tags;"
    )


def fetch(q: str) -> dict:
    req = urllib.request.Request(
        OVERPASS, data=("data=" + q).encode("utf-8"),
        headers={"User-Agent": "ariake-monitor/1.0 (locate)"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as exc:                      # noqa: BLE001
            if attempt == 3:
                raise
            print(f"  再試行 {attempt + 1}: {exc}", flush=True)
            time.sleep(8 * (attempt + 1))
    return {}


def centre(el: dict) -> tuple[float, float] | None:
    if "lat" in el and "lon" in el:
        return el["lat"], el["lon"]
    c = el.get("center")
    if c:
        return c["lat"], c["lon"]
    return None


def metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    import math
    dy = (a[0] - b[0]) * 111320
    dx = (a[1] - b[1]) * 111320 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def best(elements: list[dict], want: str, cur: tuple[float, float],
         station: bool) -> dict | None:
    """名前が一致するもののうち、今の座標に一番近いものを選ぶ。

    同名の別施設 (系列店など) に飛ばないよう、距離も見る。
    面 (way/relation) を点 (node) より優先する。建物そのものの重心が欲しいため。
    """
    cands = []
    for el in elements:
        tags = el.get("tags") or {}
        nm = tags.get("name", "")
        if want not in nm:
            continue
        # 駅は駅そのものだけ。同名のバス停や出入口に引っ張られないようにする。
        if station and tags.get("railway") != "station":
            continue
        if not station and tags.get("railway") == "station":
            continue
        p = centre(el)
        if not p:
            continue
        d = metres(cur, p)
        if d > 1200:                       # 1.2km 以上離れていたら別物とみなす
            continue
        rank = 0 if el["type"] in ("way", "relation") else 1
        cands.append((rank, d, el, p))
    if not cands:
        return None
    cands.sort(key=lambda t: (t[0], t[1]))
    r, d, el, p = cands[0]
    return {"lat": round(p[0], 6), "lng": round(p[1], 6), "dist": d,
            "osm": f"{el['type']}/{el['id']}",
            "name": (el.get("tags") or {}).get("name", "")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patch", action="store_true", help="config.py を書き換える")
    args = ap.parse_args()

    targets = {sid: ALIASES.get(sid, sp["name"]) for sid, sp in SPOTS.items()
               if sp.get("lat") and sp.get("lng")}
    # 道路など、建物を持たないものは対象外
    targets = {k: v for k, v in targets.items() if not k.startswith("road")}


    print("Overpass 照会 (1回)", flush=True)
    els = fetch(query()).get("elements", [])
    print(f"  名前付き要素 {len(els)} 件", flush=True)

    found: dict[str, dict] = {}
    for sid, want in targets.items():
        cur = (SPOTS[sid]["lat"], SPOTS[sid]["lng"])
        hit = best(els, want, cur, sid.startswith("st_"))
        if hit:
            found[sid] = hit

    print("\n--- ずれの大きい順 ---", flush=True)
    rows = sorted(found.items(), key=lambda kv: -kv[1]["dist"])
    for sid, h in rows:
        print(f"{h['dist']:7.1f}m  {sid:22s} {SPOTS[sid]['name']}"
              f"  → {h['lat']}, {h['lng']}  [{h['osm']} {h['name']}]", flush=True)
    missing = sorted(set(targets) - set(found))
    if missing:
        print("\n見つからず (触らない): " + ", ".join(missing), flush=True)

    if not args.patch:
        return

    src = open(CONFIG, encoding="utf-8").read()
    changed = 0
    for sid, h in found.items():
        if h["dist"] < 5:                   # 5m 未満は誤差なので触らない
            continue
        # そのスポットの定義ブロックの中だけを書き換える
        m = re.search(r'("' + re.escape(sid) + r'":\s*\{)(.*?)(\n    \},)', src, re.S)
        if not m:
            print(f"  ブロックが見つからない: {sid}", flush=True)
            continue
        body = m.group(2)
        nb, n1 = re.subn(r'"lat":\s*-?[\d.]+', f'"lat": {h["lat"]}', body, count=1)
        nb, n2 = re.subn(r'"lng":\s*-?[\d.]+', f'"lng": {h["lng"]}', nb, count=1)
        if n1 and n2:
            src = src[:m.start(2)] + nb + src[m.end(2):]
            changed += 1
    open(CONFIG, "w", encoding="utf-8").write(src)
    print(f"\nconfig.py を更新: {changed} 件", flush=True)


if __name__ == "__main__":
    main()
