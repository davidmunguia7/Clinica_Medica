@echo off
chcp 65001 >nul
rem Borra y vuelve a crear la base de la presentacion con los datos de ejemplo.
rem No toca la base de trabajo (clinica_familiar). Ver docs\presentacion.md
cd /d "%~dp0.."
set DB_NAME=clinica_presentacion
venv\Scripts\python.exe manage.py preparar_presentacion
echo.
pause
