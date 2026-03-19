import asyncio
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import TOKEN

bot = Bot(token=TOKEN)
dp = Dispatcher()

scheduler = AsyncIOScheduler()

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

# --- БАЗА ДАННЫХ ---
cursor.execute("""
CREATE TABLE IF NOT EXISTS categories(
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id INTEGER,
name TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS events(
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id INTEGER,
category TEXT,
date TEXT
)
""")

conn.commit()

state = None
current_category = None

months = {
1:"января",2:"февраля",3:"марта",4:"апреля",
5:"мая",6:"июня",7:"июля",8:"августа",
9:"сентября",10:"октября",11:"ноября",12:"декабря"
}

# --- КАТЕГОРИИ ---
def get_categories(user_id):
    cursor.execute("SELECT name FROM categories WHERE user_id=?", (user_id,))
    rows = cursor.fetchall()
    return [r[0] for r in rows]

def build_menu(user_id):
    keyboard = [
        [KeyboardButton(text="✏️ Редактировать категории")],
        [KeyboardButton(text="📅 Мои события")],
        [KeyboardButton(text="❌ Удалить событие")]
    ]

    for c in get_categories(user_id):
        keyboard.append([KeyboardButton(text=c)])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def category_menu():
    keyboard = [
        [KeyboardButton(text="➕ Создать категорию")],
        [KeyboardButton(text="🗑 Удалить категорию")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def format_date(dt):
    return f"{dt.day} {months[dt.month]} в {dt.strftime('%H:%M')}"

# --- НАПОМИНАНИЯ ---
async def send_reminder(chat_id, text):
    await bot.send_message(chat_id, f"⏰ Напоминание!\n\n{text}")

def schedule_event(chat_id, category, dt):
    text = f"{category} — {format_date(dt)}"

    scheduler.add_job(send_reminder, "date",
        run_date=dt - timedelta(hours=2),
        args=[chat_id, text]
    )

    scheduler.add_job(send_reminder, "date",
        run_date=dt - timedelta(days=1),
        args=[chat_id, text]
    )

# --- ОБРАБОТКА ---
@dp.message()
async def handler(message: types.Message):

    global state, current_category

    user_id = message.from_user.id
    text = message.text

    if text == "/start":
        await message.answer(
            "Привет! Я бот напоминаний",
            reply_markup=build_menu(user_id)
        )

    elif text == "✏️ Редактировать категории":
        await message.answer("Редактор категорий", reply_markup=category_menu())

    elif text == "⬅️ Назад":
        await message.answer("Главное меню", reply_markup=build_menu(user_id))

    elif text == "➕ Создать категорию":
        state = "create_category"
        await message.answer("Напиши название категории")

    elif state == "create_category":
        cursor.execute(
            "INSERT INTO categories(user_id,name) VALUES(?,?)",
            (user_id, text)
        )
        conn.commit()
        state = None

        await message.answer(
            f"Категория создана: {text}",
            reply_markup=build_menu(user_id)
        )

    elif text == "🗑 Удалить категорию":
        cats = get_categories(user_id)

        if not cats:
            await message.answer("Категорий нет")
            return

        msg = "Напиши название категории\n\n"
        for c in cats:
            msg += c + "\n"

        state = "delete_category"
        await message.answer(msg)

    elif state == "delete_category":
        cursor.execute(
            "DELETE FROM categories WHERE name=? AND user_id=?",
            (text, user_id)
        )
        cursor.execute(
            "DELETE FROM events WHERE category=? AND user_id=?",
            (text, user_id)
        )
        conn.commit()
        state = None

        await message.answer("Категория удалена", reply_markup=build_menu(user_id))

    elif text in get_categories(user_id):
        current_category = text
        state = "waiting_date"

        await message.answer("Напиши дату\nпример: 19.03 18:00")

    elif state == "waiting_date":
        try:
            dt = datetime.strptime(text, "%d.%m %H:%M")

            cursor.execute(
                "INSERT INTO events(user_id,category,date) VALUES(?,?,?)",
                (user_id, current_category, text)
            )
            conn.commit()

            schedule_event(message.chat.id, current_category, dt)

            state = None

            await message.answer(
                "Событие добавлено",
                reply_markup=build_menu(user_id)
            )

        except:
            await message.answer("Формат: 19.03 18:00")

    elif text == "📅 Мои события":

        cursor.execute(
            "SELECT category,date FROM events WHERE user_id=?",
            (user_id,)
        )
        rows = cursor.fetchall()

        if not rows:
            await message.answer("Событий нет")
            return

        events = []
        for r in rows:
            dt = datetime.strptime(r[1], "%d.%m %H:%M")
            events.append((r[0], dt))

        events = sorted(events, key=lambda x: x[1])

        msg = "Твои события:\n\n"

        for i, e in enumerate(events):
            dt = e[1]
            msg += f"{i+1}. {e[0]} — <b>{format_date(dt)}</b>\n"

        await message.answer(msg, parse_mode="HTML")

    elif text == "❌ Удалить событие":

        cursor.execute(
            "SELECT id,category,date FROM events WHERE user_id=?",
            (user_id,)
        )
        rows = cursor.fetchall()

        if not rows:
            await message.answer("Событий нет")
            return

        msg = "Напиши номер события\n\n"

        for i, r in enumerate(rows):
            dt = datetime.strptime(r[2], "%d.%m %H:%M")
            msg += f"{i+1}. {r[1]} {format_date(dt)}\n"

        state = ("delete_event", rows)
        await message.answer(msg)

    elif isinstance(state, tuple) and state[0] == "delete_event":
        try:
            rows = state[1]
            index = int(text) - 1
            event_id = rows[index][0]

            cursor.execute(
                "DELETE FROM events WHERE id=? AND user_id=?",
                (event_id, user_id)
            )
            conn.commit()

            state = None

            await message.answer(
                "Событие удалено",
                reply_markup=build_menu(user_id)
            )

        except:
            await message.answer("Неверный номер")

# --- ЗАПУСК ---
async def main():
    scheduler.start()
    await dp.start_polling(bot)

asyncio.run(main())