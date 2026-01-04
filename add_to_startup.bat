@echo off
set "SCRIPT_PATH=%~dp0run_bot.bat"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\AscendLimitsBot.lnk"

echo Adding to startup...
echo Script Path: %SCRIPT_PATH%
echo Startup Folder: %STARTUP_FOLDER%

powershell "$s=(New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT_PATH%');$s.TargetPath='%SCRIPT_PATH%';$s.Save()"

echo.
echo Success! The bot will now run automatically when you log in.
pause
