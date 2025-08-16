"""Entry point for the Telegram admin bot."""

from __future__ import annotations

import asyncio
import contextlib
from typing import NoReturn

from aiohttp import web
from aiogram import Bot, Dispatcher
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest

from .config import load_settings
from .handlers import setup_router
from .logging import setup_logging


async def health_handler(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def metrics_handler(_: web.Request) -> web.Response:
    registry = CollectorRegistry(auto_describe=True)
    output = generate_latest(registry)
    return web.Response(body=output, content_type=CONTENT_TYPE_LATEST)


async def run_http_server(host: str, port: int) -> None:
    app = web.Application()
    app.add_routes([web.get("/health", health_handler), web.get("/metrics", metrics_handler)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    await asyncio.Event().wait()  # run forever


async def main_async() -> NoReturn:
    setup_logging()
    settings = load_settings()
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(setup_router(settings.admin_ids))

    http_task = asyncio.create_task(run_http_server(settings.http_host, settings.http_port))
    try:
        await dp.start_polling(bot)
    finally:
        http_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await http_task


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()
