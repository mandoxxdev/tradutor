@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title GMP Tradutor

if not exist ".venv\Scripts\python.exe" (
    echo O sistema ainda nao foi instalado. Clique duas vezes em instalar.bat primeiro.
    pause
    exit /b 1
)

:: Modo offline: nada e consultado na internet durante a reuniao
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
set HF_HUB_DISABLE_TELEMETRY=1
set PYTHONUTF8=1
set KMP_DUPLICATE_LIB_OK=TRUE

echo Iniciando o GMP Tradutor... (feche esta janela para encerrar)
echo.
".venv\Scripts\python.exe" -m servidor %*
if errorlevel 1 (
    echo.
    echo O servidor terminou com erro. Leia a mensagem acima.
    pause
)
