@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Postuladorsito (no cierres esta ventana mientras uses la app)
python app_postulador.py %*
if errorlevel 1 pause
