ТЗ для Codex

# 1. ОБЩЕЕ ОПИСАНИЕ И ЦЕЛИ

## 1.1. Цель

Система создаёт «саммари-каналы» в Telegram на основе постов из других каналов. Пользовательский **master-аккаунт** (MTProto/Telethon) подписан на источники, слушает новые посты, разбивает их на темы, делает саммари, отправляет администратору карточки на модерацию и собирает одобренные пункты в дайджест, публикуемый ботом в целевом канале по расписанию.

## 1.2. Основные пользовательские сценарии (MVP)

* **Админ после развёртывания** (через файлы конфигурации и бота):

  * Подключает **master** (номер → код → пароль 2FA) — интерактивно в боте.
  * Сканирует подписки master, выбирает **отслеживаемые** каналы.
  * Указывает целевой **канал публикации**; проходит тест-пост.
  * Редактирует **промпт** саммари (версионирование).
  * Выбирает **модели** по задачам (classify/summary/link) и задаёт **API-ключи**.
  * Запускает/останавливает пайплайн; делает тест-прогон.
  * Настраивает **расписание дайджеста** и часовой пояс.

* **Онлайн-работа**:

  * Master слушает посты отслеживаемых каналов.
  * Для каждого поста: детекция **one/many** тем, разбиение (≤3 темы).
  * Для каждой темы: саммари; если есть ссылки — извлечение контента и учёт в саммари.
  * Админу приходят карточки тем **Ок/Отмена**.
  * Одобренные темы копятся и **публикуются по cron** в целевой канал; отклонённые — отбрасываются.

## 1.3. Ключевые ограничения/политики

* **Формат Telegram**: `parse_mode=HTML`, лимит 4096 символов/сообщение, корректное чанкование.
* **Пустой выпуск**: если нет одобренных тем — публикация пропускается, админу уходит уведомление.
* **Лимит тем в выпуске**: ≤10; лишние переносятся в следующий выпуск.
* **Атрибуция**: ссылки на первоисточники, в конце пункта — `(@username источника)`, UTM: `utm_source=tg_digest&utm_medium=post&utm_campaign=<YYYYMMDD>`.
* **ToS/право**: публикуем саммари + ссылки, не перезаливаем чужие медиа/полный текст.

## 1.4. Acceptance Criteria (готовность MVP)

* `docker compose up -d` + минимальный `.env` — и всё работает.
* Подключение master (номер/код/пароль) — сессия сохраняется и переживает рестарт.
* Управление источниками из подписок master (список/поиск/вкл/выкл).
* Проверка прав целевого канала тест-постом; понятное сообщение при недостатке прав.
* Редактор промптов (версии) + выбор моделей/ключей по задачам; ключи шифруются.
* Пайплайн: new post → split → links → summarize → модерация → digest (cron) → публикация.
* Логи/метрики, алерты (master оффлайн, провайдер LLM падает, публикация фейл, пустой выпуск).
* Ретраи, фолбэк-модель, circuit-breaker на LLM; дедуп (simhash).
* Поведение на правках/удалениях постов источников определено (см. 3.9).

---

# 2. СТЕК

## 2.1. Технологии

* **Python 3.11+**
* Бот: **aiogram v3**
* Master (MTProto): **Telethon**
* Планировщик: **APScheduler**
* Хранилище: **PostgreSQL 15** + **alembic** (миграции)
* Кэш/очереди/троттлинг: **Redis**
* Векторка (на будущее/RAG): **pgvector** (пакет и расширение, можно включить сразу)
* HTTP/парсинг ссылок: **httpx**, **readability-lxml**
* Дедуп: **simhash**
* Логирование: **structlog**
* Метрики: **prometheus_client**
* Тесты: **pytest**
* Форматирование/линт: **black, isort, flake8, mypy**
* Контейнеризация: **Docker + docker-compose**
* Безопасность: AES-GCM (ключ в `.env`)

## 2.2. Сервисы (контейнеры)

* `bot` — админ-панель/модерация/настройки (aiogram)
* `watcher` — master-сессия, ingest постов (Telethon)
* `worker` — пайплайн обработки/сборки/публикации
* `scheduler` — cron-триггеры дайджестов
* `db` — Postgres
* `redis` — Redis
* (опц.) `exporter` для метрик/логов

---

# 3. СТРУКТУРА И ТЕХНИЧЕСКИЕ ДЕТАЛИ

## 3.1. Структура репозитория

```
.
├─ app/
│  ├─ bot/                  # aiogram: FSM, меню, модерация, настройки
│  ├─ watcher/              # telethon: логин master, подписки, слушатель каналов
│  ├─ worker/               # pipeline: parse → split → expand → summarize → moderate → assemble → publish
│  ├─ common/               # конфиг, clients (LLM), crypto, utils, logging, errors
│  ├─ db/
│  │  ├─ migrations/        # alembic
│  │  └─ schema.sql         # исходная схема (синхронизирована с миграциями)
│  └─ tests/                # unit/integration/e2e + фикстуры
├─ config/
│  ├─ owner.env.sample      # заполняется владельцем и копируется в .env
│  ├─ owner_inputs.yaml     # человеко-читаемые параметры (расписание, TZ и т.п.)
│  ├─ models.yaml           # привязка задач → провайдеры/модели + fallback
│  ├─ prices.yaml           # прайсы LLM для расчёта cost_cents
│  └─ schedule.yaml         # cron и временная зона (дублируется в DB settings)
├─ prompts/
│  ├─ summary_v1.txt        # активный промпт по умолчанию
│  └─ _archive/             # прошлые версии (vN)
├─ docker/
│  ├─ bot.Dockerfile
│  ├─ watcher.Dockerfile
│  ├─ worker.Dockerfile
│  └─ docker-compose.yml
├─ ops/
│  ├─ Makefile
│  ├─ HEALTHCHECKS.md
│  └─ SECURITY.md
└─ docs/
   ├─ OWNER_ACTIONS.md      # что должен сделать владелец после старта
   └─ README.md             # быстрый старт и FAQ
```

## 3.2. Файлы конфигурации владельца (OWNER I/O)

### 3.2.1. `config/owner.env.sample` → копируется в `.env`

```
# Telegram Bot
BOT_TOKEN=123:ABC
ADMIN_IDS=123456789,987654321

# Timezone (для контейнеров)
TZ=Asia/Almaty

# DB/Cache
DB_URL=postgresql+psycopg://app:app@db:5432/app
REDIS_URL=redis://redis:6379/0

# Crypto (32 байта base64, для AES-GCM шифрования ключей/сессий)
SECRETS_MASTER_KEY_BASE64=

# Telethon (нужно получить на my.telegram.org)
TELEGRAM_API_ID=
TELEGRAM_API_HASH=

# LLM defaults (можно оставить пустым и задать в боте)
LLM_PROVIDER_DEFAULT=openai
LLM_API_KEY_DEFAULT=
```

### 3.2.2. `config/owner_inputs.yaml`

```yaml
digest:
  cron: "0 9,18 * * *"   # два выпуска в день
  tz: "Asia/Almaty"
pipeline:
  enabled: true
limits:
  max_topics_per_digest: 10
  replay_hours: 24
```

### 3.2.3. `config/models.yaml`

```yaml
tasks:
  classify:
    primary: { provider: "openai", model: "gpt-4o-mini" }
    fallback: { provider: "openai", model: "gpt-4o-mini" }
  summary:
    primary: { provider: "openai", model: "gpt-4o-mini" }
    fallback: { provider: "openai", model: "gpt-4o-mini" }
  link:
    primary: { provider: "openai", model: "gpt-4o-mini" }
    fallback: { provider: "openai", model: "gpt-4o-mini" }
timeouts:
  per_task_seconds: 20
retries:
  max_attempts: 3
  backoff_seconds: 2
circuit_breaker:
  error_threshold: 5
  cool_down_seconds: 120
```

### 3.2.4. `config/prices.yaml` (пример)

```yaml
openai:
  gpt-4o-mini:
    input_per_1k_tokens_cents: 15
    output_per_1k_tokens_cents: 60
```

### 3.2.5. `prompts/summary_v1.txt` (шаблон)

```
Ты — редактор новостного дайджеста. Задача: строгое саммари фактов.
Формат:
- 2–4 коротких буллета (без оценок).
- 1 ключевая цифра (если есть).
- 2–3 ссылки на источники (если есть; формат: короткая подпись + URL).
Правила:
- Используй ТОЛЬКО предоставленный текст поста и извлечённые статьи по ссылкам.
- Ничего не выдумывай. Не обобщай без фактов.
- Если источников < 2 для сильного утверждения — явно пометь "(низкая уверенность)".
Выводи только готовый текст саммари без предисловий.
```

### 3.2.6. `docs/OWNER_ACTIONS.md` (владелец делает один раз после старта)

* Получить на **my.telegram.org**: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` → записать в `.env`.
* Создать бота у **@BotFather** → `BOT_TOKEN` → в `.env`.
* (Опц.) Вставить `LLM_API_KEY_DEFAULT` → в `.env` или настроить позже в боте.
* Запустить: `docker compose up -d`.
* В Telegram: написать боту `/start` с админ-аккаунта (`ADMIN_IDS`).
* Пройти логин master: ввести **телефон → код → пароль 2FA**.
* Добавить бота в целевой канал и выдать право постинга → выполнить «Проверить доступ».
* Настроить расписание/модели/промпты через меню бота.

## 3.3. `docker/docker-compose.yml` (схема, без лишних подробностей)

```yaml
version: "3.9"
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
    volumes: [ "db_data:/var/lib/postgresql/data" ]
    healthcheck: { test: ["CMD-SHELL","pg_isready -U app -d app"], interval: 10s, timeout: 5s, retries: 5 }

  redis:
    image: redis:7
    volumes: [ "redis_data:/data" ]
    healthcheck: { test: ["CMD","redis-cli","ping"], interval: 10s, timeout: 5s, retries: 5 }

  bot:
    build: { context: .., dockerfile: docker/bot.Dockerfile }
    env_file: [ ../config/owner.env.sample, ../.env ]
    depends_on: [ db, redis ]
    healthcheck: { test: ["CMD","curl","-f","http://localhost:8080/health"], interval: 10s, timeout: 5s, retries: 5 }

  watcher:
    build: { context: .., dockerfile: docker/watcher.Dockerfile }
    env_file: [ ../config/owner.env.sample, ../.env ]
    depends_on: [ db, redis ]
    restart: unless-stopped

  worker:
    build: { context: .., dockerfile: docker/worker.Dockerfile }
    env_file: [ ../config/owner.env.sample, ../.env ]
    depends_on: [ db, redis ]
    restart: unless-stopped

  scheduler:
    build: { context: .., dockerfile: docker/worker.Dockerfile }
    command: ["python","-m","app.worker.scheduler"]
    env_file: [ ../config/owner.env.sample, ../.env ]
    depends_on: [ db, redis ]
    restart: unless-stopped

volumes:
  db_data: {}
  redis_data: {}
```

## 3.4. БД: схема (основные таблицы)

**settings** `(key text pk, value jsonb, updated_at timestamptz)`
— хранит `digest.cron`, `digest.tz`, `pipeline.enabled`, текущую версию промпта, активные модели и т.п.
**secrets** `(id serial pk, kind text, name text, enc_value bytea, created_at, updated_at)`
— шифруются AES-GCM (`SECRETS_MASTER_KEY_BASE64`), хранит LLM-ключи, Telethon-сессию.
**master_sessions** `(id serial pk, enc_session bytea, valid bool, created_at, updated_at)`
**sources** `(id bigserial pk, tg_id bigint, username text, title text, enabled bool, trust_level int, added_by bigint, added_at timestamptz)`
**raw_posts** `(id bigserial pk, source_id bigint fk, tg_message_id bigint, author text, text text, media jsonb, urls text[], published_at timestamptz, fetched_at timestamptz, simhash bigint, status text)`
**topics** `(id bigserial pk, raw_post_id bigint fk, ordinal int, text text, urls text[], status text, created_at, updated_at)`
**summaries** `(id bigserial pk, topic_id bigint fk, prompt_version int, model text, summary_text text, citations text[], tokens_in int, tokens_out int, cost_cents int, created_at)`
**digests** `(id bigserial pk, scheduled_at timestamptz, posted_at timestamptz, target_channel_id bigint, status text)`
**digest_items** `(digest_id bigint fk, summary_id bigint fk, position int)`

Индексы:

* `raw_posts(source_id, tg_message_id)` уникальный
* `topics(raw_post_id)`
* `summaries(topic_id)`
* `digests(scheduled_at)`

## 3.5. Приоритет конфигов

* `DB settings` > `config/*.yaml` > `.env` (кроме `SECRETS_MASTER_KEY_BASE64` — только из `.env`).
* Кнопка «Сбросить к дефолтам» — откат к `config/*.yaml` и `prompts/summary_v1.txt`.

## 3.6. FSM/меню бота (ядро)

* **/start** — главное меню.
* «Master-логин» → Phone → Code → (Password) → Save session (AES-GCM) → `valid=true`.
* «Источники» → «Сканировать подписки» → список/поиск → `[Отслеживать/Убрать]`, `enabled toggle`.
* «Канал публикации» → ввести `@username/id` → «Проверить доступ» (тест-пост → удалить).
* «Промпты» → показать активную версию → «Редактировать» → «Сохранить как vN» → «Сделать активной».
* «Модели/ключи» → per-task `classify/summary/link` → выбрать провайдера/модель → ввести/обновить ключ (в `secrets`) → «Тест запроса».
* «Пайплайн» → `Запустить/Остановить` → «Тест-прогон».
* «Расписание» → пресеты/cron + `tz` → предпросмотр ближайших 3 запусков.
* «Модерация» → лента карточек тем (превью 150–300 символов, источник, ссылки) → **Ок/Отмена**.

## 3.7. Watcher (Telethon)

* Логин master: интерактивно (номер → код → пароль), ошибки/лимиты — корректные сообщения.
* Сессия сериализуется и шифруется, хранится в `master_sessions`.
* Подписки: `iter_dialogs` фильтр каналов → синк в `sources`.
* Слушатель новых сообщений по `sources.enabled=true`.
* **Replay**: при старте добрать за последние `replay_hours` (по `owner_inputs.yaml`), хранить `last_tg_message_id` per-source; уникальник `(source_id, tg_message_id)`.

## 3.8. Worker: пайплайн

**parse**

* Нормализация текста, сбор ссылок (включая URL-кнопки), склейка альбомов, статус → `parsed`.
* Медиа-только без подписи — пропускаем (MVP).

**split_topics (one/many)**

* Эвристики: пустые строки, заголовки/эмодзи/нумерация.
* Если неуверенность — дёрнуть `classify`.
* Макс **3 темы**; при сомнении — считать **одной** (экономия токенов).

**expand_links**

* `httpx` параллельно (≤6 одновременных), таймаут 8с, 1 ретрай; token-bucket: ≤20 ссылок/мин.
* Readability → заголовок/лид/основной текст; урезать до лимита символов.

**summarize**

* Модель — из `models.yaml` (`summary`), с фолбэком.
* Таймауты/ретраи по `models.yaml`.
* Circuit-breaker: при N ошибках — пауза и алерт админу.
* Считать токены (оценочно) и `cost_cents` по `prices.yaml`.

**moderate**

* Админу карточка: превью, источник, ссылки → **Ок/Отмена**.
* На Ок: `topics.status=approved`; на Отмена: `declined`.

**assemble_digest / publish**

* Триггер от `scheduler` (cron + tz).
* Собрать `approved` за окно [prev_run, now).
* Если пусто — уведомление и завершение.
* Ограничение: ≤10 тем; лишние переносятся.
* Формирование текста (HTML, экранирование), чанкование ≤4096.
* Публикация: пауза/троттлинг, idempotency-ключ `digest_id:part_n`, запись `posted_at`.

## 3.9. Поведение на краях Telegram

* **Правка поста** до модерации → обновить `raw_post`, перегенерить темы.
* **Удаление поста** до модерации → пометить связанные темы `declined`.
* **Уже одобренный** и попавший в выпуск пост: изменения игнорируются (только лог).
* **Forward/репост**: указывать оригинальный канал как источник, если доступно.
* **Медиа-альбомы**: подписи склеивать в один текст.
* **URL-кнопки**: извлекать ссылки из `reply_markup`.

## 3.10. Дедупликация

* Дубликат, если тот же `(source_id, tg_message_id)` или `simhash` с Hamming ≤3 по тексту за последние 12 часов этого источника → `status=duplicate`, не обрабатывать.

## 3.11. Ограничения/рейты

* Telegram публикация: ≤20 msg/min; при flood-wait — вычислить `retry_at`, ждать и повторить.
* HTTP fetch: ≤6 concurrent, таймаут 8с, глобально ≤20 URL/мин.
* LLM: лимиты/таймауты из `models.yaml`; лог микро-статистики.

## 3.12. Безопасность

* Шифрование секретов/сессий: **AES-GCM**, ключ `SECRETS_MASTER_KEY_BASE64` (32 байта base64).
* Ротация ключа: двойное шифрование K1→K2 по команде из бота (в MVP можно просто указать процедуру в SECURITY.md).
* Маскирование токенов/телефонов в логах; запрет логировать `enc_value`.
* Админ-команды доступны только `ADMIN_IDS`.

## 3.13. Логи и метрики

* JSON-логи (structlog), уровни INFO/ERROR, `request_id`.
* Prometheus-метрики:

  * `ingest_posts_total`, `topics_created_total`, `summaries_total`
  * `moderation_pending`, `digest_items_pending`
  * `publish_failures_total`, `llm_errors_total`
  * гистограммы: `summary_latency_seconds`, `link_fetch_seconds`
* Эндпойнты `/health`, `/metrics` в bot/worker/scheduler.

## 3.14. Алерты (в Telegram админу)

* Нет валидной master-сессии / требуется повторный логин.
* Circuit-breaker LLM (превышен порог ошибок).
* Публикация дайджеста провалена.
* Пустой выпуск (нет approved тем к запуску).

## 3.15. Тест-план

**Unit**: парсер ссылок; split heuristics; чанкование 4096; экранирование HTML; расчёт cost.
**Integration**: LLM-стаб `LLM_PROVIDER=stub`; Telethon-фикстуры (моки апдейтов).
**E2E** (`make e2e`):

1. Миграции, сид начальных настроек из `config/*.yaml`.
2. Имитация входящих постов (фикстуры) → pipeline до модерации.
3. Авто-Ок нескольких тем → cron публикация в «лог-sink» канал (заглушка).
4. Проверки: записи в `digests`, чанкование, лимиты.
5. Инъекция ошибок LLM/HTTP → ретраи, фолбэк, алерты.

## 3.16. Docker/безопасность

* Контейнеры под non-root; pinned базовые образы.
* Healthchecks для всех сервисов.
* Volumes: `db_data`, `redis_data`.
* Pre-commit: `black`, `isort`, `flake8`, `mypy`.

## 3.17. Makefile (минимум)

```
make up          # docker compose up -d
make down        # docker compose down
make logs        # tail по всем сервисам
make migrate     # alembic upgrade head
make seed        # начальные settings из config/*.yaml
make test        # pytest
make e2e         # интеграционный сценарий
```

## 3.18. Производительность

* Цель: обработка 1 поста (1–2 темы) < 5 сек при доступной модели.
* Параллельность worker: по настройке (по умолчанию 8 задач).
* Ограничение токенов саммари: по модели/цене (configurable).

---

### ПРИМЕЧАНИЕ

* Взаимодействия, требующие человека (получение `API_ID/API_HASH`, `BOT_TOKEN`, ввод SMS-кода и 2FA-пароля master, добавление бота в целевой канал) описаны в `docs/OWNER_ACTIONS.md`. Все остальные параметры и поведение задаются через **файлы конфигурации** (`config/*.yaml`, `.env`) и/или через **меню бота`, причём приоритет — **DB settings**.
