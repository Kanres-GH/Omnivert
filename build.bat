@echo off
REM Build Omnivert in one-folder mode (fast startup), then zip it for release.
setlocal
cd /d "%~dp0"

echo [1/3] Regenerating icon.ico from ico_test.png...
python make_icon.py

echo [2/3] Building (one-folder)...
python -m PyInstaller --noconfirm --windowed --clean ^
  --name Omnivert --icon icon.ico ^
  --add-data "icon.ico;." --add-data "web;web" ^
  --collect-all webview omnivert.py

if exist "dist\Omnivert\Omnivert.exe" (
  echo [3/3] Zipping dist\Omnivert -^> Omnivert.zip ...
  if exist "Omnivert.zip" del /Q "Omnivert.zip"
  powershell -NoProfile -Command "Compress-Archive -Path 'dist\Omnivert' -DestinationPath 'Omnivert.zip' -Force"
  rmdir /S /Q build 2>nul
  del /Q Omnivert.spec 2>nul
  echo.
  echo Done.
  echo   Run locally:  dist\Omnivert\Omnivert.exe
  echo   Distribute:   Omnivert.zip  ^(extract, then run Omnivert.exe inside^)
) else (
  echo.
  echo BUILD FAILED.
)
endlocal
pause
