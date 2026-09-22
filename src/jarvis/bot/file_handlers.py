from __future__ import annotations

import logging
import tempfile
from html import escape
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from aiogram.dispatcher.event.bases import SkipHandler

from jarvis.bot.keyboards import BTN_FILES, MAIN_BUTTONS, main_keyboard
from jarvis.files import (
    DownloadIndex,
    ProjectPathError,
    ensure_sendable_file,
    format_tree,
    human_size,
    relative_posix,
    resolve_inside,
    zip_target,
)
from jarvis.store import Store

log = logging.getLogger(__name__)
router = Router(name="jarvis-files")


class FileForm(StatesGroup):
    waiting_path = State()


@router.message(Command("files"))
async def cmd_files(
    message: Message,
    store: Store,
    state: FSMContext,
    downloads: DownloadIndex,
    command: CommandObject,
) -> None:
    await _show_files(message, store, state, downloads, (command.args or "").strip())


@router.message(F.text == BTN_FILES)
async def btn_files(
    message: Message, store: Store, state: FSMContext, downloads: DownloadIndex
) -> None:
    await _show_files(message, store, state, downloads, "")


async def _show_files(
    message: Message,
    store: Store,
    state: FSMContext,
    downloads: DownloadIndex,
    rel: str,
) -> None:
    await state.clear()
    active = await store.get_active(message.chat.id)
    if active is None:
        await message.answer(
            "Сначала выбери проект: /new, /open или /projects.",
            reply_markup=main_keyboard(),
        )
        return
    root = Path(active.path)
    try:
        start = resolve_inside(root, rel) if rel else root
    except ProjectPathError as exc:
        await message.answer(str(exc), reply_markup=main_keyboard())
        return
    if not start.exists():
        await message.answer("Нет такого пути.", reply_markup=main_keyboard())
        return
    tree, top_level, truncated = format_tree(root, start)
    downloads.store(message.chat.id, top_level)
    header = f"Файлы <b>{escape(active.name)}</b>"
    if rel:
        header += f" / <code>{escape(rel)}</code>"
    await message.answer(header + ":", reply_markup=_download_keyboard(top_level))
    for chunk in _split(tree, 3500):
        await message.answer(f"<pre>{escape(chunk)}</pre>")
    footer = "Скачать: /get путь  ·  весь проект: /get ."
    if truncated:
        footer = "Список обрезан. Уточни папку: /files путь\n" + footer
    await message.answer(footer, reply_markup=main_keyboard())


@router.message(Command("get"))
async def cmd_get(
    message: Message,
    command: CommandObject,
    store: Store,
    state: FSMContext,
) -> None:
    arg = (command.args or "").strip()
    if not arg:
        await state.set_state(FileForm.waiting_path)
        await message.answer(
            "Путь внутри проекта (файл, папка) или <code>.</code> для всего проекта.",
            reply_markup=main_keyboard(),
        )
        return
    await state.clear()
    await _send_project_item(message, store, arg)


@router.message(FileForm.waiting_path, F.text)
async def on_get_path(message: Message, store: Store, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text in MAIN_BUTTONS:
        raise SkipHandler
    if text.startswith("/"):
        await state.clear()
        await message.answer("Скачивание отменено.", reply_markup=main_keyboard())
        return
    await state.clear()
    await _send_project_item(message, store, text)


@router.callback_query(F.data.startswith("dl:"))
async def cb_download(query: CallbackQuery, store: Store, downloads: DownloadIndex) -> None:
    raw = (query.data or "")[3:]
    try:
        index = int(raw)
    except ValueError:
        await query.answer("Некорректный файл", show_alert=True)
        return
    if query.message is None:
        await query.answer()
        return
    rel = downloads.get(query.message.chat.id, index)
    if rel is None:
        await query.answer("Список устарел, нажми Файлы ещё раз", show_alert=True)
        return
    await query.answer(rel[:64])
    await _send_project_item(query.message, store, rel)


@router.callback_query(F.data == "dlall")
async def cb_download_all(query: CallbackQuery, store: Store) -> None:
    if query.message is None:
        await query.answer()
        return
    await query.answer("архив")
    await _send_project_item(query.message, store, ".")


def _download_keyboard(rel_paths: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, rel in enumerate(rel_paths[:20]):
        prefix = "📁 " if rel.endswith("/") else ""
        rows.append(
            [InlineKeyboardButton(text=(prefix + rel)[:64], callback_data=f"dl:{index}")]
        )
    rows.append([InlineKeyboardButton(text="Весь проект (zip)", callback_data="dlall")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_project_item(message: Message, store: Store, rel: str) -> None:
    if message.bot is None:
        return
    active = await store.get_active(message.chat.id)
    if active is None:
        await message.answer("Сначала выбери проект.", reply_markup=main_keyboard())
        return
    root = Path(active.path)
    try:
        target = resolve_inside(root, rel)
        ensure_sendable_file(target)
    except ProjectPathError as exc:
        await message.answer(str(exc), reply_markup=main_keyboard())
        return
    try:
        if target.is_file():
            await message.bot.send_document(
                message.chat.id,
                FSInputFile(target),
                caption=escape(relative_posix(root, target)[:900]),
            )
            return
        with tempfile.TemporaryDirectory(prefix="jarvis-zip-") as tmp:
            zip_name = f"{root.name if target == root else target.name}.zip"
            zip_path = Path(tmp) / zip_name
            await message.answer(f"Собираю архив <code>{escape(zip_name)}</code>…")
            size = zip_target(root, target, zip_path)
            await message.bot.send_document(
                message.chat.id,
                FSInputFile(zip_path),
                caption=f"{escape(relative_posix(root, target))} · {human_size(size)}",
            )
    except ProjectPathError as exc:
        await message.answer(str(exc), reply_markup=main_keyboard())
    except Exception:
        log.exception("failed to send project item %s", rel)
        await message.answer("Не удалось отправить файл.", reply_markup=main_keyboard())


def _split(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    rest = text
    while rest:
        chunks.append(rest[:limit])
        rest = rest[limit:]
    return chunks
