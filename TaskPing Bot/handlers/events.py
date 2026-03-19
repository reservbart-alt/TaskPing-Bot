from aiogram import types
from database import add_event, get_events


async def add_event_handler(message: types.Message):
    user_id = message.from_user.id
    text = message.text

    try:
        parts = text.split()

        event_text = " ".join(parts[:-2])
        date = f"{parts[-2]} {parts[-1]}"

        add_event(user_id, event_text, date)

        await message.answer("✅ Событие добавлено")

    except:
        await message.answer("❌ Пример:\nАвтошкола 19.03 16:30")


async def show_events(message: types.Message):
    user_id = message.from_user.id
    events = get_events(user_id)

    if not events:
        await message.answer("📭 У тебя нет событий")
        return

    text = "📅 Твои события:\n\n"

    for event in events:
        text += f"• {event[0]} — {event[1]}\n"

    await message.answer(text)