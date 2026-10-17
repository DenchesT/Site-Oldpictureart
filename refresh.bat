@echo off
chcp 65001 >nul
rem Притянуть на сайт правку старого поста из канала (README, «Правка старого поста»).
rem Можно ввести номер поста, ссылку https://t.me/oldpictureart/1234,
rem адрес страницы (sisley-lug-1875.html) или кусок названия.
echo Какой пост обновить?
set /p POST=Номер, ссылка t.me или кусок названия: 
if "%POST%"=="" goto :eof
python build_site.py --refresh "%POST%"
echo.
echo Готово!
pause
