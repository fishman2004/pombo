@echo off
rem Instala o Pombo nesta pasta. Nao precisa de administrador.
cd /d "%~dp0"
echo.
echo  Instalando o Pombo...
echo.

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo  Nao encontrei o Python. Instale o Python 3.12 ou mais novo
  echo  marcando "Install for me only" e rode este arquivo de novo.
  echo  Passo a passo no README.md.
  pause
  exit /b 1
)

%PY% -m venv .venv
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
