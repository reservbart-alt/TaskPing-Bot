from aiogram import Router
from keyboards.menu import main_menu

router = Router()

@router.message(commands=["start"])
async def start(message):

    await message.answer(
        "Привет! Это бот напоминаний",
        reply_markup=main_menu()
    )