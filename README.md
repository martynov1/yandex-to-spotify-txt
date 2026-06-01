# yandex-to-spotify

CLI-инструмент для импорта плейлистов из Яндекс Музыки в Spotify.

## Возможности

- **Окно (GUI)** на customtkinter и параллельно полноценный **CLI** — два
  взаимозаменяемых интерфейса над одним и тем же ядром.
- Список своих плейлистов в Яндекс Музыке (включая «Мне нравится»).
- Создание плейлиста в Spotify и автоматический поиск треков.
- Точное сопоставление по **ISRC**, когда он доступен, с откатом на fuzzy-поиск по
  названию, исполнителю и длительности — устойчиво к ремастерам, фит-сноскам и т.п.
- Режим dry-run: только посмотреть, что будет сопоставлено, без создания плейлиста.
- Перенос нескольких/всех плейлистов разом.
- Список ненайденных треков и список сопоставлений с низкой уверенностью пишутся в
  отдельные файлы, чтобы их можно было пересмотреть руками.

## Установка

```bash
cd yandex-to-spotify
python3.11 -m venv .venv   # или: uv venv --python 3.11 .venv
source .venv/bin/activate
pip install -e .
```

Требуется Python 3.10+.

## Настройка

1. Скопируйте `.env.example` в `.env`.
2. Заполните:
   - `YANDEX_MUSIC_TOKEN` — токен Яндекс Музыки. Способы получения:
     <https://yandex-music.readthedocs.io/en/main/token.html>
   - `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` — создайте приложение в
     [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
   - `SPOTIFY_REDIRECT_URI` — должен совпадать со значением, указанным в настройках
     приложения Spotify. По умолчанию `http://127.0.0.1:8888/callback`.

## Использование

### Окно (GUI)

```bash
yandex-to-spotify-gui
```

Поля учётных данных предзаполняются из `.env`. Нажмите «Подключиться», выберите
нужные плейлисты галочками, при желании измените порог совпадения / префикс и
жмите «Импортировать выбранные». Прогресс и журнал — внизу окна; файлы
`unmatched_*.txt` и `review_*.txt` появятся в текущем каталоге.

### CLI

Посмотреть свои плейлисты:

```bash
yandex-to-spotify list
```

Импортировать один плейлист (`kind` берётся из колонки `kind` команды `list`):

```bash
yandex-to-spotify import 3
yandex-to-spotify import liked --name "Liked from Yandex"
yandex-to-spotify import 3 --public --threshold 0.55
yandex-to-spotify import 3 --dry-run     # ничего не создаст, только покажет статистику
```

Импортировать сразу все плейлисты:

```bash
yandex-to-spotify import-all --prefix "[YM] "
yandex-to-spotify import-all --skip-liked --dry-run
```

При первом запуске Spotify откроет браузер для OAuth-авторизации;
токен будет закэширован в файле `.spotify_cache`.

### Выходные файлы

- `unmatched_<id>.txt` — треки, которые не удалось найти в Spotify.
- `review_<id>.txt` — сопоставления с низкой уверенностью (score < 0.8).
  Формат строки: `[score] Yandex artist — title → Spotify artist — title`.

Имена этих файлов можно переопределить флагами `--unmatched-out` и `--review-out`.

## Разработка

```bash
pip install -e ".[dev]"
pytest
```

Иконка приложения генерируется скриптом:

```bash
python scripts/generate_icon.py
```

Результат — `src/yandex_to_spotify/assets/icon*.png`, лежит в git, чтобы при
обычной установке Pillow не требовался. Окно подхватывает иконку через
`iconphoto`. На macOS дополнительно используется PyObjC, чтобы поменять
иконку в Dock (зависимость подтягивается автоматически при установке на macOS).
Без бандлинга в `.app` Dock-иконка будет жить только пока окно открыто — это
ограничение запуска Python-скриптов на macOS, не баг.

## Архитектура

```text
src/yandex_to_spotify/
  models.py         — Track, Playlist, PlaylistSummary (dataclasses)
  yandex_client.py  — клиент Яндекс Музыки
  spotify_client.py — клиент Spotify Web API (через spotipy)
  matcher.py        — ISRC + fuzzy-поиск трека в Spotify
  transfer.py       — оркестрация импорта одного плейлиста; передаёт прогресс
                      через колбэки, поэтому общим ядром пользуются и CLI, и GUI
  cli.py            — Click CLI
  gui.py            — customtkinter-окно; всё I/O — в фоновых потоках, обмен
                      с UI через queue.Queue
  assets/icon*.png  — иконка приложения
tests/
  test_matcher.py   — оффлайн-тесты матчинга через подменённый Spotify-клиент
scripts/
  generate_icon.py  — пересборка иконки (нужен Pillow)
```

## Ограничения

- `yandex-music` — неофициальная библиотека; поведение может меняться вслед за API.
- Поиск по Spotify зависит от их каталога в вашем регионе — часть треков может быть
  недоступна.
- ISRC присутствует не у всех треков Яндекс Музыки. Когда его нет, работает fuzzy.
- Threshold по умолчанию (0.6) — компромисс между полнотой и точностью. Поднимите его,
  если получаете слишком много ложных совпадений, или понизьте, если теряете треки.
