from aiogram import types
from database import add_user

async def start(message: types.Message):
    add_user(message.from_user.id)

    await message.answer(
        "👋 Привет!\n\n"
        "Напиши событие так:\n"
        "Автошкола 19.03 16:30\n\n"
        "Или нажми: 📅 Мои события"
    )