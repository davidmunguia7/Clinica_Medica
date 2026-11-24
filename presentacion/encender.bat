@echo off
chcp 65001 >nul
rem Enciende el sistema para la presentacion y lo publica con una direccion https.
rem Usa la base clinica_presentacion (preparar_datos.bat). Ver docs\presentacion.md
cd /d "%~dp0.."

where cloudflared >nul 2>nul
if errorlevel 1 goto sin_cloudflared

set DB_NAME=clinica_presentacion
set DEBUG=False
set ALLOWED_HOSTS=localhost,127.0.0.1,.trycloudflare.com
set CSRF_TRUSTED_ORIGINS=https://*.trycloudflare.com

echo Encendiendo el sistema en otra ventana...
start "Clinica Familiar - servidor de la presentacion" cmd /k venv\Scripts\waitress-serve.exe --listen=127.0.0.1:8080 --threads=8 sistema_clinico.wsgi:application
echo.
echo En unos segundos aparece abajo la direccion publica: termina en .trycloudflare.com
echo Esa es la que se le pasa al profesor. En esta computadora tambien sirve http://127.0.0.1:8080
echo Para apagar todo: cierre esta ventana y la del servidor.
echo.
cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8080
goto fin

:sin_cloudflared
echo Falta instalar cloudflared. En PowerShell escriba:
echo     winget install --id Cloudflare.cloudflared
echo y despues cierre y vuelva a abrir esta ventana.

:fin
echo.
pause
