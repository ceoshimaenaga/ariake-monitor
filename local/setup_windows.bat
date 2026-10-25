@echo off
chcp 65001 >nul
REM ============================================================
REM  有明 混雑マップ ローカル運用セットアップ (Windows / RTX機)
REM  ・必要なものを入れる
REM  ・毎時の収集をタスクに登録する
REM  ※「管理者として実行」してください
REM ============================================================
setlocal
set DIR=%~dp0..
pushd "%DIR%"
set DIR=%CD%
echo インストール先: %DIR%
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [エラー] python が PATH にありません。
  echo          https://www.python.org/downloads/ から入れて、
  echo          インストール時に "Add python.exe to PATH" にチェックしてください。
  pause & popd & exit /b 1
)

echo --- ライブラリを入れます
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 (echo [エラー] pip install に失敗しました & pause & popd & exit /b 1)

echo.
echo --- ブラウザを入れます (イベント表の読み取り用。初回のみ数分かかります)
python -m pip install playwright
python -m playwright install chromium
if errorlevel 1 (echo [警告] ブラウザの導入に失敗しました。--render なしなら動きます)

echo.
echo --- 毎時の収集をタスクに登録します
schtasks /Create /F /TN "AriakeMonitor_Collect" /SC HOURLY /ST 00:07 ^
  /TR "cmd /c cd /d \"%DIR%\" && python local\refresh.py --push >> local\refresh.log 2>&1" ^
  /RL HIGHEST
if errorlevel 1 (echo [警告] タスクの登録に失敗しました) else (echo [OK] 毎時7分に収集します)

echo.
echo --- 初回の収集を今すぐ実行します
python local\refresh.py --render
echo.
echo ============================================================
echo  セットアップ完了
echo.
echo   手元で見る      local\serve.bat
echo   公開する        local\publish.bat   (cloudflared が要ります)
echo   手動で更新      python local\refresh.py --push
echo   ログ            local\refresh.log
echo ============================================================
pause
popd
