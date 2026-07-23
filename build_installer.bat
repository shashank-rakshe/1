@echo off
REM Builds dcad end-to-end on Windows: venv, dependencies, the single-file
REM exe (dcad.spec), then the installer wizard (installer.iss) if Inno
REM Setup is installed. Double-click this file, or run it from a command
REM prompt in this repo's root folder. See README.md "Packaging as an
REM executable" for what each step does and how to fix common failures.
setlocal enabledelayedexpansion

where python >nul 2>nul
if errorlevel 1 (
    echo [dcad] Python was not found on PATH. Install Python 3.11+ from
    echo        https://python.org/downloads/ ^(check "Add python.exe to PATH"
    echo        during install^), then re-run this script.
    pause
    exit /b 1
)

echo [dcad] Creating/activating the virtual environment...
if not exist .venv (
    python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat || goto :error

echo [dcad] Installing dependencies...
pip install -r requirements.txt || goto :error
pip install pyinstaller || goto :error

echo [dcad] Building dist\dcad.exe...
pyinstaller --noconfirm dcad.spec || goto :error

where iscc >nul 2>nul
if errorlevel 1 (
    echo.
    echo [dcad] dist\dcad.exe built successfully.
    echo [dcad] Inno Setup's "iscc" was not found on PATH, so the installer
    echo        wizard was skipped. dist\dcad.exe already runs on its own --
    echo        install Inno Setup from https://jrsoftware.org/isdl.php and
    echo        re-run this script to also produce a proper installer.
    pause
    exit /b 0
)

echo [dcad] Building the installer wizard...
iscc installer.iss || goto :error

echo.
echo [dcad] Done. installer_output\dcad-setup.exe is ready to hand out.
pause
exit /b 0

:error
echo.
echo [dcad] A step above failed -- scroll up for the actual error. See
echo        README.md "Packaging as an executable" for troubleshooting
echo        (common causes: a missing OCP DLL, or a missing hidden import).
pause
exit /b 1
