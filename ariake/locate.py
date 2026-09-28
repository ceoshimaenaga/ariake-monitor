"""スポットの座標を、地図に描いている建物の輪郭に合わせる。

config.py の緯度経度は手入力の4桁で、実際の建物と最大1km ずれていた。
地図を拡大すると、マーカーが更地に浮いて見える。

合わせ先は basemap.json の `named` (地図として描いている輪郭そのものに
名前を付けたもの)。印と建物が同じ出どころになるので、原理的にずれない。
Overpass には問い合わせないので、混雑で失敗することもない。

    python ariake/locate.py          # ずれを一覧する
    python ariake/locate.py --patch  # config.py の座標を書き換える

名前で引き当てられなかったものは触らない (誤った場所に動かさないため)。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ariake.config import SPOTS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.py")
BASEMAP = os.path.join(os.path.dirname(HERE), "designs", "basemap.json")

# basemap.json 上の名前が config と違うもの。
# 値は (探す名前, 最低限の広さ m2)。広さは同名の小さな別棟を弾くために使う。
MATCH: dict[str, tuple[str, int]] = {
    "bigsight": ("東京ビッグサイト", 20000),
    "ariake_arena": ("有明アリーナ", 8000),
    "ariake_coliseum": ("有明コロシアム", 8000),
    "garden_theater": ("東京ガーデンシアター", 3000),
    "shiki_ariake": ("有明四季劇場", 1500),
    "gymex": ("有明GYM-EX", 1500),
    "ariake_garden": ("有明ガーデン", 5000),
    "ariake_tennis_forest": ("有明テニスの森", 0),
    "ariake_sports": ("有明スポーツセンター", 1500),
    "ganken_ariake": ("がん研", 5000),
    "izumi_spa": ("泉天空の湯", 0),
    "aeon_ariake": ("イオンスタイル", 0),
    "aeon_shinonome": ("イオン", 3000),
    "toyosu_market": ("豊洲市場", 10000),
    "lalaport_toyosu": ("ららぽーと豊洲", 10000),
    "kidzania": ("キッザニア", 0),
    "teamlab_planets": ("チームラボ", 0),
    "miraikan": ("日本科学未来館", 3000),
    "fujitv": ("フジテレビ", 3000),
    "aquacity": ("アクアシティ", 5000),
    "decks": ("デックス東京ビーチ", 5000),
    "cruise_terminal": ("東京国際クルーズターミナル", 0),
    "odaiba_beach": ("お台場海浜公園", 0),
    "shiokaze": ("潮風公園", 0),
    "toyosu_gururi": ("豊洲ぐるり公園", 0),
}


def metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    dy = (a[0] - b[0]) * 111320
    dx = (a[1] - b[1]) * 111320 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def pick(named: list[dict], want: str, floor: int,
         cur: tuple[float, float]) -> dict | None:
    """名前を含む輪郭のうち、一番広いものを選ぶ。

    今の座標は当てにならない (最大1km ずれている) ので、距離では選ばない。
    ただし別の街の同名施設を掴まないよう、2km を超えるものは除く。
    """
    cands = [n for n in named
             if want in n["name"] and n["m2"] >= floor
             and metres(cur, (n["lat"], n["lng"])) < 2000]
    if not cands:
        return None
    cands.sort(key=lambda n: -n["m2"])
    top = cands[0]
    return {"lat": top["lat"], "lng": top["lng"], "m2": top["m2"],
            "kind": top["kind"], "name": top["name"], "n": len(cands),
            "dist": metres(cur, (top["lat"], top["lng"]))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patch", action="store_true", help="config.py を書き換える")
    args = ap.parse_args()

    base = json.load(open(BASEMAP, encoding="utf-8"))
    named = base.get("named") or []
    if not named:
        print("basemap.json に名前付きの輪郭がありません。"
              "先に basemap ワークフローを回してください。", flush=True)
        raise SystemExit(1)
    print(f"名前付きの輪郭 {len(named)} 件", flush=True)

    found: dict[str, dict] = {}
    for sid, (want, floor) in MATCH.items():
        sp = SPOTS.get(sid)
        if not sp or not sp.get("lat"):
            continue
        hit = pick(named, want, floor, (sp["lat"], sp["lng"]))
        if hit:
            found[sid] = hit

    print("\n--- ずれの大きい順 ---", flush=True)
    for sid, h in sorted(found.items(), key=lambda kv: -kv[1]["dist"]):
        print(f"{h['dist']:7.1f}m  {sid:22s} {SPOTS[sid]['name']}"
              f"  → {h['lat']}, {h['lng']}"
              f"  {h['kind']}{h['m2']:,}m2 候補{h['n']}  [{h['name']}]", flush=True)
    missing = sorted(set(MATCH) - set(found))
    if missing:
        print("\n見つからず (触らない): " + ", ".join(missing), flush=True)

    if not args.patch:
        return

    src = open(CONFIG, encoding="utf-8").read()
    changed = 0
    for sid, h in found.items():
        if h["dist"] < 5:                   # 5m 未満は誤差なので触らない
            continue
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
