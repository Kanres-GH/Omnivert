@echo off
REM Rebuild Converter.exe from source (icon + code).
setlocal
cd /d "%~dp0"

echo [1/2] Regenerating icon.ico from icon.png...
python make_icon.py

echo [2/2] Building Converter.exe...
python -m PyInstaller --noconfirm --windowed --onefile --clean ^
  --name Converter --icon icon.ico --add-data "icon.ico;." ^
  --collect-all customtkinter --hidden-import darkdetect converter.py

if exist "dist\Converter.exe" (
  copy /Y "dist\Converter.exe" "Converter.exe" >nul
  rmdir /S /Q build 2>nul
  rmdir /S /Q dist 2>nul
  del /Q Converter.spec 2>nul
  echo.
  echo Done -> Converter.exe
) else (
  echo.
  echo BUILD FAILED.
)
endlocal
pause
