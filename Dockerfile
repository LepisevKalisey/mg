# Python 3.11 slim
FROM python:3.11-slim

WORKDIR /app

# Установим зависимости сборки для telethon (минимально)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY app ./app

# Создадим структуру данных
RUN mkdir -p /app/data/pending /app/data/approved /app/data/sessions

ENV PYTHONUNBUFFERED=1
ENV SERVICE=assistant

EXPOSE 8001 8003

# Запускаем API (авто-выбор по SERVICE)
CMD ["sh", "-c", "if [ \"$SERVICE\" = \"collector\" ]; then uvicorn app.collector.main:app --host 0.0.0.0 --port 8001; else uvicorn app.assistant.main:app --host 0.0.0.0 --port 8003; fi"]