from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from jarvis.config import Settings

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class AclMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def __call__(
        self,
        handler: Handler,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, (Message, CallbackQuery)):
            user = event.from_user
        if user is None:
            return None

        data["settings"] = self._settings
        if self._settings.bootstrap_acl:
            if isinstance(event, Message) and event.text:
                command = event.text.split()[0].split("@", 1)[0]
                if command in {"/start", "/help"} or event.text == "Справка":
                    return await handler(event, data)
            return None

        if user.id not in self._settings.allowed_user_ids:
            return None
        return await handler(event, data)
