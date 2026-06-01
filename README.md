# yandex-to-spotify-txt

Десктоп-приложение для экспорта плейлистов Яндекс Музыки в текстовые файлы.
Для каждого выбранного плейлиста создаётся `.txt`, где каждая строка — `Артист - Трек`.
Дальше этими файлами можно загрузить треки в Spotify или любой другой сервис
(SpotMyBackup, Soundiiz, TuneMyMusic и т.п.).

## Установка

```bash
git clone git@github.com:martynov1/yandex-to-spotify-txt.git
cd yandex-to-spotify-txt
python3.11 -m venv .venv     # или: uv venv --python 3.11 .venv
source .venv/bin/activate
pip install -e .
```

Требуется Python 3.10+.

## Получение токена Яндекс Музыки

В Яндекс Музыке нет публичного OAuth для сторонних приложений, токен получается
через device-auth поток. Запустите скрипт ниже — он откроет в консоли ссылку и код,
по которым нужно подтвердить вход в браузере под вашим Яндекс-аккаунтом:

```python
from yandex_music import Client


def on_code(code):
    print(f'Откройте {code.verification_url} и введите код: {code.user_code}')


client = Client()
token = client.device_auth(on_code=on_code)

# Сохраните токен, чтобы не проходить авторизацию заново.
print(f'access_token:  {token.access_token}')
print(f'refresh_token: {token.refresh_token}')
print(f'expires_in:    {token.expires_in}')

client.init()
print(client.me.account.login)
```

Сохраните `access_token` — это и есть значение для поля **Yandex token** в приложении
(или переменной `YANDEX_MUSIC_TOKEN` в `.env`).

## Использование

```bash
yandex-to-spotify-gui
```

1. Вставьте Yandex-токен в поле (кнопка «Вставить» забирает из буфера).
2. Нажмите **Подключиться** — загрузится список ваших плейлистов и «Мне нравится».
3. Отметьте галочками нужные плейлисты.
4. Нажмите **Экспортировать в TXT** — откроется диалог выбора папки.
5. Для каждого плейлиста создастся файл `<название>.txt` в выбранной папке.

### Формат выходного файла

Одна строка — один трек:

```text
Linkin Park - Numb
Muse - Uprising
The Beatles, John Lennon - Imagine
```

У треков с несколькими артистами имена перечислены через запятую.

### Загрузка файла в Spotify

В самом Spotify импорта из текста нет, но это умеют сторонние сервисы:

- **Soundiiz** (soundiiz.com) — есть бесплатный план, ест список треков и переносит в плейлист.
- **TuneMyMusic** (tunemymusic.com) — то же самое, но платный для больших списков.
- **SpotMyBackup** — open-source, нужно немного фиддлить с CSV.

## Разработка

```bash
pip install -e ".[dev]"
pytest
```

Иконка генерируется скриптом:

```bash
python scripts/generate_icon.py
```

## Архитектура

```text
src/yandex_to_spotify/
  models.py         — Track, Playlist, PlaylistSummary
  yandex_client.py  — клиент Яндекс Музыки
  gui.py            — окно на customtkinter
  assets/icon*.png  — иконка приложения
```

Файлы `spotify_client.py`, `transfer.py`, `matcher.py`, `cli.py` остались
от предыдущей итерации (импорт в Spotify через Web API), сейчас не используются
GUI и оставлены на случай возврата к ней.

## Ограничения

- `yandex-music` — неофициальная библиотека; поведение может меняться вслед за API.
- На macOS с Python из uv (Tk 9.0) + customtkinter 5.2.2 не работают системные
  Cmd+V и Cmd+C в полях ввода — для этого добавлена кнопка «Вставить» рядом с полем токена.
