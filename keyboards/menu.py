from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu():

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [InlineKeyboardButton(text="➕ Создать событие",callback_data="create")],

            [InlineKeyboardButton(text="📋 Мои события",callback_data="events")],

            [InlineKeyboardButton(text="📂 Категории",callback_data="categories")]

        ]
    )