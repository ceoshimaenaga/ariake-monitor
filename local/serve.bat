@echo off
chcp 65001 >nul
REM 手元で地図を見る。編集 → ブラウザを再読み込み、で反映されます。
cd /d "%~dp0.."
echo --- サイトを組み直します
python ariake\build_site.py
echo.
echo === http://localhost:8787/ を開いてください ===
echo (このウィンドウを閉じると止まります)
start "" http://localhost:8787/
python -m http.server 8787 -d _site
