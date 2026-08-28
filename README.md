# Site-Oldpictureart

Статический сайт-галерея картин, который собирается из постов Telegram-канала
[@oldpictureart](https://t.me/oldpictureart). Готовые страницы лежат в `docs/`
и публикуются через GitHub Pages.

## Что где

| Файл | Зачем |
|---|---|
| `build_site.py` | Основной сборщик: забирает новые посты из Telegram, качает картинки, генерирует страницы картин, теги, главную, sitemap, RSS, манифест |
| `rebuild_pages.py` | Пересборка всех страниц из `posts_meta.json` **без Telegram** — когда правится только вёрстка |
| `site_common.py` | Общий `<head>`, бутстрап темы и общие скрипты для всех генераторов |
| `generate_quiz.py` | Страница квиза |
| `generate_timeline.py` | Страница таймлайна |
| `generate_map.py` | Карта музеев (координаты кэшируются в `museum_coordinates.json`) |
| `docs/style.css` | Все стили сайта |
| `posts_meta.json` | База постов: художник, название, музей, техника, файлы картинок |

## Запуск

```bash
# полная сборка с забором новых постов (нужен .env)
python build_site.py

# только пересобрать HTML из уже скачанных данных
python rebuild_pages.py

# то же, но не трогать карту (не ходить в Nominatim)
python rebuild_pages.py --no-map
```

На Windows: `update.bat` — полная сборка, `rebuild.bat` — только пересборка страниц.

## .env

```
API_ID=...
API_HASH=...
PHONE=+7...
```

Файл в `.gitignore` и в репозиторий не попадает.

## Правила вёрстки

HTML собирается генераторами, поэтому **править файлы в `docs/*.html` бесполезно** —
следующая сборка их перезапишет. Разметку меняем в `*.py`, стили — в `docs/style.css`,
после чего прогоняем `python rebuild_pages.py`.
