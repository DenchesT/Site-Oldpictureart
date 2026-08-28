@echo off
chcp 65001 >nul
echo Запуск парсинга...
python build_site.py
echo.
echo Готово!
pause
