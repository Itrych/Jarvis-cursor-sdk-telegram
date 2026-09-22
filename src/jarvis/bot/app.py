from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from jarvis.bot.acl import AclMiddleware
from jarvis.bot import agent_handlers, file_handlers, handlers
from jarvis.config import Settings
from jarvis.files import DownloadIndex
from jarvis.runtime import AgentRuntime
from jarvis.store import Store

log = logging.getLogger(__name__)


async def run_bot(settings: Settings) -> None:
    store = Store(settings.db_path)
    await store.init()
    runtime = AgentRuntime(settings, store)
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp["settings"] = settings
    dp["store"] = store
    dp["runtime"] = runtime
    dp["downloads"] = DownloadIndex()
    dp.message.middleware(AclMiddleware(settings))
    dp.callback_query.middleware(AclMiddleware(settings))
    dp.include_router(handlers.router)
    dp.include_router(file_handlers.router)
    dp.include_router(agent_handlers.router)

    async def on_shutdown() -> None:
        await runtime.stop()

    dp.shutdown.register(on_shutdown)
    log.info("Jarvis polling started")
    await dp.start_polling(bot)
