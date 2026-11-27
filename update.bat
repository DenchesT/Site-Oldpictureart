@echo off
chcp 65001 >nul
cd /d "%~dp0" || exit /b 1
git pull --ff-only || goto :failed
python build_site.py %* || goto :failed
echo Готово!
pause
exit /b 0
:failed
echo Обновление остановлено. Подробности выше.
pause
exit /b 1
