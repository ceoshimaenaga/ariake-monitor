# -*- coding: utf-8 -*-
"""イベント取得先の健全性チェック (保守用ツール)。

会場サイトが改修されてイベントが取れなくなったとき、どのURLなら
取れるのかを調べるためのもの。候補URLを片っ端から叩いて、
「HTTPステータス / ページタイトル / JSON-LDで取れた件数 /
 ヒューリスティック解析で取れた件数 / 最初の3件」を表形式で出す。

使い方:
    python ariake/probe.py                    # 既定の候補リストを全部調べる
    python ariake/probe.py URL [URL ...]      # 指定URLだけ調べる
    python ariake/probe.py --discover 会場名 …  # 公式サイトURLを Wikidata から調べて試す
    python ariake/probe.py --dump URL         # 日付を含むHTMLブロックの生タグを出す
    python ariake/probe.py --json URL         # JSON APIの構造を出す (WordPress等)

GitHub Actions の "ariake-probe" ワークフローから手動実行できる
(ローカルからサイトに繋がらない環境でも調査できるようにするため)。
"""

from __future__ import annotations

import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config                                             # noqa: E402
from sources import events as E                            # noqa: E402
import util                                              # noqa: E402
from util import fetch, now_jst, soup                      # noqa: E402

util.HTTP_TIMEOUT = 8          # 調査中は短く打ち切る
util.HTTP_SLEEP = 0.6

# 会場ごとの候補URL。現行の設定に加え、ありそうな綴りも一緒に試す。
CANDIDATES: dict[str, list[str]] = {
    "ariake_arena": [
        "https://ariake-arena.tokyo/event/",
        "https://ariake-arena.tokyo/events/",
        "https://ariake-arena.tokyo/schedule/",
        "https://ariake-arena.tokyo/",
        "https://www.ariake-arena.tokyo/event/",
    ],
    "garden_theater": [
        "https://www.tokyo-gardentheater.com/schedule/",
        "https://tokyo-gardentheater.com/schedule/",
        "https://tokyo-gardentheater.com/",
        "https://www.tokyo-gardentheater.jp/",
        "https://tokyo-gardentheater.jp/schedule/",
    ],
    "ariake_garden": [
        "https://ariake-garden.com/event/",
        "https://ariake-garden.jp/event/",
        "https://www.ariake-garden.jp/event/",
        "https://ariake-garden.jp/",
        "https://ariakegarden.jp/",
    ],
    "shiki_ariake": [
        "https://www.shiki.jp/theatres/ariake_haru/",
        "https://www.shiki.jp/theatres/ariake_haru/schedule/",
        "https://www.shiki.jp/theatres/ariake_aki/schedule/",
        "https://www.shiki.jp/navi/schedule/",
        "https://www.shiki.jp/schedule/",
    ],
    "gymex": [
        "https://ariake-arena.tokyo/gymex/",
        "https://ariake-gymex.tokyo/",
        "https://ariake-gymex.jp/",
        "https://ariake-arena.tokyo/facility/gymex/",
    ],
    "bigsight": [
        "https://www.bigsight.jp/visitor/event/",
        "https://www.bigsight.jp/visitor/event/?ym={ym}",
    ],
    "ariake_coliseum": [
        "https://www.tptc.co.jp/park/03_08/event",
    ],
}


def probe(url: str, venue: str = "bigsight") -> dict:
    url = url.replace("{ym}", now_jst().strftime("%Y%m"))
    r = fetch(url)
    if r is None:
        return {"url": url, "status": "接続不可", "title": "", "jsonld": 0,
                "html": 0, "samples": []}
    # JSON が返るURLは構造を出す (HTML解析しても意味がないため)
    if "json" in (r.headers.get("Content-Type") or "").lower():
        print(f"   JSONレスポンス: {url}", flush=True)
        probe_json(url)
        return {"url": url, "status": r.status_code, "title": "(JSON)",
                "jsonld": 0, "html": 0, "samples": []}
    body = r.text
    try:
        title = soup(body).title.get_text(strip=True)[:60]
    except Exception:                                     # noqa: BLE001
        title = ""
    src = {"urls": [url], "default_open": "10:00", "default_end": "17:00"}
    today = date.today()
    try:
        ld = E.from_jsonld(body, venue, src, today)
    except Exception as e:                                # noqa: BLE001
        ld = []
        title += f" [JSON-LD解析エラー: {e}]"
    try:
        hs = E.from_html(body, venue, src, today)
    except Exception as e:                                # noqa: BLE001
        hs = []
        title += f" [HTML解析エラー: {e}]"
    best = ld or hs
    return {"url": url, "status": r.status_code, "title": title,
            "jsonld": len(ld), "html": len(hs),
            "samples": [f"{e['start_date']}〜{e['end_date']} {e['title'][:40]}"
                        for e in best[:3]]}


# --- 公式サイトURLの自動発見 (Wikidata の「公式ウェブサイト」P856) -------------
WD_SEARCH = "https://www.wikidata.org/w/api.php"


def discover(name: str) -> list[str]:
    """会場名から公式サイトURLを引く。Wikidata → Wikipedia外部リンク の順。"""
    urls: list[str] = []
    from util import fetch_json
    d = fetch_json(WD_SEARCH, params={"action": "wbsearchentities", "search": name,
                                      "language": "ja", "uselang": "ja",
                                      "format": "json", "limit": 3})
    for hit in ((d or {}).get("search") or []):
        c = fetch_json(WD_SEARCH, params={"action": "wbgetclaims", "entity": hit["id"],
                                          "property": "P856", "format": "json"})
        for claim in ((c or {}).get("claims") or {}).get("P856", []):
            v = (((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value"))
            if isinstance(v, str) and v.startswith("http"):
                urls.append(v)
    if not urls:                       # Wikipedia 記事の外部リンクから拾う
        d = fetch_json("https://ja.wikipedia.org/w/api.php",
                       params={"action": "query", "prop": "extlinks", "titles": name,
                               "ellimit": "40", "format": "json"})
        for page in (((d or {}).get("query") or {}).get("pages") or {}).values():
            for el in page.get("extlinks") or []:
                u = el.get("*", "")
                if u.startswith("http") and "wikipedia" not in u and "wikimedia" not in u:
                    urls.append(u)
    # 重複を除き、スケジュールっぽいパスを足す
    out: list[str] = []
    for u in urls[:4]:
        base = u if u.endswith("/") else u + "/"
        for suffix in ("", "event/", "events/", "schedule/", "calendar/",
                       "eventinfo/", "event/calendar/"):
            cand = base + suffix
            if cand not in out:
                out.append(cand)
    return out


def dump(url: str) -> None:
    """日付を含むHTMLブロックの生タグを出す (抽出ロジック改善のための調査用)。"""
    import re as _re
    r = fetch(url)
    if r is None:
        print("  取得できませんでした", flush=True)
        return
    s = soup(r.text)
    for bad in s(["script", "style", "nav", "footer", "header"]):
        bad.decompose()
    shown = 0
    for tag in s.find_all(E.BLOCK_TAGS):
        if tag.find(E.BLOCK_TAGS):
            continue
        text = _re.sub(r"\s+", " ", tag.get_text(" ", strip=True))
        if not (12 <= len(text) <= 400) or E.NOISE.search(text):
            continue
        if not E.parse_date_range(text, date.today()):
            continue
        print(f"--- ブロック {shown + 1} <{tag.name} class={tag.get('class')}>", flush=True)
        print("    " + str(tag)[:700].replace("\n", " "), flush=True)
        # 親を1階層さかのぼった構造も出す (タイトルが親側にあるケースの確認)
        if tag.parent is not None:
            ptxt = _re.sub(r"\s+", " ", tag.parent.get_text(" ", strip=True))[:200]
            print(f"    親<{tag.parent.name} class={tag.parent.get('class')}>: {ptxt}",
                  flush=True)
        shown += 1
        if shown >= 6:
            break
    if shown:
        return
    # 日付ブロックが無い場合は、ページの素の構造を出して原因を見る
    print("  日付を含むブロックなし。ページ構造を出します。", flush=True)
    body_text = _re.sub(r"\s+", " ", s.get_text(" ", strip=True))
    print(f"  本文({len(body_text)}文字)の冒頭: {body_text[:500]}", flush=True)
    # 同じclassが3回以上出る要素 = 一覧のカード構造とみなす
    from collections import Counter
    counts: Counter = Counter()
    for tag in s.find_all(True):
        cls = " ".join(tag.get("class") or [])
        if cls:
            counts[(tag.name, cls)] += 1
    print("  繰り返し構造 (上位8件):", flush=True)
    for (name, cls), n in counts.most_common(8):
        if n < 3:
            continue
        sample = s.find(name, class_=cls.split()[0])
        txt = _re.sub(r"\s+", " ", sample.get_text(" ", strip=True))[:120] if sample else ""
        print(f"    <{name} class=\"{cls}\"> ×{n}  例: {txt}", flush=True)
    # 日付らしき文字列が本文にあるか
    hits = _re.findall(r"\d{1,4}[年./-]\d{1,2}[月./-]\d{1,2}|\d{1,2}/\d{1,2}", body_text)
    print(f"  本文中の日付らしき文字列: {hits[:12]}", flush=True)


def probe_json(url: str) -> None:
    """JSON API の構造を出す。JSで描画されるサイトの裏側APIを探すため。"""
    from util import fetch_json
    d = fetch_json(url)
    if d is None:
        print("  JSONとして取得できませんでした", flush=True)
        return
    if isinstance(d, list):
        print(f"  配列 {len(d)} 件", flush=True)
        if d:
            item = d[0]
            if isinstance(item, dict):
                print(f"  1件目のキー: {sorted(item)[:30]}", flush=True)
                for k in sorted(item):
                    v = item[k]
                    if isinstance(v, (str, int, float)) and str(v):
                        print(f"    {k}: {str(v)[:110]}", flush=True)
                    elif isinstance(v, dict) and v:
                        print(f"    {k}: (dict) {str(v)[:110]}", flush=True)
            else:
                print(f"  1件目: {str(item)[:200]}", flush=True)
    elif isinstance(d, dict):
        print(f"  オブジェクト キー: {sorted(d)[:40]}", flush=True)
        for k in sorted(d)[:12]:
            print(f"    {k}: {str(d[k])[:130]}", flush=True)


def main() -> None:
    args = [a for a in sys.argv[1:] if a.strip()]
    if args and args[0] == "--json":
        for url in args[1:]:
            print(f"=== JSON構造: {url} ===", flush=True)
            probe_json(url)
            print(flush=True)
        return
    if args and args[0] == "--dump":
        for url in args[1:]:
            print(f"=== HTML構造ダンプ: {url} ===", flush=True)
            dump(url)
        return
    if "--discover" in args:
        # --discover 以降の「http で始まらない語」を会場名として扱い、
        # http で始まる引数はそのまま調査対象に追加する。
        names = [a for a in args if not a.startswith("http") and a != "--discover"]
        direct = [a for a in args if a.startswith("http")]
        found: list[str] = []
        for name in names:
            print(f"[{name}] の公式サイトを検索…", flush=True)
            for u in discover(name):
                print(f"  候補: {u}", flush=True)
                found.append(u)
        args = direct + found
        print(flush=True)
    jobs = ([("指定", u) for u in args] if args else
            [(v, u) for v, urls in CANDIDATES.items() for u in urls])
    print(f"=== イベント取得先の健全性チェック ({len(jobs)} URL) ===\n", flush=True)
    ok_by_venue: dict[str, list[str]] = {}
    for venue, url in jobs:
        r = probe(url, venue if venue in config.SPOTS else "bigsight")
        mark = "OK " if (r["jsonld"] or r["html"]) else "－ "
        print(f"{mark}[{venue}] {r['status']} {r['url']}", flush=True)
        print(f"     title: {r['title']}", flush=True)
        print(f"     JSON-LD: {r['jsonld']}件 / HTML解析: {r['html']}件", flush=True)
        for s in r["samples"]:
            print(f"       - {s}", flush=True)
        if r["jsonld"] or r["html"]:
            ok_by_venue.setdefault(venue, []).append(
                f"{r['url']} (JSON-LD {r['jsonld']} / HTML {r['html']})")
        print(flush=True)

    print("=== 使えるURL ===", flush=True)
    for venue in (CANDIDATES if not args else {"指定": None}):
        found = ok_by_venue.get(venue)
        print(f"  {venue}: " + (found[0] if found else "見つからず"), flush=True)


if __name__ == "__main__":
    main()
