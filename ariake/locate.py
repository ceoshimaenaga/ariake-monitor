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
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ariake.config import SPOTS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.py")
BASEMAP = os.path.join(os.path.dirname(HERE), "designs", "basemap.json")

# basemap.json 上の名前が config と違うもの。
# 値は (探す名前, 最低限の広さ m2)。広さは同名の小さな別棟を弾くために使う。
MATCH: dict[str, tuple[str, int]] = {
    # OSM はビッグサイトを棟ごとに分けている。イラストにしている逆ピラミッドは
    # 会議棟なので、そこに合わせる。
    "bigsight": ("会議棟", 5000),
    "ariake_arena": ("有明アリーナ", 8000),
    "ariake_coliseum": ("有明コロシアム", 8000),
    "garden_theater": ("東京ガーデンシアター", 3000),
    "ariake_garden": ("有明ガーデン", 5000),
    "ariake_tennis_forest": ("有明テニスの森", 0),
    "ganken_ariake": ("がん研", 5000),
    "aeon_shinonome": ("イオン", 3000),
    "toyosu_market": ("千客万来", 3000),
    "lalaport_toyosu": ("ららぽーと豊洲", 10000),
    "miraikan": ("日本科学未来館", 3000),
    # フジテレビ本社は FCG ビル。"フジテレビ" だと湾岸スタジオを掴む。
    "fujitv": ("FCGビル", 5000),
    "aquacity": ("アクアシテイ", 5000),      # OSM 上の表記ゆれ (シテイ)
    "decks": ("デックス東京ビーチ", 5000),
    "toyosu_gururi": ("豊洲ぐるり公園", 0),
    # キッザニア東京はららぽーと豊洲の建物の中にある施設なので、同じ建物に合わせる
    "kidzania": ("ららぽーと豊洲", 10000),
    "ariake_sports": ("有明スポーツセンター", 1000),
    "teamlab_planets": ("チームラボ プラネッツ", 1000),
    "izumi_spa": ("泉天空の湯", 1000),
    "aeon_ariake": ("イオンスタイル", 5000),
    "odaiba_beach": ("お台場海浜公園", 0),
    "shiokaze": ("潮風公園", 0),
    # 以下は OSM に名前が見つからないので触らない:
    #   有明GYM-EX / 有明四季劇場 / 東京国際クルーズターミナル
    #   (クルーズターミナルは近くに "青海客船ターミナル" があるが、
    #    同じものか確かめられないので動かさない)
}


# 名前だけを取りに行く軽い問い合わせ先。基盤地図の取得より桁違いに軽いので、
# Overpass が混んでいても通りやすい。
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.osm.jp/api/interpreter",
]


def fetch_some(bbox: list[float], names: list[str]) -> list[dict]:
    """名前を指定して、その施設だけを引く。

    範囲内の名前付きを全部取る問い合わせは、Overpass が混んでいると
    いつまでも返ってこない。残り数件を埋めるだけなら、名前で絞った方が
    圧倒的に軽い。点でも面でも拾う。
    """
    w, s_, e, n = bbox[0], bbox[1], bbox[2], bbox[3]
    box = f"({s_},{w},{n},{e})"
    pat = "|".join(x.replace('"', '\\"') for x in names)
    q = (f'[out:json][timeout:120];nwr["name"~"{pat}"]{box};out center tags;')
    last = None
    for rnd in range(3):
        for url in ENDPOINTS:
            try:
                print(f"  名前で照会 ({rnd + 1}周目): {url}", flush=True)
                req = urllib.request.Request(
                    url, data=("data=" + q).encode("utf-8"),
                    headers={"User-Agent": "ariake-monitor/1.0 (locate)"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.loads(r.read().decode("utf-8")).get("elements", [])
            except Exception as exc:                      # noqa: BLE001
                print(f"  ! {exc}", flush=True)
                last = exc
        if rnd < 2:
            time.sleep(15 * (rnd + 1))
    raise SystemExit(f"名前を取得できませんでした: {last}")


def fetch_names(bbox: list[float]) -> list[dict]:
    """名前の付いた建物と公園だけを取る。

    基盤地図には道路も海岸線も入っていて重く、混雑時に 502/504 で落ちる。
    ここで欲しいのは「名前と、だいたいの位置」だけなので、対象を絞って
    軽く取り、正確な位置は手元の輪郭に当てて決める。
    """
    w, s_, e, n = bbox[0], bbox[1], bbox[2], bbox[3]
    box = f"({s_},{w},{n},{e})"
    # 施設は建物として描かれているとは限らず、建物の中の点 (POI) として
    # 登録されていることが多い。劇場やジムや温浴施設はたいていこちら。
    # 点も取って、あとで建物の輪郭に吸着させる。
    q = ("[out:json][timeout:150];("
         f'way["name"]["building"]{box};'
         f'relation["name"]["building"]{box};'
         f'way["name"]["leisure"]{box};'
         f'relation["name"]["leisure"]{box};'
         f'node["name"]["amenity"]{box};'
         f'node["name"]["shop"]{box};'
         f'node["name"]["leisure"]{box};'
         f'node["name"]["tourism"]{box};'
         f'node["name"]["office"]{box};'
         f'node["name"]["building"]{box};'
         ");out center tags;")
    last = None
    for rnd in range(3):
        for url in ENDPOINTS:
            try:
                print(f"  名前を取得 ({rnd + 1}周目): {url}", flush=True)
                req = urllib.request.Request(
                    url, data=("data=" + q).encode("utf-8"),
                    headers={"User-Agent": "ariake-monitor/1.0 (locate)"})
                with urllib.request.urlopen(req, timeout=180) as r:
                    return json.loads(r.read().decode("utf-8")).get("elements", [])
            except Exception as exc:                      # noqa: BLE001
                print(f"  ! {exc}", flush=True)
                last = exc
        if rnd < 2:
            time.sleep(20 * (rnd + 1))
    raise SystemExit(f"名前を取得できませんでした: {last}")


def ring_centre(ring: list[list[float]]) -> tuple[float, float]:
    """輪郭の重心 (緯度, 経度)。重心が外に出る形では頂点の平均に逃がす。"""
    a = 0.0; cx = 0.0; cy = 0.0
    for i in range(len(ring)):
        x0, y0 = ring[i]; x1, y1 = ring[(i + 1) % len(ring)]
        f = x0 * y1 - x1 * y0
        a += f; cx += (x0 + x1) * f; cy += (y0 + y1) * f
    avg = (sum(p[1] for p in ring) / len(ring),
           sum(p[0] for p in ring) / len(ring))
    if abs(a) < 1e-12:
        return avg
    c = (cy / (3 * a), cx / (3 * a))
    return c if inside(c, ring) else avg


def inside(pt: tuple[float, float], ring: list[list[float]]) -> bool:
    y, x = pt; ins = False; n = len(ring); j = n - 1
    for i in range(n):
        xi, yi = ring[i]; xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and \
                (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
            ins = not ins
        j = i
    return ins


def ring_m2(ring: list[list[float]]) -> float:
    la = sum(p[1] for p in ring) / len(ring)
    k = 111320 * math.cos(math.radians(la))
    a = 0.0
    for i in range(len(ring)):
        x0, y0 = ring[i]; x1, y1 = ring[(i + 1) % len(ring)]
        a += (x0 * k) * (y1 * 111320) - (x1 * k) * (y0 * 111320)
    return abs(a) / 2


def snap(base: dict, els: list[dict]) -> list[dict]:
    """取ってきた要素を、手元の輪郭に吸着させる (fetch と分けてある)。"""
    rings = [(r, ring_centre(r), ring_m2(r), "building") for r in base["buildings"]]
    rings += [(r, ring_centre(r), ring_m2(r), "park") for r in base["parks"]]
    out = []
    for el in els:
        nm = (el.get("tags") or {}).get("name")
        if not nm:
            continue
        c = el.get("center") or ({"lat": el.get("lat"), "lon": el.get("lon")}
                                 if el.get("lat") else None)
        if not c:
            continue
        pt = (c["lat"], c["lon"])
        hit = next((t for t in rings if inside(pt, t[0])), None)
        if hit is None:
            near = min(rings, key=lambda t: metres(pt, t[1]), default=None)
            if near is not None and metres(pt, near[1]) <= 60:
                hit = near
        if hit is None:
            out.append({"name": nm, "kind": "point",
                        "lat": round(pt[0], 6), "lng": round(pt[1], 6), "m2": 0})
        else:
            out.append({"name": nm, "kind": hit[3],
                        "lat": round(hit[1][0], 6), "lng": round(hit[1][1], 6),
                        "m2": round(hit[2])})
    return out


def attach_names(base: dict) -> list[dict]:
    """取ってきた名前を、手元の輪郭に貼り付ける。

    Overpass の out center は外接矩形の中心なので、L字の建物では
    建物の外に落ちる。その点を含む輪郭、無ければ一番近い輪郭を選び、
    位置はその輪郭の重心にする。こうすると、印は必ず地図に描いてある
    建物の上に乗る。
    """
    els = fetch_names(base["bbox"])
    print(f"  名前付き {len(els)} 件", flush=True)
    rings = [(r, ring_centre(r), ring_m2(r), "building") for r in base["buildings"]]
    rings += [(r, ring_centre(r), ring_m2(r), "park") for r in base["parks"]]
    out = []
    for el in els:
        nm = (el.get("tags") or {}).get("name")
        if not nm:
            continue
        c = el.get("center") or ({"lat": el.get("lat"), "lon": el.get("lon")}
                                 if el.get("lat") else None)
        if not c:
            continue
        pt = (c["lat"], c["lon"])
        # その点を含む輪郭 → 近くの輪郭 → どれにも当たらなければ点そのもの。
        # 当たらないものを捨てると、建物として描かれていない施設 (公園の
        # 相手や埠頭の施設など) が永久に直らないので、点のまま残す。
        hit = next((t for t in rings if inside(pt, t[0])), None)
        if hit is None:
            near = min(rings, key=lambda t: metres(pt, t[1]), default=None)
            if near is not None and metres(pt, near[1]) <= 60:
                hit = near
        if hit is None:
            out.append({"name": nm, "kind": "point",
                        "lat": round(pt[0], 6), "lng": round(pt[1], 6), "m2": 0})
        else:
            out.append({"name": nm, "kind": hit[3],
                        "lat": round(hit[1][0], 6), "lng": round(hit[1][1], 6),
                        "m2": round(hit[2])})
    return out


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
    near = [n for n in named
            if want in n["name"] and metres(cur, (n["lat"], n["lng"])) < 2000]
    # 広さの下限は、面のある候補を選り分けるためのもの。面がある候補が
    # 一つも残らないなら、点として登録されている施設なので下限は外す。
    cands = [n for n in near if n["m2"] >= floor] or near
    if not cands:
        return None
    # 300m2 未満の輪郭は、施設本体ではなく案内板やトイレのことが多い。
    # 広さの手がかりとしては点と同じ扱いにして、公園 → 点 → 建物 の順で選ぶ。
    # 名前が完全に一致するものを最優先にする。部分一致だけで大きさ順に
    # 選ぶと、"イオン" が有明のイオンスタイルを、"会議棟" が会議棟地下
    # 駐車場を、"潮風公園" が潮風公園案内図を掴んでしまう。
    rank = {"park": 0, "point": 1, "building": 2}
    cands.sort(key=lambda n: (0 if n["name"] == want else 1,
                              -(n["m2"] if n["m2"] >= 300 else 0),
                              rank.get(n["kind"], 3)))
    top = cands[0]
    return {"lat": top["lat"], "lng": top["lng"], "m2": top["m2"],
            "kind": top["kind"], "name": top["name"], "n": len(cands),
            "dist": metres(cur, (top["lat"], top["lng"]))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patch", action="store_true", help="config.py を書き換える")
    ap.add_argument("--fetch-names", action="store_true",
                    help="名前を取り直して basemap.json に貼り付ける")
    ap.add_argument("--find", default="",
                    help="この名前 (| 区切り) だけを引いて basemap.json に足す")
    args = ap.parse_args()

    base = json.load(open(BASEMAP, encoding="utf-8"))
    named = base.get("named") or []
    if args.find:
        got = snap(base, fetch_some(base["bbox"], args.find.split("|")))
        have = {(x["name"], x["lat"], x["lng"]) for x in named}
        add = [g for g in got if (g["name"], g["lat"], g["lng"]) not in have]
        for g in sorted(add, key=lambda x: -x["m2"]):
            print(f"  + {g['name'][:34]:36s} {g['kind']:8s} {g['m2']:>8,} "
                  f"{g['lat']},{g['lng']}", flush=True)
        named += add
        base["named"] = named
        json.dump(base, open(BASEMAP, "w", encoding="utf-8"),
                  ensure_ascii=False, separators=(",", ":"))
        print(f"basemap.json に追加: {len(add)} 件", flush=True)
    elif args.fetch_names or not named:
        named = attach_names(base)
        base["named"] = named
        json.dump(base, open(BASEMAP, "w", encoding="utf-8"),
                  ensure_ascii=False, separators=(",", ":"))
        print(f"basemap.json に名前を貼り付け: {len(named)} 件", flush=True)
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
