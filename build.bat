@echo off
REM Rebuild Omnivert.exe from source (icon + code).
setlocal
cd /d "%~dp0"

echo [1/2] Regenerating icon.ico from icon.png...
python make_icon.py

echo [2/2] Building Omnivert.exe...
python -m PyInstaller --noconfirm --windowed --onefile --clean ^
  --name Omnivert --icon icon.ico --add-data "icon.ico;." ^
  --collect-all customtkinter --hidden-import darkdetect omnivert.py

if exist "dist\Omnivert.exe" (
  copy /Y "dist\Omnivert.exe" "Omnivert.exe" >nul
  rmdir /S /Q build 2>nul
  rmdir /S /Q dist 2>nul
  del /Q Omnivert.spec 2>nul
  echo.
  echo Done -> Omnivert.exe
) else (
  echo.
  echo BUILD FAILED.
)
endlocal
pause
