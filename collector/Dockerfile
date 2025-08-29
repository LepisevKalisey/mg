FROM python:3.11-slim

WORKDIR /app

# Ускоряем сборку: ставим зависимости отдельно
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Копируем только код сервиса collector
COPY collector /app

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]