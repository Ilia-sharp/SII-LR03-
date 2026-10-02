# Лабораторная работа №3 — Whisper и ключевые слова

**Дисциплина:** Системы искусственного интеллекта  
**Курс:** 4  
**Вариант:** №16  
**scenario_id:** `car_wash`  
**Сценарий:** Автомойка  
**Репозиторий GitVerse:** `SII-LR03-NazdraTenko`  
**Тег:** `v1.0`

## Цель
Собран аудиосервис по цепочке:

**аудиофайл → декодирование → faster-whisper → текст → поиск ключевых слов → API**.

Ключевые слова варианта №16: `мойка`, `кузов`, `салон`, `запись`.

## Что реализовано

- `POST /transcribe` — принимает аудиофайл и возвращает транскрипцию, сегменты и найденные ключевые слова.
- `GET /health` — проверка доступности сервиса.
- Русский язык: `language=ru`.
- CPU-only Whisper: модель `base`, `int8`.
- Модель загружается **один раз при старте** приложения.
- Ключевые слова находятся в `config/keywords.yaml`, а не в Python-коде; поиск учитывает словоформы («мойку», «записаться», «кузова»).
- Проверяются пустой файл, неподдерживаемое расширение/формат и превышение лимита `60` секунд.
- FFmpeg используется для декодирования и приведения звука к `mono / 16 kHz / s16`.
- Подготовлены 5 коротких sample-аудиофайлов в `samples/`.
- Есть unit-тесты и smoke-тест API.

## Структура

```text
SII-LR03-NazdraTenko/
├── app/
│   ├── __init__.py
│   ├── asr.py
│   ├── audio.py
│   ├── config.py
│   ├── keywords.py
│   ├── main.py
│   └── schemas.py
├── config/
│   └── keywords.yaml
├── static/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── samples/
│   ├── 01_booking_wash.wav
│   ├── 02_body_wash.wav
│   ├── 03_interior.wav
│   ├── 04_full_service.wav
│   ├── 05_wash_body_interior.wav
│   └── README.md
├── scripts/
│   ├── run.ps1
│   ├── test.ps1
│   └── smoke_test.ps1
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_config.py
│   ├── test_keywords.py
│   └── test_ui.py
├── Dockerfile
├── render.yaml
├── .env.example
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
├── REPORT.md
└── README.md
```

## Установка на Windows

Нужны **Python 3.12+** и **FFmpeg** в `PATH`.

Проверка:

```powershell
python --version
ffmpeg -version
```

Создание окружения и установка зависимостей:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Запуск

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

После запуска:

- Swagger: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

При **первом запуске** сервиса faster-whisper один раз скачает модель `base` (~140 МБ, нужен интернет) — старт займёт чуть дольше. Дальше модель берётся из локального кэша и загружается один раз при старте.

### One-click для Windows

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\run.ps1
```

## Проверка API

### Health

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Ожидается:

```json
{"status":"ok"}
```

### Transcribe

```powershell
curl.exe -X POST http://127.0.0.1:8000/transcribe -F "file=@samples\\04_full_service.wav"
```

Формат ответа:

```json
{
  "scenario_id": "car_wash",
  "scenario_name": "Автомойка",
  "text": "...",
  "language": "ru",
  "segments": [
    {"start": 0.0, "end": 3.2, "text": "..."}
  ],
  "keywords_found": [
    {"keyword": "мойка", "count": 1},
    {"keyword": "кузов", "count": 1},
    {"keyword": "салон", "count": 1},
    {"keyword": "запись", "count": 1}
  ],
  "model": "whisper-base",
  "model_version": "v1.0",
  "latency_ms": 3200
}
```

Значение `latency_ms` зависит от ПК и фактической длины аудио.

## Тесты

Unit-тесты без загрузки модели:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Полный smoke-test работающего сервиса на всех sample-файлах:

```powershell
.\scripts\smoke_test.ps1
```

## Проверка требований задания

| Требование | Реализация |
|---|---|
| Индивидуальный вариант | №16, `car_wash` |
| 3–5 sample-аудио | 5 файлов в `samples/` |
| Русский Whisper | `language=ru` |
| Транскрипция | faster-whisper |
| Поиск ключевых слов | `config/keywords.yaml` |
| POST /transcribe | реализован |
| GET /health | реализован |
| Пустой файл | HTTP 400 |
| Неверный формат | HTTP 415 |
| Лимит длины | 60 секунд, HTTP 413 |
| Модель один раз | FastAPI lifespan |
| CPU | `device=cpu`, `compute_type=int8` |
| README | этот файл |
| Git-тег | `v1.0` |
| GitVerse | репозиторий `SII-LR03-NazdraTenko` |

## Деплой на Render (Free: 0,1 CPU, 512 МБ RAM)

В репозитории есть `Dockerfile` и `render.yaml`. Free-план очень ограничен, поэтому для него заданы:

| Параметр | Значение | Зачем |
|---|---|---|
| `WHISPER_MODEL` | `tiny` | `base` вместе с Python и ctranslate2 легко упирается в 512 МБ RAM |
| `WHISPER_CPU_THREADS` | `1` | у сервиса доля одного ядра |
| `WHISPER_BEAM_SIZE` | `1` | меньше нагрузка на CPU (жадное декодирование) |
| `MAX_UPLOAD_MB` | `25` (по умолчанию) | файл не должен целиком лежать в памяти |

Модель скачивается при сборке образа, поэтому после «засыпания» сервис не качает её заново. Модель загружается в фоне: порт открывается сразу, а до готовности `POST /transcribe` отвечает `503`, `GET /ready` показывает `model_loaded`, интерфейс пишет «Модель загружается…».

Шаги: запушить репозиторий → Render → **New → Blueprint** (или **Web Service**, Runtime = Docker, Instance Type = Free) → Health Check Path `/health`.

Ограничения free-плана, о которых лучше знать заранее:

- сервис засыпает через ~15 минут без запросов, пробуждение занимает около минуты;
- на 0,1 CPU распознавание даже короткого файла идёт десятки секунд, `latency_ms` будет большим;
- `tiny` ошибается чаще `base`, особенно на русском; для точной проверки ключевых слов запускайте локально с `base`.

Локально можно переопределять те же параметры: `$env:WHISPER_MODEL="tiny"; python -m uvicorn app.main:app`.

## GitVerse

После локальной проверки:

```bash
git init
git add .
git commit -m "feat: complete LR3 whisper audio service"
git branch -M main
git remote add origin <URL-репозитория-GitVerse>
git push -u origin main
git tag -a v1.0 -m "ЛР3: Whisper и поиск ключевых слов"
git push origin v1.0
```

В репозитории по требованиям задания необходимо добавить `MaxxxVS` как collaborator.

## Примечание по образцам

В `samples/` лежат пять собственных коротких записей голоса (по 2–5 секунд) с разными формулировками по сценарию `car_wash`. Исходные голосовые сообщения конвертированы в WAV (16 кГц, моно) командой `ffmpeg -i запись.ogg -ac 1 -ar 16000 samples/<имя>.wav`.

Краткий отчёт находится в `REPORT.md`.

## Веб-интерфейс

Проект содержит готовый веб-интерфейс по адресу `http://127.0.0.1:8000/`. Интерфейс работает на тех же FastAPI-эндпоинтах и не требует отдельной установки Node.js или фронтенд-сервера.

В интерфейсе можно:

- перетащить или выбрать аудиофайл;
- запустить распознавание одним нажатием;
- быстро проверить готовые sample-файлы;
- увидеть распознанный текст, время обработки и количество сегментов;
- увидеть найденные ключевые слова и полный JSON ответа API;
- перейти в Swagger через ссылку `Swagger API`.
