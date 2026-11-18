@echo off
setlocal
cd /d "%~dp0"
set "NASM=nasm"
if defined NASM_EXE set "NASM=%NASM_EXE%"

echo Building 2BASIC and 2BRES with NASM...
"%NASM%" -v >nul 2>&1
if errorlevel 1 (
  echo ERROR: NASM not found. Put nasm.exe on PATH or set NASM_EXE.
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "tools\get_sdk.ps1"
if errorlevel 1 (
  echo ERROR: Could not locate the compatible OS8088 include.
  exit /b 1
)

if not exist "dist" mkdir "dist"
"%NASM%" -f bin -w+error -I"%~dp0sdk/apps/" -o "dist\2BASIC.O88" "src\2basic.asm"
if errorlevel 1 goto fail
"%NASM%" -f bin -w+error -I"%~dp0sdk/apps/" -o "dist\2BRES.O88" "src\2bres.asm"
if errorlevel 1 goto fail

echo.
echo BUILD PASSED:
echo   dist\2BASIC.O88
echo   dist\2BRES.O88
echo.
echo OPTIONAL: Run MAKEDISK.BAT to create a B: disk image.
exit /b 0
:fail
echo.
echo BUILD FAILED. See NASM errors above.
exit /b 1
