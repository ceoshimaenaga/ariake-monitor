"""手元の PC だけで、収集から公開までを一度に回す。

    python local/refresh.py            # 収集してサイトを組む
    python local/refresh.py --push     # そのうえで GitHub に反映する
    python local/refresh.py --render   # イベント表がJSで描かれるサイトも読む

クラウド (GitHub Actions) でやっていたことと同じ内容を、順番に実行する。
観測ログ (ariake.db) はこの PC に残るので、動かすほど平常値の精度が上がる。
Actions のキャッシュと違って揮発しない。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(args: list[str], what: str) -> bool:
    print(f"\n--- {what}", flush=True)
    t = time.time()
    r = subprocess.run([sys.executable] + args, cwd=ROOT)
    ok = r.returncode == 0
    print(f"--- {what}: {'OK' if ok else '失敗'} ({time.time() - t:.1f}s)", flush=True)
    return ok


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git"] + list(args), cwd=ROOT,
                          capture_output=True, text=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true",
                    help="ariake.json をコミットして GitHub に反映する")
    ap.add_argument("--render", action="store_true",
                    help="JS で描かれるイベント表も読む (Playwright が要る)")
    args = ap.parse_args()

    # JS で描かれるページは、必要なときだけ。毎時やるには重い。
    if args.render:
        run(["ariake/render.py"], "イベント表を読む (ブラウザ)")

    if not run(["ariake/collect.py"], "混雑データを集める"):
        print("\n収集に失敗しました。ネットワークか、施設側のページの変更が原因です。",
              flush=True)
        raise SystemExit(1)

    run(["ariake/build_site.py"], "公開用サイトを組む")

    if not args.push:
        print("\n完了。手元で見るには local\\serve.bat を実行してください。", flush=True)
        return

    st = git("status", "--porcelain", "ariake.json")
    if not st.stdout.strip():
        print("\nデータに変更なし。反映はしません。", flush=True)
        return
    print("\n--- GitHub に反映", flush=True)
    git("add", "ariake.json")
    git("commit", "-m", "chore: refresh ariake congestion data")
    # 手元とクラウドの両方が触っている間は、取り込んでから送る
    git("pull", "--rebase", "--autostash", "origin", "main")
    p = git("push", "origin", "HEAD:main")
    print(p.stdout + p.stderr, flush=True)
    print("--- 反映: " + ("OK" if p.returncode == 0 else "失敗"), flush=True)


if __name__ == "__main__":
    main()
