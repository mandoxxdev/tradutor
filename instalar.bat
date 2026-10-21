@echo off
:: Mensagens sem acento de proposito: este .bat NAO deve usar "chcp 65001", porque o cmd
:: do Windows falha ao executar arquivos .bat em pastas com acento quando esta em UTF-8.
setlocal EnableExtensions
cd /d "%~dp0"
title GMP Tradutor - Instalacao
set PYTHONUTF8=1
set PIP_DISABLE_PIP_VERSION_CHECK=1

echo ======================================================================
echo   GMP Tradutor - instalacao (roda uma unica vez, precisa de internet)
echo ======================================================================
echo.

:: ---------------------------------------------------------------- Python
set "PY="
for %%V in (3.12 3.11 3.10) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    for %%V in (312 311 310) do (
        if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
    )
)
if not defined PY (
    python -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,12) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo Python 3.10, 3.11 ou 3.12 nao foi encontrado neste computador.
    echo Vou instalar o Python 3.11 para o seu usuario usando o winget ^(gerenciador de pacotes do Windows^).
    echo.
    winget --version >nul 2>&1
    if errorlevel 1 (
        echo O winget nao esta disponivel. Instale o Python 3.11 manualmente em:
        echo    https://www.python.org/downloads/windows/
        echo Marque a opcao "Add python.exe to PATH" e rode este instalador de novo.
        pause
        exit /b 1
    )
    winget install -e --id Python.Python.3.11 --scope user --silent --accept-package-agreements --accept-source-agreements
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    ) else (
        echo Nao foi possivel instalar o Python automaticamente. Instale manualmente e rode de novo.
        pause
        exit /b 1
    )
)
echo Python encontrado: %PY%
%PY% --version

:: ---------------------------------------------------------------- venv
:: Uma .venv copiada de outro computador aponta para um Python que nao existe aqui: recria.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys" >nul 2>&1 || (
        echo O ambiente .venv veio de outro computador e nao funciona aqui. Recriando...
        rmdir /s /q ".venv"
    )
)
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Criando o ambiente Python em .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo ERRO ao criar o ambiente. Verifique se a pasta nao esta protegida.
        pause
        exit /b 1
    )
)
set "VPY=.venv\Scripts\python.exe"

echo.
echo Instalando as dependencias (pode levar alguns minutos)...
"%VPY%" -m pip install --upgrade pip >nul
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERRO ao instalar as dependencias. Verifique a conexao com a internet e rode de novo.
    pause
    exit /b 1
)

:: ---------------------------------------------------------------- GPU
set "GPU=0"
nvidia-smi >nul 2>&1 && set "GPU=1"
if "%GPU%"=="1" (
    echo.
    echo GPU NVIDIA detectada: instalando as bibliotecas CUDA ^(cuBLAS e cuDNN^)...
    "%VPY%" -m pip install -r requirements-cuda.txt
    if errorlevel 1 echo Aviso: nao foi possivel instalar as bibliotecas CUDA; o sistema vai usar a CPU.
) else (
    echo.
    echo Nenhuma GPU NVIDIA detectada: o sistema vai rodar na CPU ^(modelo "small"^).
)

:: ---------------------------------------------------------------- Argos (opcional)
if /i "%~1"=="argos" (
    echo.
    echo Instalando o motor alternativo Argos Translate ^(opcional, puxa o PyTorch^)...
    "%VPY%" -m pip install -r requirements-argos.txt
)

:: ---------------------------------------------------------------- Modelos
echo.
echo Baixando os modelos de voz e traducao ^(uma unica vez: cerca de 1 GB sem GPU, 3 GB com GPU^)...
if /i "%~1"=="argos" (
    "%VPY%" instalacao\baixar_modelos.py --argos pt en it es de fr
) else (
    "%VPY%" instalacao\baixar_modelos.py
)
if errorlevel 1 (
    echo ERRO no download dos modelos. Verifique a internet e rode instalar.bat de novo ^(o download continua de onde parou^).
    pause
    exit /b 1
)

echo.
echo Verificando a instalacao...
"%VPY%" instalacao\verificar.py
echo.
echo ======================================================================
echo   Instalacao concluida. Para usar: clique duas vezes em iniciar.bat
echo ======================================================================
pause
