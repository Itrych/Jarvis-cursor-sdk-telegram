from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from jarvis.bot.keyboards import (
    BTN_HELP,
    BTN_NEW,
    BTN_OPEN,
    BTN_PROJECTS,
    BTN_STATUS,
    main_keyboard,
)
from jarvis.config import Settings
from jarvis.models import format_selection
from jarvis.projects import attach_existing_project, create_new_project, scan_project_dirs
from jarvis.store import Project, ProjectNameError, Store

router = Router(name="jarvis")


class Form(StatesGroup):
    new_project_name = State()


def _project_line(project: Project | None) -> str:
    if project is None:
        return "Активный проект: не выбран"
    return f"Активный проект: <b>{escape(project.name)}</b>"


def _projects_keyboard(projects: list[Project], active_id: int | None) -> InlineKeyboardMarkup | None:
    if not projects:
        return None
    rows: list[list[InlineKeyboardButton]] = []
    for project in projects[:20]:
        mark = "• " if project.id == active_id else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark}{project.name}"[:64],
                    callback_data=f"use:{project.id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _open_keyboard(names: list[str]) -> InlineKeyboardMarkup | None:
    if not names:
        return None
    rows = [
        [InlineKeyboardButton(text=name[:64], callback_data=f"open:{name}")]
        for name in names[:20]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(CommandStart())
async def cmd_start(message: Message, settings: Settings, store: Store, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id if message.from_user else 0
    if settings.bootstrap_acl:
        await message.answer(
            "Jarvis в режиме настройки.\n"
            f"Твой Telegram user id: <code>{user_id}</code>\n"
            "Добавь его в <code>TELEGRAM_ALLOWED_USER_IDS</code> в файле <code>.env</code> "
            "и перезапусти демон.",
        )
        return
    active = await store.get_active(message.chat.id)
    await message.answer(
        "Jarvis на связи.\n"
        "Команды и кнопки делают одно и то же.\n"
        f"{_project_line(active)}",
        reply_markup=main_keyboard(),
    )


@router.message(Command("help"))
@router.message(F.text == BTN_HELP)
async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "<b>Jarvis</b> — пульт к локальному Cursor-агенту.\n\n"
        "/start — клавиатура\n"
        "/help — эта справка\n"
        "/status — конфиг без секретов\n"
        "/new [имя] — новый проект (папка в projects_root)\n"
        "/open — взять существующую папку\n"
        "/projects — список и переключение\n"
        "/task [текст] — задача активному агенту\n"
        "/files [путь] — список файлов проекта\n"
        "/get путь — прислать файл; папка или <code>.</code> — zip\n"
        "/model — сменить модель и effort\n"
        "/effort — только effort текущей модели\n"
        "/stop — отмена ввода или прогона\n"
        "Обычное сообщение — follow-up в активный проект.",
        reply_markup=main_keyboard(),
    )


@router.message(Command("status"))
@router.message(F.text == BTN_STATUS)
async def cmd_status(message: Message, settings: Settings, store: Store, state: FSMContext) -> None:
    await state.clear()
    ids = ", ".join(str(i) for i in sorted(settings.allowed_user_ids)) or "не заданы"
    active = await store.get_active(message.chat.id)
    model_line = (
        format_selection(active.model, active.model_params) if active else "нет проекта"
    )
    await message.answer(
        "<b>Статус Jarvis</b>\n"
        f"Этап: 5, модель + effort\n"
        f"{_project_line(active)}\n"
        f"Модель: <code>{escape(model_line)}</code>\n"
        f"projects_root: <code>{escape(str(settings.projects_root))}</code>\n"
        f"Модель по умолчанию: <code>{escape(settings.default_model)}</code>\n"
        f"Telegram token: {'задан' if settings.telegram_ready else 'нет'}\n"
        f"CURSOR_API_KEY: {'задан' if settings.cursor_ready else 'нет'}\n"
        f"Allowed user ids: <code>{escape(ids)}</code>",
        reply_markup=main_keyboard(),
    )


@router.message(Command("new"))
async def cmd_new(
    message: Message,
    command: CommandObject,
    settings: Settings,
    store: Store,
    state: FSMContext,
) -> None:
    arg = (command.args or "").strip()
    if arg:
        await _create_named_project(message, settings, store, state, arg)
        return
    await _ask_new_project_name(message, state)


@router.message(F.text == BTN_NEW)
async def btn_new(message: Message, state: FSMContext) -> None:
    await _ask_new_project_name(message, state)


async def _ask_new_project_name(message: Message, state: FSMContext) -> None:
    await state.set_state(Form.new_project_name)
    await message.answer(
        "Имя нового проекта (латиница, цифры, точка, дефис). Папка появится в projects_root.",
        reply_markup=main_keyboard(),
    )


@router.message(Form.new_project_name, F.text)
async def on_new_project_name(
    message: Message, settings: Settings, store: Store, state: FSMContext
) -> None:
    text = (message.text or "").strip()
    if text.startswith("/"):
        await state.clear()
        await message.answer("Создание проекта отменено.")
        return
    await _create_named_project(message, settings, store, state, text)


async def _create_named_project(
    message: Message,
    settings: Settings,
    store: Store,
    state: FSMContext,
    name: str,
) -> None:
    try:
        project = await create_new_project(
            store, settings.projects_root, name, settings.default_model
        )
    except FileExistsError:
        await message.answer(
            f"Папка <code>{escape(name)}</code> уже есть. Открой её через /open.",
            reply_markup=main_keyboard(),
        )
        return
    except ProjectNameError as exc:
        await message.answer(str(exc), reply_markup=main_keyboard())
        return
    await state.clear()
    await store.set_active(message.chat.id, project.id)
    await message.answer(
        f"Проект <b>{escape(project.name)}</b> создан.\n"
        f"<code>{escape(project.path)}</code>\n"
        "Он выбран как активный. Дальше /task или просто напиши задачу.",
        reply_markup=main_keyboard(),
    )


@router.message(Command("open"))
@router.message(F.text == BTN_OPEN)
async def cmd_open(message: Message, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    dirs = scan_project_dirs(settings.projects_root)
    if not dirs:
        await message.answer(
            f"В <code>{escape(str(settings.projects_root))}</code> пока нет папок. "
            "Создай проект через /new.",
            reply_markup=main_keyboard(),
        )
        return
    await message.answer(
        "Какую папку открыть?",
        reply_markup=_open_keyboard([p.name for p in dirs]),
    )


@router.callback_query(F.data.startswith("open:"))
async def cb_open(
    query: CallbackQuery, settings: Settings, store: Store
) -> None:
    name = (query.data or "")[5:]
    try:
        project = await attach_existing_project(
            store, settings.projects_root, name, settings.default_model
        )
    except ProjectNameError as exc:
        await query.answer(str(exc)[:200], show_alert=True)
        return
    if query.message:
        await store.set_active(query.message.chat.id, project.id)
        await query.message.answer(
            f"Проект <b>{escape(project.name)}</b> активен.\n"
            f"<code>{escape(project.path)}</code>",
            reply_markup=main_keyboard(),
        )
    await query.answer(f"Открыт {project.name}")


@router.message(Command("projects"))
@router.message(F.text == BTN_PROJECTS)
async def cmd_projects(message: Message, store: Store, state: FSMContext) -> None:
    await state.clear()
    projects = await store.list_projects()
    active = await store.get_active(message.chat.id)
    if not projects:
        await message.answer(
            "Зарегистрированных проектов нет. /new или /open.",
            reply_markup=main_keyboard(),
        )
        return
    lines = [_project_line(active), "Нажми, чтобы переключить:"]
    await message.answer(
        "\n".join(lines),
        reply_markup=_projects_keyboard(projects, active.id if active else None),
    )


@router.callback_query(F.data.startswith("use:"))
async def cb_use(query: CallbackQuery, store: Store) -> None:
    raw = (query.data or "")[4:]
    try:
        project_id = int(raw)
    except ValueError:
        await query.answer("Некорректный проект", show_alert=True)
        return
    project = await store.get_project(project_id)
    if project is None:
        await query.answer("Проект не найден", show_alert=True)
        return
    if query.message:
        await store.set_active(query.message.chat.id, project.id)
        await query.message.answer(
            f"Активный проект: <b>{escape(project.name)}</b>",
            reply_markup=main_keyboard(),
        )
    await query.answer(project.name)

