@echo off
chcp 65001 >nul
REM この PC から直接公開する (熱海モニターと同じ cloudflared 方式)。
REM 事前に一度だけ:
REM   cloudflared tunnel login
REM   cloudflared tunnel create ariake
REM   cloudflared tunnel route dns ariake ariake.shukuhakudaichou.com
REM   %USERPROFILE%\.cloudflared\config.yml に転送先 http://localhost:8787 を書く
cd /d "%~dp0.."
python ariake\build_site.py
start "ariake-server" /min python -m http.server 8787 -d _site
timeout /t 2 >nul
echo === 固定URL: https://ariake.shukuhakudaichou.com ===
echo (このウィンドウは閉じないでください。閉じるとトンネルが止まります)
cloudflared.exe tunnel run ariake
