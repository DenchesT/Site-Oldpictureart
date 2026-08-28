@echo off
chcp 65001 >nul
echo Пересборка страниц из posts_meta.json (без Telegram)...
python rebuild_pages.py
echo.
echo Готово!
pause
