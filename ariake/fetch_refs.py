# -*- coding: utf-8 -*-
"""建物の参照写真を集める。

イラストを実物に似せるには写真を見る必要があるが、実行環境から外部サイトへ
出られないため、ネットワークのある環境 (GitHub Actions) でこれを走らせる。

画像URLならそのまま保存し、ページのURLなら og:image などから写真を取り出す。

使い方:
    python ariake/fetch_refs.py "name=URL" "name=URL" ...
"""

from __future__ import annotations

import json
import os
import re
import sys
from urllib.parse import urljoin, urlparse

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir,
                   "designs", "refs")
UA = "Mozilla/5.0 (compatible; AriakeCongestionMonitor/1.0)"
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")

# 写真として使えないもの。
# 位置図(Map_..._svg.png)や広告バナーを掴んでしまう事故が実際に起きたので、
# 見つけ次第そういうものは弾く。
SKIP = re.compile(
    r"(logo|icon|favicon|sprite|banner|btn_|button|placeholder|"
    r"map[_-]|locator|\.svg|campaign|sneaker|pickup|topics?_)", re.I)


WIKI_API = "https://{lang}.wikipedia.org/w/api.php"


def wikipedia_lead_image(url: str) -> str | None:
    """Wikipedia の記事なら、代表画像 (pageimages) を取る。

    og:image を素直に拾うと、記事によっては位置図を掴んでしまうため。
    """
    m = re.match(r"https://([a-z]+)\.wikipedia\.org/wiki/([^?#]+)", url)
    if not m:
        return None
    lang, title = m.group(1), m.group(2)
    from urllib.parse import unquote
    import requests
    try:
        r = requests.get(WIKI_API.format(lang=lang), timeout=40,
                         headers={"User-Agent": UA},
                         params={"action": "query", "prop": "pageimages",
                                 "piprop": "original", "format": "json",
                                 "titles": unquote(title)})
        pages = (r.json().get("query") or {}).get("pages") or {}
        for pg in pages.values():
            src = (pg.get("original") or {}).get("source")
            if src and not SKIP.search(src):
                return src
    except Exception as e:                                # noqa: BLE001
        print(f"    (Wikipedia API 失敗: {e})", flush=True)
    return None


def get(url: str):
    import requests
    return requests.get(url, headers={"User-Agent": UA, "Accept-Language": "ja"},
                        timeout=60, allow_redirects=True)


def image_urls_from_html(html: str, base: str) -> list[str]:
    """og:image を最優先に、ページ内の写真らしいURLを拾う。"""
    urls: list[str] = []
    for pat in (r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
                r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)'):
        urls += re.findall(pat, html, re.I)
    # 本文中の画像 (大きそうなものを優先するため出現順に集める)
    for m in re.findall(r'<img[^>]+src=["\']([^"\']+)', html, re.I):
        urls.append(m)
    out, seen = [], set()
    for u in urls:
        a = urljoin(base, u.strip())
        low = a.lower().split("?")[0]
        if not low.endswith(IMG_EXT) or SKIP.search(a) or a in seen:
            continue
        seen.add(a)
        out.append(a)
    return out


SOURCES = os.path.join(OUT, "sources.json")


def record(name: str, url: str) -> None:
    """どのURLから取った写真かを残す。
    生成時に参照画像として渡し直すのと、出典を辿るのに要る。"""
    try:
        with open(SOURCES, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:                                     # noqa: BLE001
        data = {}
    data[name] = url
    os.makedirs(OUT, exist_ok=True)
    with open(SOURCES, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)


def save(name: str, data: bytes, ctype: str) -> str:
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(
        ctype.split(";")[0].strip(), "jpg")
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{name}.{ext}")
    with open(path, "wb") as f:
        f.write(data)
    return path


def fetch_one(name: str, url: str) -> None:
    lead = wikipedia_lead_image(url)
    if lead:
        print(f"    Wikipedia の代表画像を使用: {lead}", flush=True)
        url = lead
    try:
        r = get(url)
    except Exception as e:                                # noqa: BLE001
        print(f"  × {name}: 取得失敗 {e}", flush=True)
        return
    if r.status_code >= 400:
        print(f"  × {name}: {r.status_code}", flush=True)
        return
    ctype = r.headers.get("Content-Type", "")
    if ctype.startswith("image/"):
        p = save(name, r.content, ctype)
        record(name, r.url)
        print(f"  ○ {name}: {os.path.basename(p)} {len(r.content):,} バイト", flush=True)
        return
    # ページなら写真を探す
    cands = image_urls_from_html(r.text, r.url)
    print(f"  … {name}: ページから画像候補 {len(cands)} 件", flush=True)
    for u in cands[:6]:
        try:
            ir = get(u)
        except Exception:                                 # noqa: BLE001
            continue
        if ir.status_code < 400 and ir.headers.get("Content-Type", "").startswith("image/") \
                and len(ir.content) > 40000:              # 小さすぎるものは写真ではない
            p = save(name, ir.content, ir.headers["Content-Type"])
            record(name, ir.url)
            print(f"  ○ {name}: {os.path.basename(p)} {len(ir.content):,} バイト  ← {ir.url}",
                  flush=True)
            return
    print(f"  × {name}: 使えそうな写真が見つからず", flush=True)


def main() -> None:
    args = [a for a in sys.argv[1:] if "=" in a]
    if not args:
        print("name=URL の形式で指定してください", file=sys.stderr)
        raise SystemExit(1)
    for a in args:
        name, url = a.split("=", 1)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name) or not url.startswith("https://"):
            print(f"  × 不正な指定: {a}", flush=True)
            continue
        fetch_one(name, url)


if __name__ == "__main__":
    main()
