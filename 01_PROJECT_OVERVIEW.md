# Обзор проекта MediaGenerator

## Описание

MediaGenerator - это система для автоматизированного сбора сообщений из Telegram каналов, их модерации через Telegram группу редакторов и создания саммари для публикации в целевой канал. Система состоит из трех микросервисов, работающих совместно для обеспечения полного цикла обработки контента.

## Цель проекта

Автоматизация процесса:
1. Мониторинга множественных Telegram каналов
2. Сбора сообщений и отправки их на модерацию в Telegram группу
3. Обработки решений редакторов (одобрение/отклонение)
4. Создания саммари из одобренных сообщений
5. Публикации саммари в целевой канал

## Основные принципы

- **Микросервисная архитектура** - каждый сервис выполняет свою задачу
- **Файловая система** - простое и надежное хранение данных
- **Telegram-based модерация** - модерация через Telegram группу с inline кнопками
- **Асинхронная обработка** - высокая производительность
- **Модульность** - легкое расширение функционала

## Архитектура системы

### Микросервисная архитектура
Система построена на принципах микросервисов с четким разделением ответственности:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   COLLECTOR     │───▶│   ASSISTANT     │───▶│    Agregator    │
│   (Сбор)        │    │   (Редактура)   │    │   (Публикация)  │
│   Port: 8001    │    │   Port: 8003    │    │   Port: 8002    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ФАЙЛОВАЯ СИСТЕМА                             │
│             /data/pending/  │  /data/approved/                  │
└─────────────────────────────────────────────────────────────────┘
```

### Сервисы

1. **Collector Service** (Порт 8001)
   - Мониторинг Telegram каналов
   - Сбор новых сообщений
   - Сохранение в папку pending
   - Отправка сообщений с кнопками Ok/Cancel в Telegram группу редакторов

2. **Assistant Service** (Порт 8003)
   - Получение callback от редакторов из Telegram группы
   - Перемещение файлов сообщений в approved или удаление при отказе
   - Обработка решений модерации

3. **Aggregator Service** (Порт 8002)
   - Создание саммари из одобренных сообщений
   - Публикация саммари в целевой канал
   - Удаление файлов после создания саммари

## Технологический стек

### Backend
- **Python 3.11** - основной язык программирования
- **FastAPI** - веб-фреймворк для REST API
- **Uvicorn** - ASGI сервер
- **Pydantic** - валидация данных
- **Telethon** - работа с Telegram API
- **aiogram** - Telegram Bot API

### Инфраструктура
- **Docker** - контейнеризация
- **Docker Compose** - оркестрация сервисов
- **Файловая система** - хранение данных (JSON файлы)

### Мониторинг и логирование
- **Встроенное логирование** Python
- **Health checks** для каждого сервиса
- **Метрики** производительности

## Структура данных

### Формат сообщения
```json
{
  "id": "unique_message_id",
  "channel_id": "telegram_channel_id",
  "channel_name": "channel_username",
  "message_id": 12345,
  "text": "Текст сообщения",
  "media": {
    "type": "photo|video|document",
    "file_id": "telegram_file_id",
    "caption": "Подпись к медиа"
  },
  "author": {
    "id": "author_id",
    "username": "author_username",
    "first_name": "Имя",
    "last_name": "Фамилия"
  },
  "timestamp": "2024-01-01T12:00:00Z",
  "metadata": {
    "views": 1000,
    "forwards": 50,
    "reactions": {...}
  },
  "status": "pending|approved|rejected",
  "moderation": {
    "moderator_id": "moderator_id",
    "timestamp": "2024-01-01T12:30:00Z",
    "reason": "Причина решения"
  }
}
```

## Файловая структура хранения

```
/data/
├── pending/          # Новые сообщения для модерации
│   ├── message_1.json
│   ├── message_2.json
│   └── ...
├── approved/         # Одобренные сообщения
│   ├── message_3.json
│   └── ...
└── sessions/        # Telegram сессии
    ├── mtproto.session
    └── temp_auth.session
```

## Поток данных

```
Telegram Каналы → Collector → pending/ → Telegram Группа Модерации → Человек-редактор принимает решение → Assistant → approved/ → Aggregator → Саммари → Целевой Канал
```

### Детальный процесс

1. **Сбор** (Collector Service)
   - Подключение к Telegram API через Telethon
   - Мониторинг указанных каналов
   - Получение новых сообщений
   - Сохранение в JSON формате в папку `pending/`
   - Отправка сообщения в Telegram группу редакторов с кнопками Ok/Cancel

2. **Модерация** (Assistant Service)
   - Получение callback от inline кнопок в Telegram группе
   - При нажатии "Ok": перемещение файла из `pending/` в `approved/`
   - При нажатии "Cancel": удаление файла из `pending/`

3. **Создание саммари** (Aggregator Service)
   - В установленное время или по принудительному вызову в управляющем боте, проверка папки `approved/` 
   - Сбор одобренных сообщений
   - Создание саммари по каждому сообщению из накопленного контента
   - Публикация дайджеста саммари в целевой канал
   - Удаление обработанных файлов

## Основные функции

### 1. Мониторинг каналов
- Подключение к Telegram API через Telethon
- Отслеживание новых сообщений в реальном времени
- Фильтрация по типу контента
- Автоматическое сохранение метаданных

### 2. Модерация контента
- Ручная модерация через Telegram группу с inline кнопками
- Система статусов через перемещение файлов сообщений(pending/approved)

### 3. Публикация контента
- Автоматическое создание саммари из одобренного контента
- Публикация в целевой канал

## Конфигурация

### Переменные окружения
```env
# Telegram API
API_ID=your_api_id
API_HASH=your_api_hash
PHONE_NUMBER=your_phone_number
BOT_TOKEN=your_bot_token

# Сервисы
COLLECTOR_HOST=0.0.0.0
COLLECTOR_PORT=8001
AGGREGATOR_HOST=0.0.0.0
AGGREGATOR_PORT=8002
ASSISTANT_HOST=0.0.0.0
ASSISTANT_PORT=8003

# Мониторинг
MONITORING_CHANNELS=@channel1,@channel2
BATCH_SIZE=10
```

## Развертывание

### Требования
- Docker 20.10+
- Docker Compose 2.0+
- Для локального запуска без Docker: Python 3.11, pip

### Переменные окружения (ключевые)
- Assistant (обязательно): BOT_TOKEN
- Collector (обязательно): API_ID, API_HASH
- Рекомендуемые/опциональные:
  - EDITORS_CHANNEL_ID — ID чата редакторов, куда Collector отправляет карточки/уведомления
  - SERVICE_URL_ASSISTANT — публичный URL ассистента для автонастройки вебхука (например, https://host/assistant)
  - TELEGRAM_WEBHOOK_SECRET — секрет вебхука (для заголовка X-Telegram-Bot-Api-Secret-Token)
  - DATA_DIR — путь каталога данных внутри контейнера (обычно /app/data)
  - SESSIONS_DIR — отдельный путь для сессий (по умолчанию /app/data/sessions)
  - MONITORING_CHANNELS или CHANNELS_FILE — список каналов для сбора
  - ADMIN_CHAT_ID — ID админ-чата для ограничений команд и уведомлений

Примечания:
- Docker Compose автоматически подхватывает файл .env в корне проекта. Для локальной разработки можно использовать .env.dev и/или скопировать его в .env.
- Ассистент при локальном запуске (без Docker) подхватывает .env из корня через python-dotenv.

### Локальный запуск (Docker)
1) Создайте внешнюю сеть Docker (используется обоими сервисами):
   - docker network create mg_net

2) Подготовьте .env или .env.dev с переменными (минимум):
   - BOT_TOKEN=<токен_бота>
   - API_ID=<api_id>
   - API_HASH=<api_hash>
   - EDITORS_CHANNEL_ID=<id_чата_редакторов> (рекомендуется)
   - SERVICE_URL_ASSISTANT=<публичный_url> (опционально, для вебхука)
   - TELEGRAM_WEBHOOK_SECRET=<секрет> (опционально)
   - HOST_DATA_DIR=<путь_на_хосте_для_тома_данных>
     - Windows пример: HOST_DATA_DIR=c:/Projects/mg/data
     - Linux пример: HOST_DATA_DIR=/srv/mg

3) Запустите сервисы по одному:
   - Assistant: docker compose -f assistant.yml up -d --build assistant
   - Collector: docker compose -f collector.yml up -d --build collector

4) Проверки работоспособности:
   - Assistant: docker compose -f assistant.yml exec assistant sh -lc "curl -fsS http://127.0.0.1:8003/health"
   - Collector: docker compose -f collector.yml exec collector sh -lc "curl -fsS http://127.0.0.1:8001/health"

5) Вебхук ассистента:
   - Если задан SERVICE_URL_ASSISTANT — ассистент на старте автоматически выставит вебхук на <SERVICE_URL_ASSISTANT>/telegram/webhook.
   - Диагностика: GET http://127.0.0.1:8003/debug/webhook-info и GET http://127.0.0.1:8003/telegram/webhook
   - Если публичного URL нет — оставьте SERVICE_URL_ASSISTANT пустым, автоконфигурация будет пропущена. Для разработки используйте Tailscale/Cloudflare Tunnel/ngrok.

### Локальный запуск (без Docker)
1) Установите зависимости:
   - python -m venv .venv
   - (Windows) .venv\Scripts\Activate.ps1
   - (Linux/macOS) source .venv/bin/activate
   - pip install -r requirements.txt

2) Создайте .env в корне проекта (минимум):
   - Assistant: BOT_TOKEN=..., SERVICE_URL_ASSISTANT=... (опционально), TELEGRAM_WEBHOOK_SECRET=... (опционально)
   - Collector: API_ID=..., API_HASH=..., PHONE_NUMBER=... (для первичной авторизации), EDITORS_CHANNEL_ID=... (опционально)
   - Если DATA_DIR не задан — сервисы используют ./data; убедитесь, что каталоги ./data/pending, ./data/approved, ./data/sessions существуют (они создаются автоматически при старте).

3) Запуск сервисов:
   - Assistant: uvicorn app.assistant.main:app --host 0.0.0.0 --port 8003
   - Collector: uvicorn app.collector.main:app --host 0.0.0.0 --port 8001

4) Проверки:
   - curl http://127.0.0.1:8003/health
   - curl http://127.0.0.1:8001/health

### Первичная авторизация Collector (Telethon)
- Убедитесь, что заданы API_ID и API_HASH; при первом входе предоставьте PHONE_NUMBER (или укажите номер в запросе).
- Запустите процесс авторизации через API коллектора (в контейнере):
  - docker compose -f collector.yml exec collector sh -lc "curl -fsS -X POST -H 'Content-Type: application/json' -d '{\"phone\":\"+<номер>\", \"chat_id\": <ADMIN_CHAT_ID>}' http://127.0.0.1:8001/api/collector/auth/start"
- Введите код подтверждения:
  - docker compose -f collector.yml exec collector sh -lc "curl -fsS -X POST -H 'Content-Type: application/json' -d '{\"code\":\"12345\"}' http://127.0.0.1:8001/api/collector/auth/code"
- Если включена 2FA, отправьте пароль:
  - docker compose -f collector.yml exec collector sh -lc "curl -fsS -X POST -H 'Content-Type: application/json' -d '{\"password\":\"<пароль>\"}' http://127.0.0.1:8001/api/collector/auth/password"
- Проверка статуса авторизации:
  - docker compose -f collector.yml exec collector sh -lc "curl -fsS http://127.0.0.1:8001/api/collector/auth/status"

Примечание: для уведомлений и сообщений от Collector в редакторский чат задайте BOT_TOKEN и EDITORS_CHANNEL_ID.

### Запуск на сервере (prod)
1) Подготовьте прод-окружение (.env):
   - BOT_TOKEN, API_ID, API_HASH (обязательно)
   - EDITORS_CHANNEL_ID (рекомендуется)
   - SERVICE_URL_ASSISTANT (публичный https), TELEGRAM_WEBHOOK_SECRET (для безопасности)
   - HOST_DATA_DIR=/srv/mg (или свой путь) и DATA_DIR=/app/data
   - ADMIN_CHAT_ID (опционально)

2) Создайте сеть и каталоги данных:
   - docker network create mg_net
   - mkdir -p /srv/mg && chown -R <user>:<group> /srv/mg

3) Запустите сервисы и проверьте:
   - docker compose -f assistant.yml up -d --build assistant
   - docker compose -f collector.yml up -d --build collector
   - curl http://localhost:8003/health
   - curl http://localhost:8001/health

4) Обновление без простоя:
   - docker compose -f assistant.yml up -d --build assistant
   - docker compose -f collector.yml up -d --build collector

5) Вебхук в проде:
   - Убедитесь, что ваш обратный прокси/маршрутизация (например, Tailscale/NGINX) публикует порт 8003 по адресу SERVICE_URL_ASSISTANT.
   - Ассистент на старте автоматически настроит вебхук; проверить можно через /debug/webhook-info.

## Безопасность

### Аутентификация
- Telegram API ключи
- Сессии пользователей
- Токены ботов

### Хранение данных
- Локальная файловая система
- Шифрование сессий Telegram
- Ротация логов

### Сетевая безопасность
- Внутренняя сеть Docker
- Ограничение портов
- HTTPS для продакшена

## Мониторинг и отладка

### Health Checks
Каждый сервис предоставляет endpoint `/health` для проверки состояния.

### Логирование
- Структурированные логи в JSON формате
- Различные уровни логирования (DEBUG, INFO, WARNING, ERROR)
- Ротация логов по размеру и времени

## Расширение системы

### Добавление новых сервисов
1. Создать новый микросервис
2. Добавить в docker-compose.yml
3. Настроить взаимодействие через API
4. Обновить документацию

## Поддержка и обслуживание

### Резервное копирование
- Автоматическое резервное копирование данных
- Экспорт конфигураций
- Восстановление из бэкапов

### Обновления
- Версионирование API
- Миграции данных
- Откат изменений

## Операционная документация: запуск, проверки и отладка (из контейнера)

Ниже приведены практические инструкции, как проверить работоспособность сервисов непосредственно из контейнера (Docker/Coolify), как провести первичную авторизацию Telethon, и как диагностировать типичные проблемы.

### Общие принципы
- Оба сервиса используют общий путь данных внутри контейнера: `/app/data` (можно переопределить переменной `DATA_DIR`).
- Структура каталога данных:
  - `/app/data/pending` — новые сообщения
  - `/app/data/approved` — одобренные
  - `/app/data/sessions` — сессия Telethon (файл `mtproto.session`)
- На PaaS (например, Coolify) прикрепите один и тот же Persistent Storage к обоим приложениям по пути `/app/data`.

### Переменные окружения (минимально необходимые)
- Общие: `DATA_DIR=/app/data`
- Collector: `API_ID`, `API_HASH`, (на первичную авторизацию — `PHONE_NUMBER` или `PHONE`), `MONITORING_CHANNELS` (либо файл `/app/data/channels.txt`)
- Assistant: `BOT_TOKEN` (обязательно), для Collector — `EDITORS_CHANNEL_ID` (целевой чат редакторов)

---

### Проверка каталога данных из контейнера
- Убедитесь, что контейнер видит и может писать в `/app/data`:
  - Проверка наличия: `ls -la /app/data`
  - Создание подпапок (если пустой том): `mkdir -p /app/data/pending /app/data/approved /app/data/sessions`

---

### Проверка Collector (внутри контейнера)
1) Health-check (локально в контейнере):
   - `curl -s http://127.0.0.1:8001/health` — в ответе `data_dirs` должны указывать на `/app/data/...`, `status` — `ok` при авторизованной сессии.
2) Авторизация Telethon (разово):
   - Убедитесь, что заданы `API_ID`, `API_HASH`, `PHONE_NUMBER` и (рекомендуется) `DATA_DIR=/app/data`.
   - При необходимости форсируйте SMS: установите `FORCE_SMS=1`.
   - Запустите: `python -m app.collector.auth_login`.
   - При включённой 2FA будет дополнительный запрос пароля.
   - После успеха появится `/app/data/sessions/mtproto.session`.
3) Проверка мониторинга:
   - В health: поле `authorized` должно быть `true`.
   - При появлении новых сообщений в отслеживаемых каналах файлы должны записываться в `/app/data/pending`.

---

### Проверка Assistant (внутри контейнера)
1) Health-check:
   - `curl -s http://127.0.0.1:8003/health` — проверяем пути `pending`/`approved` и статус `ok`.
2) Тест webhook вручную:
   - Отправьте тестовый callback-запрос (замените `FILENAME.json` на существующий файл в `pending` и укажите корректный `chat_id`):
```
POST /telegram/webhook
Content-Type: application/json

{
  "callback_query": {
    "id": "1",
    "message": {"message_id": 123, "chat": {"id": 123456789}},
    "data": "approve:FILENAME.json"
  }
}
```
   - Ожидаем перемещение файла из `pending` в `approved`.

---

### Авторизация Telethon: рекомендации
- Предпочтительно выполнить авторизацию локально и загрузить готовый файл сессии в `/app/data/sessions/mtproto.session` на PaaS — так вы избежите интерактивных шагов в облаке.
- Если делаете авторизацию в контейнере:
  - Установите `FORCE_SMS=1`, если код в приложении не приходит.
  - Следите за сообщениями `FLOOD_WAIT` (превышен лимит попыток) — подождите указанное время.
  - При включённой 2FA будет запрос пароля — подготовьте его заранее.

---

### Типичные проблемы и решения (Troubleshooting)
1) Код подтверждения не приходит при авторизации внутри контейнера:
   - По умолчанию Telegram отправляет код в чат «Telegram» в вашем приложении (не SMS). Проверьте этот чат в клиенте Telegram (мобильном/десктопном).
   - Включите отправку SMS: установите `FORCE_SMS=1` и повторите `python -m app.collector.auth_login`.
   - Возможен лимит попыток (FLOOD_WAIT) — дождитесь указанного таймаута.
   - Убедитесь, что номер в международном формате и соответствует аккаунту.
   - Проверьте сетевую доступность Telegram из окружения PaaS (файрвол, egress-политики). При проблемах авторизуйтесь локально и перенесите файл сессии.
2) Ошибка sqlite3 «unable to open database file»:
   - Причина: отсутствует каталог `/app/data/sessions` в смонтированном томе.
   - Решение: создайте каталог и убедитесь в правах записи; повторите запуск. В коде сервисов каталоги создаются автоматически при старте, но если том пустой, убедитесь, что у пользователя контейнера есть права на запись.
3) Файлы не появляются/не перемещаются:
   - Проверьте переменную `DATA_DIR` и что оба сервиса используют один и тот же персистентный том в `/app/data`.
   - Проверьте логи сервисов и ответы `/health`.

---

### Чек-лист быстрой диагностики
- /app/data смонтирован и доступен для записи
- В collector `/health` показывает `authorized=true`
- В assistant `/health` показывает корректные пути
- Для авторизации использован `FORCE_SMS=1` (при необходимости)
- Файлы в `/app/data/pending` создаются (collector), и перемещаются в `/app/data/approved` (assistant)

## tg accounts
### Chorizzo1
API_ID=23905873
API_HASH=b7e4242c20df906337c07f2e59cebdbe
PHONE_NUMBER=+77073492959
### Rimus Striker
API_ID=23461862
API_HASH=376b4723b246f9a3f3e65039de8cf998
PHONE_NUMBER=+77071793989
