from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from jarvis.bot.keyboards import (
    BTN_EFFORT,
    BTN_MODEL,
    BTN_STOP,
    BTN_TASK,
    MAIN_BUTTONS,
    main_keyboard,
)
from jarvis.config import Settings
from jarvis.models import format_selection, merge_params
from jarvis.runtime import AgentRuntime, ProjectBusyError
from jarvis.store import Store

router = Router(name="jarvis-agent")


class AgentForm(StatesGroup):
    waiting_prompt = State()


def _models_keyboard(models: list) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, item in enumerate(models[:25]):
        label = (getattr(item, "display_name", None) or item.id)[:64]
        rows.append([InlineKeyboardButton(text=label, callback_data=f"md:{index}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _effort_keyboard(options: list) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=option.label[:64], callback_data=f"ef:{index}")]
        for index, option in enumerate(options[:25])
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("task"))
async def cmd_task(
    message: Message,
    command: CommandObject,
    store: Store,
    runtime: AgentRuntime,
    settings: Settings,
    state: FSMContext,
) -> None:
    arg = (command.args or "").strip()
    if arg:
        await _dispatch_prompt(message, store, runtime, settings, state, arg)
        return
    await state.set_state(AgentForm.waiting_prompt)
    await message.answer("Напиши задачу для активного проекта.", reply_markup=main_keyboard())


@router.message(F.text == BTN_TASK)
async def btn_task(message: Message, state: FSMContext) -> None:
    await state.set_state(AgentForm.waiting_prompt)
    await message.answer("Напиши задачу для активного проекта.", reply_markup=main_keyboard())


@router.message(AgentForm.waiting_prompt, F.text)
async def on_prompt(
    message: Message,
    store: Store,
    runtime: AgentRuntime,
    settings: Settings,
    state: FSMContext,
) -> None:
    text = (message.text or "").strip()
    if text.startswith("/"):
        await state.clear()
        await message.answer("Ввод задачи отменён.", reply_markup=main_keyboard())
        return
    await _dispatch_prompt(message, store, runtime, settings, state, text)


@router.message(Command("model"))
@router.message(F.text == BTN_MODEL)
async def cmd_model(message: Message, runtime: AgentRuntime, store: Store) -> None:
    if not message.bot:
        return
    try:
        models = await runtime.list_models()
    except Exception as exc:
        await message.answer(f"Не удалось получить список моделей: {exc}", reply_markup=main_keyboard())
        return
    if not models:
        await message.answer("Каталог моделей пуст.", reply_markup=main_keyboard())
        return
    active = await store.get_active(message.chat.id)
    current = (
        format_selection(active.model, active.model_params) if active else None
    )
    hint = f"Сейчас: <code>{escape(current)}</code>\n" if current else ""
    await message.answer(
        hint + "Выбери модель для активного проекта. После неё спрошу effort.",
        reply_markup=_models_keyboard(models),
    )


@router.callback_query(F.data.startswith("md:"))
async def cb_model(query: CallbackQuery, runtime: AgentRuntime, store: Store) -> None:
    raw = (query.data or "")[3:]
    try:
        index = int(raw)
    except ValueError:
        await query.answer("Некорректный выбор", show_alert=True)
        return
    model = runtime.model_by_index(index)
    if not model:
        await query.answer("Список устарел, нажми /model ещё раз", show_alert=True)
        return
    if query.message is None:
        await query.answer()
        return
    active = await store.get_active(query.message.chat.id)
    if active is None:
        await query.answer("Сначала выбери проект", show_alert=True)
        return
    await store.update_agent(active.id, active.agent_id, model.id, model_params=())
    await query.message.answer(
        f"Модель проекта <b>{escape(active.name)}</b>: <code>{escape(model.id)}</code>.\n"
        "Effort сброшен на значение по умолчанию.",
        reply_markup=main_keyboard(),
    )
    await query.answer(model.id)
    await _prompt_effort(query.message, runtime, model)


@router.message(Command("effort"))
@router.message(F.text == BTN_EFFORT)
async def cmd_effort(
    message: Message, runtime: AgentRuntime, store: Store, settings: Settings
) -> None:
    active = await store.get_active(message.chat.id)
    if active is None:
        await message.answer("Сначала выбери проект.", reply_markup=main_keyboard())
        return
    try:
        await runtime.list_models()
    except Exception as exc:
        await message.answer(f"Не удалось получить каталог моделей: {exc}", reply_markup=main_keyboard())
        return
    model_id = active.model or settings.default_model
    model = runtime.model_by_id(model_id)
    if model is None:
        await message.answer(
            "Текущая модель не найдена в каталоге. Сначала /model.",
            reply_markup=main_keyboard(),
        )
        return
    await message.answer(
        f"Сейчас: <code>{escape(format_selection(active.model, active.model_params))}</code>",
        reply_markup=main_keyboard(),
    )
    await _prompt_effort(message, runtime, model)


@router.callback_query(F.data.startswith("ef:"))
async def cb_effort(query: CallbackQuery, runtime: AgentRuntime, store: Store) -> None:
    raw = (query.data or "")[3:]
    try:
        index = int(raw)
    except ValueError:
        await query.answer("Некорректный выбор", show_alert=True)
        return
    option = runtime.effort_by_index(index)
    if option is None:
        await query.answer("Список устарел, нажми Effort ещё раз", show_alert=True)
        return
    if query.message is None:
        await query.answer()
        return
    active = await store.get_active(query.message.chat.id)
    if active is None:
        await query.answer("Сначала выбери проект", show_alert=True)
        return
    if not active.model:
        await query.answer("Сначала выбери модель", show_alert=True)
        return
    pairs = merge_params(active.model_params, option)
    await store.update_agent(
        active.id, active.agent_id, active.model, model_params=pairs
    )
    await query.message.answer(
        f"Effort проекта <b>{escape(active.name)}</b>: "
        f"<code>{escape(format_selection(active.model, pairs))}</code>",
        reply_markup=main_keyboard(),
    )
    await query.answer(option.label[:64])


async def _prompt_effort(message: Message, runtime: AgentRuntime, model) -> None:
    options = runtime.prepare_effort_options(model)
    if not options:
        await message.answer(
            f"Для <code>{escape(model.id)}</code> каталог Cursor не отдаёт effort. "
            "Можно сразу /task — уйдёт режим по умолчанию.",
            reply_markup=main_keyboard(),
        )
        return
    await message.answer(
        f"Effort для <code>{escape(model.id)}</code>:",
        reply_markup=_effort_keyboard(options),
    )


@router.message(Command("stop"))
@router.message(F.text == BTN_STOP)
async def cmd_stop(
    message: Message, store: Store, runtime: AgentRuntime, state: FSMContext
) -> None:
    current = await state.get_state()
    if current is not None:
        await state.clear()
        await message.answer("Ввод отменён.", reply_markup=main_keyboard())
        return
    active = await store.get_active(message.chat.id)
    if active is None:
        await message.answer("Нет активного проекта.", reply_markup=main_keyboard())
        return
    cancelled = await runtime.cancel(active.id)
    if cancelled:
        await message.answer(f"Останавливаю прогон <b>{escape(active.name)}</b>…", reply_markup=main_keyboard())
        return
    await message.answer("Сейчас нет активного прогона.", reply_markup=main_keyboard())


async def _dispatch_prompt(
    message: Message,
    store: Store,
    runtime: AgentRuntime,
    settings: Settings,
    state: FSMContext,
    prompt: str,
) -> None:
    await state.clear()
    if not settings.cursor_ready:
        await message.answer("CURSOR_API_KEY не задан.", reply_markup=main_keyboard())
        return
    active = await store.get_active(message.chat.id)
    if active is None:
        await message.answer("Сначала выбери проект: /new, /open или /projects.", reply_markup=main_keyboard())
        return
    if runtime.is_busy(active.id):
        await message.answer(
            f"Проект <b>{escape(active.name)}</b> уже занят. /stop или подожди.",
            reply_markup=main_keyboard(),
        )
        return
    if message.bot is None:
        return
    await message.answer(
        f"Задача ушла в <b>{escape(active.name)}</b>…",
        reply_markup=main_keyboard(),
    )
    try:
        await runtime.run_prompt(
            message.bot,
            message.chat.id,
            active,
            prompt,
            model=active.model or settings.default_model,
        )
    except ProjectBusyError as exc:
        await message.answer(str(exc), reply_markup=main_keyboard())


@router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def follow_up(
    message: Message,
    store: Store,
    runtime: AgentRuntime,
    settings: Settings,
    state: FSMContext,
) -> None:
    text = (message.text or "").strip()
    if text in MAIN_BUTTONS:
        return
    await _dispatch_prompt(message, store, runtime, settings, state, text)
