"""公開サイト (_site/) を組み立てる。

designs/5-atlas.html を唯一の原本として扱い、公開用に
  - 相対パス (../ariake.json など) を配信時のフラットな配置に合わせる
  - 検索避け (noindex) を外す
だけを行う。原本を二重に持たないので、デザインを直せば公開ページも直る。

GitHub Pages のワークフローから呼ばれる。手元でも
    python ariake/build_site.py && python -m http.server -d _site
で同じものを確認できる。
"""
from __future__ import annotations

import os
import re
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_site")

PAGE = "designs/5-atlas.html"
# (コピー元, 配信パス)
ASSETS = [
    ("ariake-common.js", "ariake-common.js"),
    ("ariake-settings.js", "ariake-settings.js"),
    ("ariake.json", "ariake.json"),
    ("designs/basemap.json", "basemap.json"),
]
ASSET_DIRS = [("designs/icons/png", "icons/png")]


def build_page() -> str:
    with open(os.path.join(ROOT, PAGE), encoding="utf-8") as f:
        html = f.read()
    # designs/ から一段上を見ていたものを、配信時は同じ階層に置く
    html = html.replace('src="../ariake-', 'src="ariake-')
    html = html.replace('A.load("../ariake.json")', 'A.load("ariake.json")')
    # 公開ページなので検索避けは外す
    html = re.sub(r'\s*<meta name="robots"[^>]*>', "", html)
    # タブに出る名前は案の番号ではなくサービス名にする
    html = html.replace(
        "<title>有明 混雑モニター — 案5 ATLAS</title>",
        "<title>有明 混雑マップ</title>\n"
        '<meta name="description" content="有明・豊洲・お台場の混雑状況と3日先までの'
        '予測を、実際の地形の地図の上に表示します。">',
    )
    return html


def main() -> None:
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_page())

    for src, dst in ASSETS:
        shutil.copy2(os.path.join(ROOT, src), os.path.join(OUT, dst))
    for src, dst in ASSET_DIRS:
        shutil.copytree(os.path.join(ROOT, src), os.path.join(OUT, dst))

    # Jekyll に触らせない (_ で始まる名前などを消されないように)
    open(os.path.join(OUT, ".nojekyll"), "w").close()

    total = sum(
        os.path.getsize(os.path.join(dp, n))
        for dp, _, ns in os.walk(OUT) for n in ns
    )
    print(f"_site/ を作成: {total / 1024 / 1024:.1f} MB", flush=True)


if __name__ == "__main__":
    main()
