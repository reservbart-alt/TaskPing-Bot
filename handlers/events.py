from aiogram import Router
from database import get_events

router = Router()

@router.callback_query(lambda c: c.data == "events")
async def show_events(callback):

    events = get_events()

    if not events:

        await callback.message.answer("Событий нет")

        return

    text = "Твои события\n\n"

    for e in events:

        text += f"{e[1]} — {e[2]}\n"

    await callback.message.answer(text)