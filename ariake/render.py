# -*- coding: utf-8 -*-
"""JavaScript で描画されるイベントページを実ブラウザで取得する。

背景
----
有明アリーナや劇団四季のサイトは、単純な HTTP 取得では中身が空
(JSで描画される / 自動アクセスを弾かれる) ため、イベントが取れない。
チケットサイト4社 (ぴあ/ローチケ/イープラス/LiveFans) も同様だった。

そこで Playwright の Chromium で実際に描画してから HTML を取り出す。
ただしブラウザ起動は重いので、毎時の収集とは分けて 6時間おきに実行し、
結果を rendered_events.json に書き出す。毎時の collect.py は
そのファイルを読むだけなのでブラウザを必要としない。

使い方:
    pip install playwright && playwright install --with-deps chromium
    python ariake/render.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config                                             # noqa: E402
from sources import events as E                            # noqa: E402
from util import UA, now_jst                               # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rendered_events.json")
WAIT_MS = 4000          # 描画待ち


def render_html(page, url: str) -> str:
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:                                     # noqa: BLE001
        pass                                              # 常時通信するサイトは諦めて進む
    page.wait_for_timeout(WAIT_MS)
    return page.content()


def _why_empty(html: str) -> list[str]:
    """0件だった原因を切り分けるための情報 (本文冒頭・繰り返し構造・日付)。"""
    import re
    from collections import Counter
    from util import soup

    out = []
    s = soup(html)
    for bad in s(["script", "style", "nav", "footer", "header"]):
        bad.decompose()
    text = re.sub(r"\s+", " ", s.get_text(" ", strip=True))
    out.append(f"    本文 {len(text)}文字: {text[:300]}")
    counts: Counter = Counter()
    for tag in s.find_all(True):
        cls = " ".join(tag.get("class") or [])
        if cls:
            counts[(tag.name, cls)] += 1
    reps = [f"<{n} class={c}>×{k}" for (n, c), k in counts.most_common(6) if k >= 3]
    out.append("    繰り返し構造: " + (" / ".join(reps) if reps else "なし"))
    hits = re.findall(r"\d{1,4}[年./-]\d{1,2}[月./-]\d{1,2}|\d{1,2}/\d{1,2}"
                      r"|\d{1,2}\s+\d{1,2}\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)", text)
    out.append(f"    日付らしき文字列: {hits[:10]}")
    return out


def main() -> None:
    from playwright.sync_api import sync_playwright

    diag: list[str] = []

    targets = [s for s in config.EVENT_SOURCES if s.get("render")]
    if not targets:
        print("render: 対象なし", flush=True)
        return

    today = date.today()
    all_events: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM") or None)
        ctx = browser.new_context(user_agent=UA, locale="ja-JP",
                                  viewport={"width": 1280, "height": 1600})
        page = ctx.new_page()
        for src in targets:
            venue = src["venue"]
            got: list[dict] = []
            for url in src["urls"]:
                try:
                    html = render_html(page, url)
                except Exception as e:                    # noqa: BLE001
                    diag.append(f"! 描画失敗 {url}: {e}")
                    continue
                ld = E.from_jsonld(html, venue, src, today)
                rec = E.from_records(html, venue, src, today)
                heu = E.from_html(html, venue, src, today)
                found = ld or rec or heu
                diag.append(f"{venue} {url}")
                diag.append(f"    HTML {len(html):,}文字 / JSON-LD {len(ld)} / "
                            f"レコード {len(rec)} / ヒューリスティック {len(heu)}")
                if not found:
                    diag.extend(_why_empty(html))
                got += found
            for ev in got:
                ev["source"] = "rendered"
                all_events.append(ev)
        browser.close()

    # 同一イベントをまとめる (期間の広い方を残す)
    merged: dict[tuple, dict] = {}
    for ev in all_events:
        t = E._norm(ev.get("title") or "")
        if (len(t) < 5 or E.LABEL_WORDS.match(t) or E.PAGE_HEADING.match(t)
                or E.NOISE_TITLE.search(t)):
            continue
        ev["title"] = t
        key = (ev["venue"], t[:60], ev["start_date"])
        old = merged.get(key)
        if not old or ev["end_date"] > old["end_date"]:
            merged[key] = ev

    out = sorted(merged.values(), key=lambda e: (e["start_date"], e["venue"]))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"generated_at": now_jst().isoformat(timespec="seconds"),
                   "events": out}, f, ensure_ascii=False, indent=1)
    print(f"rendered_events.json 書き出し: {len(out)}件", flush=True)
    for e in out[:10]:
        print(f"  {e['start_date']}〜{e['end_date']} [{e['venue']}] {e['title'][:50]}",
              flush=True)
    # 診断はログの最後にまとめて出す (末尾だけ見れば原因が分かるように)
    print("\n=== 取得先ごとの診断 ===", flush=True)
    for line in diag:
        print(line, flush=True)


if __name__ == "__main__":
    main()
