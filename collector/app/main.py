from fastapi import FastAPI

app = FastAPI(title="MG Collector", version="0.1.0")


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "collector"}


# TODO: внедрить Telethon (MTProto) для подписки на каналы и приёма постов
# TODO: добавить базовую саммаризацию (LLM) и сохранение в БД
# TODO: реализовать роли и доступ через Telegram-бот (Aiogram)