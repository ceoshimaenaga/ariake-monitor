# -*- coding: utf-8 -*-
"""生成した建物イラスト(SVG)を地図で使える形に整える。

やること:
  1. 生成物に付いてくる白い背景の矩形を取り除く (地図の上に重ねるため)
  2. 色を温かみのある無彩色に置き換える

2 の理由: 地図上で色は「混雑度」を表す軸として使っている。建物まで同じ青系だと
色が二役になって読めなくなるので、建物は色を持たない「もの」として描き、
混雑は建物の背後の面と輪に任せる。

使い方:
    python ariake/prepare_icons.py        # designs/icons/*.svg → designs/icons/prep/
"""

from __future__ import annotations

import os
import re
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "designs", "icons")
DST = os.path.join(SRC, "prep")

# 生成時に指定した4色 → 温かみのある無彩色 (明るいほど手前・屋根面)
RECOLOR = {
    (24, 79, 149):   "#57554c",   # 最も濃い面 → 影側
    (57, 135, 229):  (154, 151, 137),  # 中間面
    (158, 197, 244): (214, 211, 198),  # 明るい面
    (195, 194, 183): (240, 238, 229),  # 最も明るい面・地面
}
RECOLOR = {
    (24, 79, 149):   (87, 85, 76),
    (57, 135, 229):  (154, 151, 137),
    (158, 197, 244): (214, 211, 198),
    (195, 194, 183): (240, 238, 229),
}

RE_RGB = re.compile(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)")
# ビューボックス全体を覆う白い矩形 (背景)
RE_BG = re.compile(
    r'<path[^>]*fill="rgb\(255,\s*255,\s*255\)"[^>]*d="M 0 0 L (\d+) 0 L \1 \1 L 0 \1 L 0 0 z"\s*/>')


def nearest(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """生成のブレで微妙に違う色が出るので、最も近い指定色に寄せてから置換する。"""
    best, bd = None, None
    for k, v in RECOLOR.items():
        d = sum((a - b) ** 2 for a, b in zip(k, rgb))
        if bd is None or d < bd:
            best, bd = v, d
    return best


def prepare(text: str) -> str:
    text, n = RE_BG.subn("", text, count=1)
    if not n:   # 書式が違う場合に備えて、全面を覆う白パスを緩く探す
        text = re.sub(r'<path[^>]*fill="rgb\(255,\s*255,\s*255\)"[^>]*d="M 0 0 [^"]*z"\s*/>',
                      "", text, count=1)

    def sub(m):
        rgb = tuple(int(x) for x in m.groups())
        if rgb == (255, 255, 255):
            return "rgb(255,255,255)"
        r, g, b = nearest(rgb)
        return f"rgb({r},{g},{b})"

    return RE_RGB.sub(sub, text)


def main() -> None:
    os.makedirs(DST, exist_ok=True)
    names = sorted(f for f in os.listdir(SRC) if f.endswith(".svg"))
    if not names:
        print("designs/icons に SVG がありません", file=sys.stderr)
        return
    for name in names:
        src = os.path.join(SRC, name)
        with open(src, encoding="utf-8") as f:
            text = f.read()
        out = prepare(text)
        with open(os.path.join(DST, name), "w", encoding="utf-8") as f:
            f.write(out)
        print(f"  {name}: {len(text):,} → {len(out):,} バイト "
              f"(背景除去 {'済' if len(out) < len(text) else '対象なし'})")
    print(f"{len(names)} 件を {DST} に書き出しました")


if __name__ == "__main__":
    main()
