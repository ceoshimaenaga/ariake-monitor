# -*- coding: utf-8 -*-
"""過去のイベントを遡って取り込む。

毎時の収集 (collect.py) は「これから先」しか見ない。
過去に何があったかは、予測の答え合わせにも、
「去年の同じ週はどうだったか」を言うためにも要る。

考え方は collect.py と同じで、違うのは月の歩き方だけ:
  - 月送りのクエリ (?ym=YYYYMM) を持つ取得先を、過去に向かって歩く
  - 年が書かれていない日付 (「1月15日」) は、その月を基準に年を決める
    (今日を基準にすると、1月のページを11月に読んだときに
     翌年の1月と誤読する)

欠けがあっても止めない。取れた分だけ入れて、取れなかった月は数える。
過去のイベントは予測には使われない (forecast は期間で絞って読むため)、
あくまで記録として貯める。

保管先は events_history.json (リポジトリにコミットする)。
DB (ariake.db) は Actions のキャッシュに置かれていて、しばらく走らないと
消える。過去の記録をそこに置くと、静かに失われる。

走らせるたびに、既にある分と突き合わせて増やす (消さない)。
サイトの改修で一時的に取れなくなっても、前に取れた分は残る。

使い方:
    python ariake/backfill.py --from 2026-01            # 今月まで
    python ariake/backfill.py --from 2026-01 --to 2026-06
    python ariake/backfill.py --from 2026-01 --dry-run  # 書かず件数だけ
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from urllib.parse import quote

sys.path.insert(0, __file__.rsplit("/", 1)[0])

import config
from sources import events as ev_mod
from util import fetch, now_jst

HISTORY_PATH = os.path.join(os.path.dirname(__file__), os.pardir,
                            "events_history.json")

# 記録として残す項目。収集時刻などの運用上の値は入れない
# (走らせるたびに差分が出て、履歴が読みにくくなるため)
FIELDS = ("venue", "title", "url", "start_date", "end_date",
          "open_time", "start_time", "end_time", "est_attendance",
          "scale_label", "hall")


def load_history(path: str) -> dict[tuple, dict]:
    """既にある記録を、鍵つきで読む。無ければ空。"""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    out = {}
    for e in data.get("events", []):
        out[(e.get("venue"), e.get("title"), e.get("start_date"))] = e
    return out


def save_history(path: str, items: dict[tuple, dict], span: str) -> None:
    evs = sorted(items.values(),
                 key=lambda e: (e.get("start_date") or "", e.get("venue") or "",
                                e.get("title") or ""))
    doc = {
        "_README": [
            "過去のイベントの記録。ariake/backfill.py が作る。",
            "欠けがあるのは承知の上。取れた分だけ貯めている。",
            "走らせるたびに増えるだけで、既にある分は消さない。",
            "予測には使っていない (これから先の予定だけを見ているため)。",
        ],
        "generated_at": now_jst().isoformat(timespec="seconds"),
        "covers": span,
        "count": len(evs),
        "events": evs,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)


# インターネットアーカイブ。保存済みページの一覧と、その中身。
# id_ を付けると、アーカイブ側の枠組み (ツールバー等) が混ざらない生のHTMLが返る。
#
# 立て続けに投げると接続を拒否される (Connection refused)。
# 相手の持ち物を読ませてもらっている以上、間を空けるのが筋でもある。
# 「拒否された」と「保存版が無い」は意味が違うので、必ず区別する。
# 混同すると「無い」と誤って判断し、取れるはずのものを諦めることになる。
CDX = ("https://web.archive.org/cdx/search/cdx?url={url}"
       "&from={ym}01&to={ym}31&output=json&limit={limit}"
       "&filter=statuscode:200&collapse=timestamp:6")
WB = "https://web.archive.org/web/{ts}id_/{url}"


PAUSE = 3.0        # 1回ごとに空ける秒数
TRIES = 3          # 拒否されたときに試す回数
BACKOFF = 8.0      # 拒否されたあと待つ秒数 (回を追うごとに倍)


def wayback(url: str):
    """アーカイブに1回問い合わせる。間を空け、拒否されたら少し待って試す。

    返り値は応答か None。None は「拒否された/届かなかった」であって、
    「保存版が無い」ではない。
    """
    wait = BACKOFF
    for i in range(TRIES):
        time.sleep(PAUSE)
        r = fetch(url)
        if r is not None:
            return r
        if i < TRIES - 1:
            time.sleep(wait)
            wait *= 2
    return None


def snapshots(url: str, ym: str, limit: int = 2):
    """その月に保存された版の日時を古い順に返す。

    返り値は (日時の並び, 届いたか)。届かなかったときは ([], False) で、
    これは「保存版が無い」 ([], True) とは区別する。
    """
    r = wayback(CDX.format(url=quote(url, safe=""), ym=ym, limit=limit))
    if r is None:
        return [], False
    try:
        rows = json.loads(r.text or "[]")
    except json.JSONDecodeError:
        return [], True
    if len(rows) < 2:          # 1行目は見出し
        return [], True
    head = rows[0]
    i = head.index("timestamp") if "timestamp" in head else 1
    return [row[i] for row in rows[1:] if len(row) > i], True


def archived_pages(src: dict, first: date):
    """その月に保存されていたページを返す。

    返り値は (ページの並び, 届いたか)。届かなかったときと、
    保存版が無かったときを呼び出し側で言い分けられるようにする。
    """
    out, reached = [], True
    ym = f"{first:%Y%m}"
    for url in src.get("urls", []):
        ts_list, ok = snapshots(url, ym)
        if not ok:
            reached = False
            continue
        for ts in ts_list:
            r = wayback(WB.format(ts=ts, url=url))
            if r is None or not r.text:
                continue
            out.append((f"保存版 {ts[:8]}", r.text))
            # 同じ月に何版もある場合、最初に中身が取れた版で足りる
            break
    return out, reached


def check_archive() -> None:
    """各取得先が、そもそもどれだけ保存されているかを調べる。

    「保存版なし」が続くとき、本当に無いのか、問い合わせ方が
    悪いだけなのかを切り分けるために使う。
    URL の書き方 (http/https、末尾のスラッシュ) で当たりが変わるので、
    いくつか試して、当たった形を出す。
    """
    print("=== 保存状況の調査 ===", flush=True)
    for src in config.EVENT_SOURCES:
        print(f"[{src['venue']}]", flush=True)
        for url in src.get("urls", []):
            variants = [url]
            if url.startswith("https://"):
                variants.append("http://" + url[len("https://"):])
            if url.endswith("/"):
                variants.append(url[:-1])
            variants.append(url.rstrip("/") + "/*")
            for v in variants:
                q = ("https://web.archive.org/cdx/search/cdx?url={u}"
                     "&output=json&limit=4&filter=statuscode:200"
                     "&collapse=timestamp:4").format(u=quote(v, safe=""))
                r = wayback(q)
                rows = []
                if r is not None:
                    try:
                        rows = json.loads(r.text or "[]")
                    except json.JSONDecodeError:
                        rows = []
                n = max(0, len(rows) - 1)
                when = ""
                if n:
                    head = rows[0]
                    i = head.index("timestamp") if "timestamp" in head else 1
                    ts = [row[i][:6] for row in rows[1:] if len(row) > i]
                    when = "  " + " ".join(ts)
                print(f"  {n:>2} 件  {v}{when}", flush=True)


def months_between(a: date, b: date):
    """a の月から b の月まで、各月の1日を順に返す。"""
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        yield date(y, m, 1)
        m += 1
        if m == 13:
            y, m = y + 1, 1


def extract(body: str, venue: str, src: dict, ref: date) -> list[dict]:
    """collect.py と同じ順序で抽出器を試す。

    ref はその月の1日。年の書かれていない日付の年を決めるのに使う。
    """
    if body.lstrip().startswith("BEGIN:VCALENDAR"):
        return ev_mod.from_ics(body, venue, src)
    found = ev_mod.from_jsonld(body, venue, src, ref)
    if not found:
        found = ev_mod.from_records(body, venue, src, ref)
    if not found:
        found = ev_mod.from_html(body, venue, src, ref)
    return found


def keep(ev: dict) -> bool:
    """collect.py と同じ基準で、ラベルや定型文のタイトルを捨てる。"""
    t = ev.get("title") or ""
    return not (len(t) < 5
                or ev_mod.LABEL_WORDS.match(t)
                or ev_mod.PAGE_HEADING.match(t)
                or ev_mod.NOISE_TITLE.search(t))


def run(d_from: date, d_to: date, dry: bool, only: str | None,
        path: str = HISTORY_PATH) -> int:
    history = load_history(path)
    before = len(history)
    added, rows = 0, []
    for src in config.EVENT_SOURCES:
        venue = src["venue"]
        if only and venue != only:
            continue

        per_month, got_total = [], 0
        for first in months_between(d_from, d_to):
            ym = f"{first:%Y-%m}"
            pages, reached = archived_pages(src, first)
            if not pages:
                per_month.append(f"{ym}:" + ("保存版なし" if reached else "届かず"))
                continue

            found = []
            for _label, body in pages:
                found += [e for e in extract(body, venue, src, first) if keep(e)]

            # 保存版には前後の月の予定も載っている。依頼した月の分だけ数える。
            found = [e for e in found
                     if e["start_date"][:7] == ym or e["end_date"][:7] == ym]

            # 同一イベントは期間の広い方を残す (collect.py と同じ)
            merged: dict[tuple, dict] = {}
            for e in found:
                k = (e["title"][:60], e["start_date"])
                old = merged.get(k)
                if not old or e["end_date"] > old["end_date"]:
                    merged[k] = e

            for e in merged.values():
                rec = {f: e.get(f) for f in FIELDS}
                key = (rec["venue"], rec["title"], rec["start_date"])
                prev = history.get(key)
                if prev is None:
                    history[key] = rec
                    added += 1
                else:
                    # 既にある記録は、空いている項目だけ埋める。
                    # 一度取れた値を、あとの取得失敗で消さないため。
                    for f in FIELDS:
                        if prev.get(f) in (None, "") and rec.get(f) not in (None, ""):
                            prev[f] = rec[f]
            per_month.append(f"{ym}:{len(merged)}")
            got_total += len(merged)

        rows.append((venue, got_total, " ".join(per_month)))

    span = f"{d_from:%Y-%m}〜{d_to:%Y-%m}"
    print(f"=== 過去イベントの取り込み {span}"
          f"{' (書き込まず)' if dry else ''} ===", flush=True)
    for venue, n, detail in rows:
        print(f"{venue:<18} {str(n):>5}  {detail}", flush=True)
    print(f"今回見つけた合計 {sum(r[1] for r in rows if isinstance(r[1], int))} 件", flush=True)
    print(f"記録: {before} 件 → {len(history)} 件 (新規 {added})", flush=True)

    if not dry:
        save_history(path, history, span)
        print(f"書き出した: {path}", flush=True)
    return added


def parse_ym(s: str) -> date:
    y, m = s.split("-")
    return date(int(y), int(m), 1)


def main() -> None:
    p = argparse.ArgumentParser(description="過去のイベントを遡って取り込む")
    p.add_argument("--from", dest="d_from", default="2026-01",
                   help="開始月 YYYY-MM (既定 2026-01)")
    p.add_argument("--to", dest="d_to", default=None,
                   help="終了月 YYYY-MM (既定 今月)")
    p.add_argument("--venue", default=None, help="この会場だけ")
    p.add_argument("--dry-run", action="store_true", help="書き出さず件数だけ出す")
    p.add_argument("--check-archive", action="store_true",
                   help="各取得先がどれだけ保存されているかだけ調べる")
    p.add_argument("--out", default=HISTORY_PATH, help="書き出し先")
    a = p.parse_args()
    if a.check_archive:
        check_archive()
        return
    d_to = parse_ym(a.d_to) if a.d_to else now_jst().date().replace(day=1)
    run(parse_ym(a.d_from), d_to, a.dry_run, a.venue, a.out)


if __name__ == "__main__":
    main()
