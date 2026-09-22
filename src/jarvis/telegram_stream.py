from __future__ import annotations

import asyncio
import logging
import re
from html import escape
from time import monotonic

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest

log = logging.getLogger(__name__)

_LIMIT = 3500
_MIN_EDIT_INTERVAL = 1.05
_GLUED_SENTENCE = re.compile(r"([.!?…])([A-ZА-ЯЁ])")


def _tool_label(tool_call: object) -> str:
    if not isinstance(tool_call, dict):
        return "tool"
    name = tool_call.get("name") or tool_call.get("toolName") or tool_call.get("tool")
    if isinstance(name, str) and name.strip():
        return name.strip()[:80]
    return "tool"


def _fit(text: str) -> str:
    if len(text) <= _LIMIT:
        return text
    return "…\n" + text[-(_LIMIT - 2) :]


def _should_break(previous: str, chunk: str) -> bool:
    if not previous or not chunk:
        return False
    if previous.endswith(("\n", " ", "\t")):
        return False
    if chunk[:1] in " \n\t.,;:!?…)]}":
        return False
    return bool(re.search(r"[.!?…]\s*$", previous) and re.match(r"[A-ZА-ЯЁ]", chunk))


def append_stream_text(previous: str, chunk: str, *, force_break: bool = False) -> str:
    """Join streamed phrases so each new sentence starts on its own line."""
    chunk = _GLUED_SENTENCE.sub(r"\1\n\2", chunk)
    if not chunk:
        return previous
    if previous and (force_break or _should_break(previous, chunk)):
        if not previous.endswith("\n"):
            previous += "\n"
    return _GLUED_SENTENCE.sub(r"\1\n\2", previous + chunk)


class LiveTelegramMessage:
    """One editable Telegram message per agent run. Deltas must stay cheap."""

    def __init__(self, bot: Bot, chat_id: int, project_name: str) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._project_name = project_name
        self._message_id: int | None = None
        self._text = ""
        self._tools: list[str] = []
        self._thinking = False
        self._pending_break = False
        self._status = "работает"
        self._dirty = True
        self._last_edit = 0.0
        self._closed = False
        self._flush_lock = asyncio.Lock()
        self._pump_task = asyncio.create_task(self._pump())

    def apply_delta(self, update: object) -> None:
        kind = getattr(update, "type", "")
        if kind == "text-delta":
            chunk = str(getattr(update, "text", ""))
            self._text = append_stream_text(
                self._text, chunk, force_break=self._pending_break
            )
            self._pending_break = False
            self._dirty = True
        elif kind == "thinking-delta":
            if not self._thinking:
                self._thinking = True
                self._pending_break = True
                self._dirty = True
        elif kind == "thinking-completed":
            self._thinking = False
            self._pending_break = True
            self._dirty = True
        elif kind == "tool-call-started":
            label = _tool_label(getattr(update, "tool_call", None))
            self._tools.append(f"→ {label}")
            self._pending_break = True
            self._dirty = True
        elif kind == "tool-call-completed":
            label = _tool_label(getattr(update, "tool_call", None))
            self._tools.append(f"✓ {label}")
            self._pending_break = True
            self._dirty = True

    def set_status(self, status: str) -> None:
        self._status = status
        self._dirty = True

    def replace_text_if_empty(self, text: str) -> None:
        if not self._text.strip() and text.strip():
            self._text = _GLUED_SENTENCE.sub(r"\1\n\2", text)
            self._dirty = True

    def render(self) -> str:
        status = self._status
        if self._thinking and status == "работает":
            status = "думает"
        lines = [f"<b>{escape(self._project_name)}</b> — {escape(status)}"]
        if self._tools:
            lines.append("")
            lines.extend(escape(item) for item in self._tools[-8:])
        if self._text.strip():
            lines.append("")
            lines.append(escape(self._text))
        return _fit("\n".join(lines))

    async def close(self, status: str) -> None:
        self.set_status(status)
        if self._closed:
            await self.flush(force=True)
            return
        self._closed = True
        self._pump_task.cancel()
        try:
            await self._pump_task
        except asyncio.CancelledError:
            pass
        await self.flush(force=True)

    async def _pump(self) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(_MIN_EDIT_INTERVAL)
                await self.flush(force=False)
        except asyncio.CancelledError:
            return

    async def flush(self, *, force: bool) -> None:
        async with self._flush_lock:
            if not self._dirty and not force:
                return
            now = monotonic()
            if not force and now - self._last_edit < _MIN_EDIT_INTERVAL:
                return
            html = self.render()
            try:
                if self._message_id is None:
                    sent = await self._bot.send_message(
                        self._chat_id,
                        html,
                        parse_mode=ParseMode.HTML,
                    )
                    self._message_id = sent.message_id
                else:
                    await self._bot.edit_message_text(
                        html,
                        chat_id=self._chat_id,
                        message_id=self._message_id,
                        parse_mode=ParseMode.HTML,
                    )
                self._last_edit = monotonic()
                self._dirty = False
            except TelegramBadRequest as exc:
                log.warning("telegram stream edit failed: %s", exc)
                if "message is not modified" in str(exc).lower():
                    self._dirty = False
                    return
                sent = await self._bot.send_message(
                    self._chat_id,
                    html,
                    parse_mode=ParseMode.HTML,
                )
                self._message_id = sent.message_id
                self._last_edit = monotonic()
                self._dirty = False
