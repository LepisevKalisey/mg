# Python 3.11 slim
FROM python:3.11-slim

WORKDIR /app

# Установим зависимости сборки для telethon (минимально) + curl для отладки health/checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY app ./app

# Создадим структуру данных
RUN mkdir -p /app/data/pending /app/data/approved /app/data/sessions

ENV PYTHONUNBUFFERED=1

EXPOSE 8001 8003

# Запуск командой из docker-compose; по умолчанию collector, но может быть переопределено
CMD ["uvicorn", "app.collector.main:app", "--host", "0.0.0.0", "--port", "8001"]