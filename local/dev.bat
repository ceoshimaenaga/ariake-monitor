@echo off
chcp 65001 >nul
REM 開発用。designs\5-atlas.html をそのまま配信するので、
REM 保存してブラウザを再読み込みすれば、組み直さずに反映されます。
cd /d "%~dp0.."
echo === http://localhost:8788/designs/5-atlas.html を開いてください ===
echo (このウィンドウを閉じると止まります)
start "" http://localhost:8788/designs/5-atlas.html
python -m http.server 8788
