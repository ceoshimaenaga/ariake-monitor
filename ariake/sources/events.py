# -*- coding: utf-8 -*-
"""各会場のイベントスケジュール収集。

取得戦略 (上から順に試し、取れたところで採用):
  1) JSON-LD (schema.org/Event) — 主要会場サイトの多くが埋め込んでいる
  2) ICS カレンダー (.ics を公開している会場)
  3) ヒューリスティックHTML解析 — 日付パターンを含むブロックから抽出

どの会場も取れなくても収集は止めず warnings に積む。
手入力の manual_events.json があれば最後に上書きマージする
(スクレイパが壊れても予測を落とさないための保険)。
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta

import config
import store
from util import fetch, now_jst, soup

MANUAL_PATH = os.path.join(os.path.dirname(__file__), os.pardir, "manual_events.json")
RENDERED_PATH = os.path.join(os.path.dirname(__file__), os.pardir,
                             "rendered_events.json")

# --- 日付・時刻パターン -----------------------------------------------------
RANGE_SEP = r"(?:[〜～~\-–—ー]|から)"
# 「10月1日（水）〜」のような曜日カッコを読み飛ばすためのパターン
DOW = r"(?:\s*[（(][^）)]{0,8}[）)])?"
D_FULL = r"(\d{4})[年./\-](\d{1,2})[月./\-](\d{1,2})"
D_MD = r"(\d{1,2})[月/](\d{1,2})"
RE_FULL_RANGE = re.compile(D_FULL + r"日?" + DOW + r"\s*" + RANGE_SEP
                           + r"\s*(?:(\d{4})[年./\-])?(\d{1,2})[月/](\d{1,2})")
RE_FULL = re.compile(D_FULL)
RE_MD_RANGE = re.compile(D_MD + r"日?" + DOW + r"\s*" + RANGE_SEP
                         + r"\s*(\d{1,2})[月/](\d{1,2})")
RE_MD = re.compile(D_MD)
RE_TIME = re.compile(r"(\d{1,2})\s*[:：]\s*(\d{2})")
# 「09 29 Tue.」のように月・日・曜日が別要素で並ぶ表記 (東京ガーデンシアター等)
RE_SPLIT_MD = re.compile(
    r"\b(\d{1,2})\s+(\d{1,2})\s+(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b\.?", re.I)
# 「9.1 TUE」のようにドット区切り＋英語曜日の表記 (有明アリーナ)。
# 曜日を必ず伴わせることで、バージョン番号等の誤検出を防ぐ。
RE_DOT_MD = re.compile(
    r"\b(\d{1,2})\.(\d{1,2})\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b\.?", re.I)
RE_LABELED_TIME = re.compile(r"(開場|開演|開始|開館|閉場|終演|終了|閉館)\D{0,6}?(\d{1,2})\s*[:：]\s*(\d{2})")
NOISE = re.compile(r"(?:プライバシー|クッキー|Cookie|お問い合わせ|アクセス|サイトマップ|ログイン)")


def _infer_year(month: int, today: date) -> int:
    """年が書かれていない日付の年を推定 (半年以上前なら翌年扱い)。"""
    y = today.year
    if month < today.month - 6:
        y += 1
    elif month > today.month + 6:
        y -= 1
    return y


def _iso(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def parse_date_range(text: str, today: date) -> tuple[str, str] | None:
    """テキストから開始日・終了日 (YYYY-MM-DD) を取り出す。"""
    m = RE_FULL_RANGE.search(text)
    if m:
        y1, m1, d1, y2, m2, d2 = m.groups()
        s = _iso(int(y1), int(m1), int(d1))
        e = _iso(int(y2 or y1), int(m2), int(d2))
        if s and e:
            if e < s:                                   # 年を跨ぐ表記
                e = _iso(int(y2 or y1) + 1, int(m2), int(d2)) or e
            return s, e
    m = RE_MD_RANGE.search(text)
    if m:
        m1, d1, m2, d2 = (int(x) for x in m.groups())
        y1 = _infer_year(m1, today)
        s = _iso(y1, m1, d1)
        e = _iso(y1 if m2 >= m1 else y1 + 1, m2, d2)
        if s and e:
            return s, e
    m = RE_FULL.search(text)
    if m:
        s = _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if s:
            return s, s
    m = RE_DOT_MD.search(text)
    if m:
        mm, dd = int(m.group(1)), int(m.group(2))
        if 1 <= mm <= 12 and 1 <= dd <= 31:
            s_ = _iso(_infer_year(mm, today), mm, dd)
            if s_:
                return s_, s_
    m = RE_SPLIT_MD.search(text)
    if m:
        mm, dd = int(m.group(1)), int(m.group(2))
        if 1 <= mm <= 12 and 1 <= dd <= 31:
            s_ = _iso(_infer_year(mm, today), mm, dd)
            if s_:
                return s_, s_
    m = RE_MD.search(text)
    if m:
        mm, dd = int(m.group(1)), int(m.group(2))
        if 1 <= mm <= 12 and 1 <= dd <= 31:
            s = _iso(_infer_year(mm, today), mm, dd)
            if s:
                return s, s
    return None


def parse_times(text: str) -> dict:
    """開場/開演/終演 の時刻を拾う。ラベル無しは出現順に開始・終了とみなす。"""
    out: dict[str, str] = {}
    for label, h, mi in RE_LABELED_TIME.findall(text):
        hh = f"{int(h):02d}:{mi}"
        if label in ("開場", "開館"):
            out.setdefault("open_time", hh)
        elif label in ("開演", "開始"):
            out.setdefault("start_time", hh)
        else:
            out.setdefault("end_time", hh)
    if "start_time" not in out or "end_time" not in out:
        found = [f"{int(h):02d}:{mi}" for h, mi in RE_TIME.findall(text)
                 if 0 <= int(h) <= 27]
        if found:
            out.setdefault("start_time", found[0])
            # ラベルから開演が取れている場合、同じ時刻を終演にしない
            if len(found) > 1 and found[-1] > out.get("start_time", ""):
                out.setdefault("end_time", found[-1])
    return out


def estimate_scale(title: str, venue: str, days: int = 1) -> tuple[int, str]:
    """タイトルのキーワードと会場定員から1日あたり来場者を見積もる。"""
    spot = config.SPOTS.get(venue, {})
    cap = spot.get("capacity", 3000)
    for keys, n, label in config.EVENT_SCALE_KEYWORDS:
        if any(k.lower() in title.lower() for k in keys):
            if n == 0:                                   # 公演系は定員基準
                return int(cap * config.DEFAULT_FILL_RATE), label
            # 複数日開催の大型展示会は「総来場」寄りの数字なので日割り補正
            per_day = n / max(1, min(days, 4)) if n >= 50000 else n
            return int(min(per_day, cap)), label
    fallback = spot.get("default_attendance")
    if fallback:
        return int(fallback), "推定 (会場の平均的な規模)"
    return int(cap * 0.5), "推定 (定員の50%)"


# --- 1) JSON-LD -------------------------------------------------------------
EVENT_TYPES = {"event", "exhibitionevent", "musicevent", "theaterevent",
               "sportsevent", "festival", "businessevent", "screeningevent"}


def _walk_jsonld(node, out: list):
    if isinstance(node, list):
        for x in node:
            _walk_jsonld(x, out)
    elif isinstance(node, dict):
        t = node.get("@type")
        types = [t] if isinstance(t, str) else (t or [])
        if any(str(x).lower() in EVENT_TYPES for x in types) and node.get("name"):
            out.append(node)
        for v in node.values():
            if isinstance(v, (list, dict)):
                _walk_jsonld(v, out)


def from_jsonld(html: str, venue: str, src: dict, today: date) -> list[dict]:
    s = soup(html)
    raw: list[dict] = []
    for tag in s.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        try:
            _walk_jsonld(json.loads(tag.string or tag.get_text() or "null"), raw)
        except Exception:                                # noqa: BLE001
            continue
    events = []
    for node in raw:
        start = str(node.get("startDate") or "")
        if len(start) < 10:
            continue
        end = str(node.get("endDate") or start)[:10]
        title = re.sub(r"\s+", " ", str(node["name"])).strip()
        st = start[11:16] if len(start) >= 16 else src.get("default_open")
        et = str(node.get("endDate") or "")[11:16] or src.get("default_end")
        days = max(1, (date.fromisoformat(end) - date.fromisoformat(start[:10])).days + 1)
        n, label = estimate_scale(title, venue, days)
        events.append({
            "venue": venue, "title": title, "url": node.get("url") or src["urls"][0],
            "start_date": start[:10], "end_date": end,
            "start_time": st, "end_time": et or None,
            "est_attendance": n, "scale_label": label, "source": "jsonld",
        })
    return events


# --- 2) ICS -----------------------------------------------------------------
def from_ics(text: str, venue: str, src: dict) -> list[dict]:
    events, cur = [], {}
    for line in text.splitlines():
        line = line.strip()
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT":
            if cur.get("SUMMARY") and cur.get("DTSTART"):
                sd = re.sub(r"[^0-9]", "", cur["DTSTART"])[:8]
                ed = re.sub(r"[^0-9]", "", cur.get("DTEND", cur["DTSTART"]))[:8]
                if len(sd) == 8:
                    s = f"{sd[:4]}-{sd[4:6]}-{sd[6:]}"
                    e = f"{ed[:4]}-{ed[4:6]}-{ed[6:]}" if len(ed) == 8 else s
                    n, label = estimate_scale(cur["SUMMARY"], venue)
                    events.append({
                        "venue": venue, "title": cur["SUMMARY"], "url": src["urls"][0],
                        "start_date": s, "end_date": max(s, e),
                        "start_time": src.get("default_open"),
                        "end_time": src.get("default_end"),
                        "est_attendance": n, "scale_label": label, "source": "ics",
                    })
        elif ":" in line:
            k, v = line.split(":", 1)
            cur[k.split(";")[0]] = v
    return events


# --- 3) レコード型HTML解析 ----------------------------------------------------
# 「日付を含み、かつ見出しかリンクを持つ最小のブロック」を1イベントとみなす。
# 東京ビッグサイトの <dl class="list-01"><dt>開催期間</dt><dd>…</dd></dl> のように、
# 日付がラベル付きで別要素に入るサイトを正しく扱うために用意した。
HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
RECORD_ROOTS = ("li", "article", "section", "div", "dl", "tr", "dd", "table")
# 見出しではなくラベルや定型文であることを示す語 (タイトルに採用しない)
LABEL_WORDS = re.compile(
    r"^(開催(期間|時間|日|場所)|公演(時間|日|時刻)|上演時間|開場時間|"
    r"会期|日時|時間|入場区分|利用施設|料金|URL|"
    r"アクセス|主催|お問い?合わせ|新規タブ|詳細|一覧|もっと見る)")
# ニュース・告知の類はイベントではないので落とす
NOISE_TITLE = re.compile(
    r"(お知らせ|ご案内|重要|休館|臨時休業|メンテナンス|料金改定|募集|"
    r"採用|プレスリリース|価格改定|営業時間変更|注意|中止|延期のお知らせ)")


# リンク文言に付く定型句 (タイトルに混ざるので落とす)
LINK_SUFFIX = re.compile(
    r"\s*(新規タブで開きます|新しいタブで開きます|別ウィンドウで開きます|"
    r"外部サイトへ|PDF|\(\d+[KMG]?B\))\s*$")
# ページ全体の見出し (イベント名ではない)
PAGE_HEADING = re.compile(
    r"^(EVENT|NEWS|TOPICS|イベント|イベント一覧|開催予定のイベント|"
    r"開催中のイベント|今後のイベント|新着情報|お知らせ一覧)[\s|｜]*$")


# タイトル先頭に付く日付やジャンル表記 (「09 29 Tue. コンサート・ショー …」)
TITLE_PREFIX = re.compile(
    r"^(?:\d{1,2}\s+\d{1,2}\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\.?\s*"
    r"|\d{1,2}\.\d{1,2}\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\.?\s*"
    r"|\d{1,4}[年./-]\d{1,2}[月./-]\d{1,2}日?\s*"
    r"|[（(]?[月火水木金土日][）)]?\s*"
    r"|コンサート・ショー\s*|スポーツ\s*|その他\s*|EVENT\s+|NEWS\s+)+", re.I)


def _norm(t: str) -> str:
    t = re.sub(r"\s+", " ", t).strip()
    prev = None
    while t != prev:                      # 「… 新規タブで開きます PDF」等を繰り返し除去
        prev = t
        t = LINK_SUFFIX.sub("", t).strip()
    return TITLE_PREFIX.sub("", t).strip()


# 見出しタグではなく class 名でイベント名を表すサイト向け。
# event_name のような明確なものを、汎用の title より優先する。
# sub_title / subtitle は見出しではなく項目ラベルであることが多いので除く。
TITLE_CLASS_STRONG = re.compile(r"(event[_-]?name|main[_-]?title|headline|"
                                r"program[_-]?name|\bname\b)", re.I)
TITLE_CLASS_WEAK = re.compile(r"(title|ttl|subject|heading)", re.I)
TITLE_CLASS_SKIP = re.compile(r"(sub[_-]?title|subttl|sub[_-]?heading)", re.I)


def _title_of(tag) -> str:
    """レコードブロック(と祖先3階層)から、イベント名らしい文字列を選ぶ。"""
    node = tag
    for _ in range(4):
        if node is None:
            break
        for h in HEADING_TAGS:
            for el in node.find_all(h):
                t = _norm(el.get_text(" ", strip=True))
                # 「EVENT 開催予定のイベント」のようなページ見出しは除く
                t = re.sub(r"^(EVENT|NEWS|TOPICS)\s+", "", t)
                if (len(t) >= 4 and not LABEL_WORDS.match(t)
                        and not PAGE_HEADING.match(t) and not RE_FULL.search(t)):
                    return t
        node = node.parent
    # 見出しタグが無い場合、class名が event_name / title 等の要素を使う
    for pattern in (TITLE_CLASS_STRONG, TITLE_CLASS_WEAK):
        node = tag
        for _ in range(3):
            if node is None:
                break
            for el in node.find_all(attrs={"class": pattern}):
                cls = " ".join(el.get("class") or [])
                if TITLE_CLASS_SKIP.search(cls):
                    continue
                t = _norm(el.get_text(" ", strip=True))
                if (len(t) >= 4 and not LABEL_WORDS.match(t)
                        and not PAGE_HEADING.match(t) and not RE_FULL.search(t)):
                    return t
            node = node.parent
    # 見出しが無ければリンク文字列から選ぶ (URLそのものや定型文は除く)
    links = []
    for a in tag.find_all("a"):
        t = _norm(a.get_text(" ", strip=True))
        if (len(t) >= 4 and not t.startswith("http") and not LABEL_WORDS.match(t)
                and not NOISE.search(t) and not RE_FULL.fullmatch(t)):
            links.append(t)
    return max(links, key=len) if links else ""


def _labeled(text: str, label: str, width: int = 60) -> str:
    """「開催期間 2026年09月24日…」のようなラベル直後の文字列を取り出す。"""
    i = text.find(label)
    return text[i + len(label): i + len(label) + width] if i >= 0 else ""


def from_records(html: str, venue: str, src: dict, today: date) -> list[dict]:
    s = soup(html)
    for bad in s(["script", "style", "nav", "footer", "header"]):
        bad.decompose()

    cands = []
    for tag in s.find_all(RECORD_ROOTS):
        text = _norm(tag.get_text(" ", strip=True))
        if not (12 <= len(text) <= 1200) or NOISE.search(text):
            continue
        if not parse_date_range(text, today):
            continue
        if not (tag.find(HEADING_TAGS) or tag.find("a")):
            continue
        cands.append(tag)
    # 入れ子になっている場合は内側(最小)だけを残す
    alive = {id(t): t for t in cands}
    for t in cands:
        for parent in t.parents:
            alive.pop(id(parent), None)

    events, seen = [], set()
    for tag in alive.values():
        text = _norm(tag.get_text(" ", strip=True))
        title = _title_of(tag)
        if len(title) < 4 or NOISE_TITLE.search(title):
            continue
        rng = (parse_date_range(_labeled(text, "開催期間") or _labeled(text, "会期"), today)
               or parse_date_range(text, today))
        if not rng:
            continue
        key = (title[:60], rng[0])
        if key in seen:
            continue
        seen.add(key)
        times = parse_times(_labeled(text, "開催時間", 80) or text)
        days = max(1, (date.fromisoformat(rng[1]) - date.fromisoformat(rng[0])).days + 1)
        n, label = estimate_scale(title, venue, days)
        href = None
        for a in tag.find_all("a"):
            h = a.get("href") or ""
            if h and not h.startswith("#"):
                href = h
                break
        if href and href.startswith("/"):
            from urllib.parse import urljoin
            href = urljoin(src["urls"][0], href)
        events.append({
            "venue": venue, "title": title[:120], "url": href or src["urls"][0],
            "start_date": rng[0], "end_date": rng[1],
            "open_time": times.get("open_time"),
            "start_time": times.get("start_time") or src.get("default_open"),
            "end_time": times.get("end_time") or src.get("default_end"),
            "est_attendance": n, "scale_label": label, "source": "record",
        })
    return events


# --- 4) ヒューリスティックHTML解析 (最後の手段) -------------------------------
BLOCK_TAGS = ("li", "tr", "article", "dl", "section", "div")


def from_html(html: str, venue: str, src: dict, today: date) -> list[dict]:
    s = soup(html)
    for bad in s(["script", "style", "nav", "footer", "header"]):
        bad.decompose()
    seen: set[tuple[str, str]] = set()
    events: list[dict] = []
    for tag in s.find_all(BLOCK_TAGS):
        # 入れ子の親ブロックは飛ばす (同じ内容を二重に拾わないため)
        if tag.find(BLOCK_TAGS):
            continue
        text = re.sub(r"\s+", " ", tag.get_text(" ", strip=True))
        if not (12 <= len(text) <= 400) or NOISE.search(text):
            continue
        rng = parse_date_range(text, today)
        if not rng:
            continue
        # タイトル候補: リンクテキスト優先、無ければ日付部分を除いた本文
        a = tag.find("a")
        title = re.sub(r"\s+", " ", a.get_text(" ", strip=True)) if a else ""
        if len(title) < 4:
            title = RE_FULL_RANGE.sub("", RE_MD_RANGE.sub("", text))
            title = RE_FULL.sub("", RE_MD.sub("", title))
            title = re.sub(r"[（(]?[月火水木金土日][）)]?", "", title)
            title = re.sub(r"\s+", " ", title).strip(" ・|-—/,、")
        if len(title) < 4 or NOISE_TITLE.search(title) or LABEL_WORDS.match(title):
            continue
        key = (title[:60], rng[0])
        if key in seen:
            continue
        seen.add(key)
        times = parse_times(text)
        days = max(1, (date.fromisoformat(rng[1]) - date.fromisoformat(rng[0])).days + 1)
        n, label = estimate_scale(title, venue, days)
        href = a.get("href") if a else None
        if href and href.startswith("/"):
            from urllib.parse import urljoin
            href = urljoin(src["urls"][0], href)
        events.append({
            "venue": venue, "title": title[:120], "url": href or src["urls"][0],
            "start_date": rng[0], "end_date": rng[1],
            "open_time": times.get("open_time"),
            "start_time": times.get("start_time") or src.get("default_open"),
            "end_time": times.get("end_time") or src.get("default_end"),
            "est_attendance": n, "scale_label": label, "source": "html",
        })
    return events


def _urls_for(src: dict, today: date) -> list[str]:
    urls = list(src.get("urls", []))
    if src.get("month_param"):
        for i in range(src.get("months", 2)):
            ym = (today.replace(day=1) + timedelta(days=32 * i)).strftime("%Y%m")
            urls.append(src["month_param"].format(ym=ym))
    return urls


def _purge_bad_titles(conn) -> int:
    """過去に保存した不正タイトルの行を消す。

    抽出ロジックを直しても、DB に残った古い行は消えないため、
    収集のたびに現在の基準で作り直す (自己修復)。
    """
    bad = []
    for row in conn.execute("SELECT id, title FROM events"):
        t = _norm(row["title"] or "")
        if (len(t) < 5 or LABEL_WORDS.match(t) or PAGE_HEADING.match(t)
                or NOISE_TITLE.search(t)):
            bad.append(row["id"])
        elif t != row["title"]:
            # 定型句を落とした結果 別イベント扱いになるので、古い行は消して
            # 今回の収集で正しいタイトルとして入れ直させる
            bad.append(row["id"])
    for eid in bad:
        conn.execute("DELETE FROM events WHERE id=?", (eid,))
    return len(bad)


def collect(conn) -> dict:
    today = now_jst().date()
    purged = _purge_bad_titles(conn)
    total, warnings, per_venue = 0, [], {}
    for src in config.EVENT_SOURCES:
        if src.get("render"):
            # 実ブラウザでの描画が必要な取得先は ariake/render.py の担当。
            # ここでHTTP取得しても空振りするだけなので飛ばす。
            continue
        venue, got = src["venue"], []
        for url in _urls_for(src, today):
            r = fetch(url)
            if r is None:
                continue
            body = r.text
            if url.endswith(".ics") or body.lstrip().startswith("BEGIN:VCALENDAR"):
                got += from_ics(body, venue, src)
                continue
            found = from_jsonld(body, venue, src, today)
            if not found:
                found = from_records(body, venue, src, today)
            if not found:
                found = from_html(body, venue, src, today)
            got += found
        # 同一イベントの重複排除 (期間の広い方を残す)
        merged: dict[tuple, dict] = {}
        for ev in got:
            k = (ev["title"][:60], ev["start_date"])
            old = merged.get(k)
            if not old or ev["end_date"] > old["end_date"]:
                merged[k] = ev
        for ev in merged.values():
            t = ev.get("title") or ""
            # どの抽出器を通っても、ラベルや定型文がタイトルのものは捨てる
            if (len(t) < 5 or LABEL_WORDS.match(t) or PAGE_HEADING.match(t)
                    or NOISE_TITLE.search(t)):
                continue
            store.upsert_event(conn, ev)
        kept = sum(1 for ev in merged.values()
                   if len(ev.get("title") or "") >= 5
                   and not LABEL_WORDS.match(ev["title"])
                   and not PAGE_HEADING.match(ev["title"])
                   and not NOISE_TITLE.search(ev["title"]))
        per_venue[venue] = kept
        total += kept
        if not kept:
            warnings.append(f"{src['label']} からイベントを取得できませんでした"
                            "（サイト改修の可能性／manual_events.json で補完可）")
    rendered = _merge_rendered(conn)
    for venue, n in rendered.items():
        per_venue[venue] = per_venue.get(venue, 0) + n
    total += sum(rendered.values())
    total += _merge_manual(conn)
    conn.commit()
    return {"ok": total > 0, "events": total, "per_venue": per_venue,
            "purged": purged, "warnings": warnings}


def _merge_rendered(conn) -> dict[str, int]:
    """render.py が実ブラウザで取得したイベントを取り込む。"""
    path = os.path.normpath(RENDERED_PATH)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:                               # noqa: BLE001
        print(f"  ! rendered_events.json 読み込み失敗: {e}", flush=True)
        return {}
    counts: dict[str, int] = {}
    for ev in (data.get("events") if isinstance(data, dict) else data) or []:
        if not ev.get("venue") or not ev.get("title") or not ev.get("start_date"):
            continue
        ev.setdefault("end_date", ev["start_date"])
        ev["source"] = "rendered"
        store.upsert_event(conn, ev)
        counts[ev["venue"]] = counts.get(ev["venue"], 0) + 1
    return counts


def _merge_manual(conn) -> int:
    """手入力イベント (manual_events.json) をマージ。"""
    path = os.path.normpath(MANUAL_PATH)
    if not os.path.exists(path):
        return 0
    try:
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
    except Exception as e:                               # noqa: BLE001
        print(f"  ! manual_events.json 読み込み失敗: {e}", flush=True)
        return 0
    n = 0
    for ev in items if isinstance(items, list) else []:
        if not ev.get("venue") or not ev.get("title") or not ev.get("start_date"):
            continue
        ev.setdefault("end_date", ev["start_date"])
        if not ev.get("est_attendance"):
            days = max(1, (date.fromisoformat(ev["end_date"])
                           - date.fromisoformat(ev["start_date"])).days + 1)
            ev["est_attendance"], ev["scale_label"] = estimate_scale(
                ev["title"], ev["venue"], days)
        ev["source"] = "manual"
        store.upsert_event(conn, ev)
        n += 1
    return n
