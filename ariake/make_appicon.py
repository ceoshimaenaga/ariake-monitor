"""アプリのアイコンを、自前の地図から作る。

ホーム画面に置かれるアイコンなので、絵として描き起こすより
「このアプリが出すもの」そのものを小さくした方が分かりやすい。
有明の陸地と運河の形は特徴があるので、それだけで identity になる。

    python ariake/make_appicon.py

designs/app/icon-{192,512,1024}.png と、角丸なしの maskable を書き出す。
Android はアイコンを丸や角丸に切り抜くので、切られて困らない余白
(safe zone) を持った maskable 版を別に用意する。
"""
from __future__ import annotations

import json
import math
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASEMAP = os.path.join(ROOT, "designs", "basemap.json")
OUT = os.path.join(ROOT, "designs", "app")

# 人流デザインの色。アイコンと中身の見た目を合わせる。
# 小さく表示されるので、地図そのものより陸と海の差を強く付ける。
# 192px のホーム画面アイコンで形が潰れないことを優先する。
SEA = (8, 13, 24)
LAND = (41, 41, 54)
SHORE = (92, 120, 150)
ROAD = (104, 104, 130)
HOT = (255, 216, 115)      # --flow-5
WARM = (227, 95, 55)       # --flow-4
MID = (140, 59, 164)       # --flow-3

# 有明の中心あたり。アイコンに収める範囲 (度)
CENTER = (35.6365, 139.7930)
SPAN = 0.021


def draw(size: int, inset: float) -> Image.Image:
    """inset は余白の割合。maskable では大きめに取って、切られても残す。"""
    b = json.load(open(BASEMAP, encoding="utf-8"))
    im = Image.new("RGB", (size, size), SEA)
    d = ImageDraw.Draw(im)

    usable = size * (1 - inset * 2)
    kx = math.cos(math.radians(CENTER[0]))
    scale = usable / SPAN

    def px(lng: float, lat: float) -> tuple[float, float]:
        return (size / 2 + (lng - CENTER[1]) * kx * scale,
                size / 2 - (lat - CENTER[0]) * scale)

    def poly(ring, fill):
        pts = [px(p[0], p[1]) for p in ring]
        if len(pts) >= 3:
            d.polygon(pts, fill=fill)

    for r in b["land"]:
        poly(r, LAND)
    for r in b["water"]:
        poly(r, SEA)
    # 海岸線。小さいと陸と海の境が消えるので、線でも示す
    sw = max(1, round(size / 220))
    for way in b["coastline"]:
        pts = [px(p[0], p[1]) for p in way]
        if len(pts) >= 2:
            d.line(pts, fill=SHORE, width=sw)

    # 幹線道路。有明の特徴である斜めの格子が出る
    w = max(1, round(size / 180))
    for way in b["roads_major"]:
        pts = [px(p[0], p[1]) for p in way]
        if len(pts) >= 2:
            d.line(pts, fill=ROAD, width=w)

    # 人流の芯。ビッグサイト → 国際展示場 → 有明ガーデンの帯を、
    # 実際の道路の上に重ねて「混んでいる所が光る」という中身を示す。
    spine = [(35.6302, 139.7941), (35.6344, 139.7918), (35.6384, 139.7931)]
    sp = [px(lng, lat) for lat, lng in spine]
    d.line(sp, fill=MID, width=max(3, round(size / 36)), joint="curve")
    d.line(sp, fill=WARM, width=max(2, round(size / 52)), joint="curve")
    d.line(sp, fill=HOT, width=max(1, round(size / 90)), joint="curve")
    for p in sp:
        r = max(2, size / 46)
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=HOT)
    return im


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    # ふつうのアイコン。余白は控えめ
    for n in (192, 512, 1024):
        draw(n, 0.06).save(os.path.join(OUT, f"icon-{n}.png"), optimize=True)
    # Android が丸や角丸に切り抜く用。中身を内側 80% に収める
    for n in (192, 512):
        draw(n, 0.18).save(os.path.join(OUT, f"maskable-{n}.png"), optimize=True)
    # Safari のホーム画面用 (角丸は OS が付けるので四角のまま)
    draw(180, 0.06).save(os.path.join(OUT, "apple-touch-icon.png"), optimize=True)
    for f in sorted(os.listdir(OUT)):
        print(f"  {f}: {os.path.getsize(os.path.join(OUT, f)) // 1024} KB", flush=True)


if __name__ == "__main__":
    main()
