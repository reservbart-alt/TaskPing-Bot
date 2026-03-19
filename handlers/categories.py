from aiogram import Router
from database import get_categories

router = Router()

@router.callback_query(lambda c: c.data == "categories")
async def categories(callback):

    cats = get_categories()

    if not cats:

        await callback.message.answer("Категорий нет")

        return

    text = "Категории\n\n"

    for c in cats:

        text += f"{c}\n"

    await callback.message.answer(text)