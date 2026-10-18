@echo off
rem Abre o Pombo (sem janela preta). Se ja estiver aberto, so mostra a tela.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo  O Pombo ainda nao foi instalado. Rode instalar.bat primeiro.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m pombo
