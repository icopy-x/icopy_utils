cd /d %~dp0

del /a /f /s /q "*.ipk"

taskkill /F /T /IM LE_console.exe
cd netcoreapp3.1
start LE_console.exe

choice /t 2 /d y

cd /d %~dp0
choice /t 2 /d y
taskkill /F /T /IM gui_main_menu.exe
start gui_main_menu.exe