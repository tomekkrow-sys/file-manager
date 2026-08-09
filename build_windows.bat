@echo off
REM Buduje file-manager.exe dla Windows (PyInstaller).
REM Wymagania: Python 3.11+ z python.org, potem dwuklik na ten plik.
setlocal
cd /d "%~dp0"

echo === File Manager - budowanie EXE (Windows) ===

if not exist .venv (
    echo ==^> Tworze srodowisko virtualne...
    py -m venv .venv
)

call .venv\Scripts\activate.bat

echo ==^> Instaluje zaleznosci...
pip install --quiet -r requirements.txt pyinstaller

echo ==^> PyInstaller...
python -m PyInstaller --noconfirm --clean file_manager.spec

echo.
echo === GOTOWE: dist\file-manager\file-manager.exe ===
echo Caly folder dist\file-manager to przenosna aplikacja - mozna go
echo skopiowac na inny komputer i uruchomic file-manager.exe.
pause
