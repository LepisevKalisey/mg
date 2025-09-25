# TASKS: Этапы 1–3 по декомпозиции на микросервисы (без шины событий и без отдельного хранилища)

Предпосылки
- Коммуникация между сервисами — только HTTP.
- Хранение данных остаётся файловым/внутрипроцессным как сейчас (без отдельного Storage-сервиса).
- Цель — сузить ответственность сервисов и упростить поддержку, не ломая текущий пользовательский поток.

Порты (предложение)
- aggregator: 8002 (как сейчас)
- classifier: 8003
- scheduler: 8004
- summarizer: 8005
- publisher: 8006

Стандарты для новых сервисов
- Каждый сервис: FastAPI, эндпоинты /health и /ready, логирование, переменные окружения для конфигурации, requirements обновлены.
- Контракты — простые JSON; все даты ISO8601; все идентификаторы строковые.

Этап 1: Выделение Classification-сервиса
1) Создать сервис app/classifier (FastAPI)
   - Эндпоинт POST /api/classifier/classify
     Вход: { id?, title?, text?, url?, source?, created_at? }
     Выход: { is_news: bool, topics: [string], confidence: number, suggested_action: "approve"|"reject"|"review" }
   - Эндпоинты /health, /ready.
2) Перенести имеющуюся логику определения новостности/категории из assistant/aggregator (если есть эвристики/LLM — вынести сюда).
3) Добавить CLIENT в assistant для вызова classifier
   - Новый конфиг ASSISTANT_CLASSIFIER_URL.
   - В местах, где нужна автоподсказка approve/reject — вызывать classifier.
   - Флаг для включения/отключения автоклассификации.
4) Обновить assistant.yml (или docker-компоуз) для нового сервиса (порт, переменные окружения).
5) Тесты и проверка
   - Юнит: мок LLM, проверка формата ответа.
   - Интеграция: assistant -> classifier -> ответы.
   - Критерии приёмки: assistant показывает корректные рекомендации без регресса публикации.

Этап 2: Выделение Scheduler-сервиса (debounce/батчинг)
1) Создать сервис app/scheduler (FastAPI)
   - Эндпоинт POST /api/scheduler/publish_soon
     Вход: { channel_id, items: [ {id, title?, text?, url?, source?, created_at?} ], wait_sec? }
     Действие: записать в очередь и (пере)запланировать дебаунс-окно.
     Выход: { scheduled_for: ISO8601, batch_key }
   - Эндпоинт POST /api/scheduler/flush
     Вход: { channel_id }
     Действие: немедленно завершить окно и опубликовать батч.
   - Эндпоинт GET /health (отдаёт next_fire_time).
   - Хранение очереди — в памяти (без отдельного хранилища).
2) Перенести текущую debounce-логику из app/aggregator/main.py в scheduler.
3) Изменить aggregator /api/aggregator/publish_soon
   - Сделать обёрткой: проксировать вызовы в scheduler.
   - Удалить/отключить локальный таймер из aggregator.
4) Конфиги
   - Новые: SCHEDULER_URL в assistant и aggregator.
   - Параметр DEBOUNCE_SECONDS читается в scheduler.
5) Интеграция публикации (временно)
   - По срабатыванию окна scheduler должен вызвать summarizer, затем publisher (см. Этап 3). До завершения Этапа 3 — можно временно вызывать старый aggregator.publish_now.
6) Тесты и проверка
   - Юнит: переотложение таймера при новых элементах, корректная агрегация.
   - Интеграция: assistant -> aggregator.publish_soon -> scheduler.
   - Критерии приёмки: батчи собираются, окно работает, ручной flush публикует.

Этап 3: Разделение Aggregator на Summarizer и Publisher
A) Summarizer-сервис (LLM-композиция)
1) Создать сервис app/summarizer (FastAPI)
   - Эндпоинт POST /api/summarizer/compose
     Вход: { channel_id, items: [ {id, title?, text?, url?, source?} ], language?, style_opts? }
     Выход: { message_markdown, blocks_meta: [ {topic, item_ids: [id]} ] }
   - Перенести в него: _compose_prompt, постобработку эмодзи/ссылок/атрибуции из aggregator.
   - Конфиги: GEMINI_API_KEY, MODEL_NAME, SUMMARY_LANGUAGE.
2) Тесты: стабильность промпта, разбиение на блоки, максимальные длины.

B) Publisher-сервис (Telegram отправка)
1) Создать сервис app/publisher (FastAPI)
   - Эндпоинт POST /api/publisher/telegram
     Вход: { channel_id, message_markdown }
     Выход: { ok: bool, message_url? }
   - Перенести в него: _publish_telegram из aggregator.
   - Конфиги: TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID.
2) Тесты: мок Telegram (или dry-run), обработка ошибок, лимиты.

C) Интеграция сервисов
1) Обновить scheduler: при срабатывании окна
   - Вызвать summarizer.compose для батча.
   - Результат передать в publisher.telegram.
   - Логировать ссылку на опубликованное сообщение.
2) Обновить aggregator
   - /publish_now: собрать единичный item -> summarizer.compose -> publisher.telegram.
   - /publish_soon: проксировать в scheduler (как в Этапе 2).
3) Обновить конфиги (ASSISTANT_/AGGREGATOR_/SCHEDULER_/SUMMARIZER_/PUBLISHER_URL), *.yml файлы сервисов.
4) Тесты и проверка контура
   - Интеграция: assistant -> scheduler -> summarizer -> publisher -> Telegram.
   - Критерии приёмки: посты публикуются, формат Markdown соответствует требованиям, источники и сегментация сохранены.

Нефункциональные задачи (сквозные)
- Логирование и трассировка запросов (request-id, batch-key).
- Единый формат ошибок: {error_code, message, details?}.
- Ретраи при сетевых ошибках между сервисами.
- Документация эндпоинтов (OpenAPI генерируется из FastAPI).

Проверка готовности
- Все новые сервисы имеют /health, конфиги, набор тестов.
- Существующий поток публикации работает через новые сервисы без регресса.
- Возможность отключить каждый новый сервис и вернуться к старому пути (флаги в конфиге).