@echo off
REM Gera a pasta dist\FlightTracker com FlightTracker.exe (arranque rapido)
REM Se a janela nativa falhar no PC de destino, a app abre no navegador (ou corre: FlightTracker.exe --browser)
REM Requisito: Python 3.11+ de https://www.python.org/downloads/windows/ (marcar "Add python.exe to PATH")
cd /d "%~dp0"
set PY=
py -3 -c "import sys" >nul 2>&1 && set PY=py -3
if not defined PY python -c "import sys" >nul 2>&1 && set PY=python
if not defined PY (
  echo.
  echo *** Python nao encontrado ***
  echo Instala o Python 3.12 em https://www.python.org/downloads/windows/
  echo e marca a opcao "Add python.exe to PATH" no instalador.
  echo Se ja estiver instalado: Definicoes ^> Aplicacoes ^> Aliases de execucao de aplicacoes
  echo e desliga os aliases python.exe / python3.exe da Microsoft Store.
  echo.
  echo Alternativa sem instalar nada: GitHub ^> Actions ^> ultimo run ^> Artifacts ^> FlightTracker-windows
  pause
  exit /b 1
)
echo A usar: %PY%
echo [1/3] A instalar dependencias...
%PY% -m pip install --upgrade pip >nul
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto :erro
echo [2/3] A gerar executavel...
%PY% -m PyInstaller --noconfirm --clean --onedir --windowed --name FlightTracker ^
  --add-data "ui;ui" --add-data "data;data" --collect-all duckdb --collect-all webview --collect-all pptx --hidden-import openpyxl --hidden-import tkinter app.py
if errorlevel 1 goto :erro
echo [3/3] Concluido: pasta dist\FlightTracker (correr FlightTracker.exe la dentro)
pause
exit /b 0
:erro
echo.
echo *** Ocorreu um erro. Copia o texto acima e envia ao Claude. ***
pause
exit /b 1
