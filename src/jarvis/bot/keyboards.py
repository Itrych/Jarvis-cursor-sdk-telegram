from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_PROJECTS = "Проекты"
BTN_NEW = "Новый"
BTN_OPEN = "Открыть"
BTN_TASK = "Задача"
BTN_FILES = "Файлы"
BTN_MODEL = "Модель"
BTN_EFFORT = "Effort"
BTN_STOP = "Стоп"
BTN_STATUS = "Статус"
BTN_HELP = "Справка"

MAIN_BUTTON_ROWS = (
    (BTN_PROJECTS, BTN_NEW, BTN_OPEN),
    (BTN_TASK, BTN_FILES, BTN_STOP),
    (BTN_MODEL, BTN_EFFORT, BTN_STATUS),
    (BTN_HELP,),
)

MAIN_BUTTONS = frozenset(label for row in MAIN_BUTTON_ROWS for label in row)


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label) for label in row] for row in MAIN_BUTTON_ROWS],
        resize_keyboard=True,
    )
