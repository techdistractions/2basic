@echo off
setlocal
cd /d "%~dp0"
if not exist "dist\2BASIC.O88" goto nofiles
if not exist "dist\2BRES.O88" goto nofiles

where py.exe >nul 2>nul
if not errorlevel 1 goto with_py
where python.exe >nul 2>nul
if not errorlevel 1 goto with_python
echo ERROR: Python 3 is required only for optional disk-image creation.
exit /b 1

:nofiles
echo ERROR: Run MAKE.BAT first, or copy both O88 binaries into dist.
exit /b 1

:with_py
py -3 "tools\makedisk.py"
exit /b %errorlevel%

:with_python
python "tools\makedisk.py"
exit /b %errorlevel%
