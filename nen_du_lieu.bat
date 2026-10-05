@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=
where py >nul 2>nul && set PY=py -3
if "%PY%"=="" where python >nul 2>nul && set PY=python
if "%PY%"=="" (
  echo [LOI] May chua cai Python hoac chua them vao PATH.
  echo Cai Python tai https://www.python.org/downloads/ ^(tick "Add python.exe to PATH", khong can quyen admin^)
  echo hoac cai tu Microsoft Store: tim "Python 3.12".
  pause
  exit /b 1
)
if not exist NGUON (
  echo [LOI] Khong thay thu muc NGUON canh file nay.
  pause
  exit /b 1
)
echo Dang nen du lieu hoa don ^(NGUON -^> DATA^)...
%PY% nen_du_lieu.py NGUON DATA
echo.
pause
