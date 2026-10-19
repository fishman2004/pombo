@echo off
rem Instala o Pombo nesta pasta. Nao precisa de administrador.
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
echo.
echo  Instalando o Pombo...
echo.

set "PY="
py -3.13 --version >nul 2>nul
if not errorlevel 1 set "PY=py -3.13"
if not defined PY (
  py -3.12 --version >nul 2>nul
  if not errorlevel 1 set "PY=py -3.12"
)
if not defined PY (
  set "PYVER="
  for /f "tokens=2" %%V in ('python --version 2^>^&1') do set "PYVER=%%V"
  if "!PYVER:~0,4!"=="3.12" set "PY=python"
  if "!PYVER:~0,4!"=="3.13" set "PY=python"
)
if not defined PY (
  echo  Nao encontrei um Python compativel.
  echo  Instale o Python 3.13 em https://www.python.org/downloads/
  echo  e marque "Add python.exe to PATH" durante a instalacao.
  pause
  exit /b 1
)

echo  Python selecionado:
%PY% --version
echo.

%PY% -m venv --clear .venv
if errorlevel 1 (
  echo  Falha ao criar o ambiente. Veja o README.md.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo  Falha ao instalar as dependencias. Verifique a internet e tente de novo.
  pause
  exit /b 1
)

echo.
echo  Pronto! Agora de dois cliques em iniciar.bat
echo.
pause
