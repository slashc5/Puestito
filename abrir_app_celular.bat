@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Postuladorsito - modo celular (no cierres esta ventana)
python app_postulador.py --red --navegador
pause
