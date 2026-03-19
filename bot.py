import asyncio
import sqlite3
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import TOKEN

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

# --- БАЗА ---
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

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
user_id INTEGER PRIMARY KEY,
timezone TEXT DEFAULT 'UTC'
)
""")

conn.commit()

months = {
    1:"января",2:"февраля",3:"марта",4:"апреля",
    5:"мая",6:"июня",7:"июля",8:"августа",
    9:"сентября",10:"октября",11:"ноября",12:"декабря"
}

# --- FSM ---
class CreateEvent(StatesGroup):
    waiting_date = State()

class CategoryState(StatesGroup):
    create = State()
    delete = State()

class TimezoneState(StatesGroup):
    choosing = State()

class DeleteEventState(StatesGroup):
    choosing = State()

# --- USERS ---
def add_user(user_id):
    cursor.execute(
        "INSERT OR IGNORE INTO users(user_id) VALUES(?)",
        (user_id,)
    )
    conn.commit()

def set_user_timezone(user_id, tz):
    cursor.execute(
        "UPDATE users SET timezone=? WHERE user_id=?",
        (tz, user_id)
    )
    conn.commit()

def get_user_timezone(user_id):
    cursor.execute(
        "SELECT timezone FROM users WHERE user_id=?",
        (user_id,)
    )
    row = cursor.fetchone()
    return row[0] if row else "UTC"

# --- ДАТА ---
def parse_user_date(text: str, user_id: int):
    user_tz = ZoneInfo(get_user_timezone(user_id))
    now = datetime.now(user_tz)

    numbers = list(map(int, re.findall(r"\d+", text)))

    if len(numbers) < 4:
        return None

    try:
        day, month, hour, minute = numbers[:4]
        year = now.year

        dt = datetime(year, month, day, hour, minute, tzinfo=user_tz)

        if dt < now:
            dt = datetime(year + 1, month, day, hour, minute, tzinfo=user_tz)

        return dt
    except:
        return None

# --- КАТЕГОРИИ ---
def get_categories(user_id):
    cursor.execute("SELECT name FROM categories WHERE user_id=?", (user_id,))
    return [r[0] for r in cursor.fetchall()]

def build_menu(user_id):
    keyboard = [
        [KeyboardButton(text="✏️ Редактировать категории")],
        [KeyboardButton(text="📅 Мои события")],
        [KeyboardButton(text="❌ Удалить событие")],
        [KeyboardButton(text="🌍 Часовой пояс")]
    ]

    for c in get_categories(user_id):
        keyboard.append([KeyboardButton(text=c)])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def category_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Создать категорию")],
            [KeyboardButton(text="🗑 Удалить категорию")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )

def format_date(dt):
    return f"{dt.day} {months[dt.month]} в {dt.strftime('%H:%M')}"

# --- СОБЫТИЯ ---
def get_all_users():
    cursor.execute("SELECT user_id FROM users")
    return [r[0] for r in cursor.fetchall()]

def get_today_events(user_id):
    user_tz = ZoneInfo(get_user_timezone(user_id))
    today = datetime.now(user_tz).date()

    cursor.execute(
        "SELECT category, date FROM events WHERE user_id=?",
        (user_id,)
    )

    result = []

    for r in cursor.fetchall():
        try:
            dt = datetime.strptime(r[1], "%Y-%m-%d %H:%M").replace(tzinfo=user_tz)
            if dt.date() == today:
                result.append((r[0], dt))
        except:
            continue

    return sorted(result, key=lambda x: x[1])

# --- НАПОМИНАНИЯ ---
async def send_reminder(chat_id, text):
    await bot.send_message(chat_id, f"⏰ Напоминание!\n\n{text}")

def schedule_event(chat_id, category, dt):
    text = f"{category} — {format_date(dt)}"

    scheduler.add_job(
        send_reminder,
        "date",
        run_date=dt - timedelta(hours=2),
        args=[chat_id, text]
    )

async def send_daily_notifications():
    users = get_all_users()

    for user_id in users:
        user_tz = ZoneInfo(get_user_timezone(user_id))
        now = datetime.now(user_tz)

        if now.hour != 7:
            continue

        events = get_today_events(user_id)

        if not events:
            continue

        msg = "📅 События на сегодня:\n\n"
        for e in events:
            msg += f"• {e[0]} — {format_date(e[1])}\n"

        try:
            await bot.send_message(user_id, msg)
        except:
            pass

# --- ХЕНДЛЕРЫ ---
@dp.message()
async def handler(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text

    add_user(user_id)

    # START
    if text == "/start":
        await state.clear()
        await message.answer("Привет!", reply_markup=build_menu(user_id))

    # TIMEZONE
    elif text == "🌍 Часовой пояс":
        await state.set_state(TimezoneState.choosing)
        await message.answer("Выбери:", reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Москва")],
                [KeyboardButton(text="Томск")],
                [KeyboardButton(text="UTC")]
            ], resize_keyboard=True))

    elif await state.get_state() == TimezoneState.choosing:
        tz_map = {
            "Москва": "Europe/Moscow",
            "Томск": "Asia/Tomsk",
            "UTC": "UTC"
        }

        if text not in tz_map:
            await message.answer("Жми кнопку")
            return

        set_user_timezone(user_id, tz_map[text])
        await state.clear()
        await message.answer("Сохранено", reply_markup=build_menu(user_id))

    # CATEGORY
    elif text == "✏️ Редактировать категории":
        await message.answer("Меню", reply_markup=category_menu())

    elif text == "➕ Создать категорию":
        await state.set_state(CategoryState.create)
        await message.answer("Название?")

    elif await state.get_state() == CategoryState.create:
        cursor.execute(
            "INSERT INTO categories(user_id,name) VALUES(?,?)",
            (user_id, text)
        )
        conn.commit()
        await state.clear()
        await message.answer("Создано", reply_markup=build_menu(user_id))

    elif text == "🗑 Удалить категорию":
        await state.set_state(CategoryState.delete)
        await message.answer("\n".join(get_categories(user_id)))

    elif await state.get_state() == CategoryState.delete:
        cursor.execute(
            "DELETE FROM categories WHERE name=? AND user_id=?",
            (text, user_id)
        )
        conn.commit()
        await state.clear()
        await message.answer("Удалено", reply_markup=build_menu(user_id))

    # СОЗДАНИЕ СОБЫТИЯ
    elif text in get_categories(user_id):
        await state.update_data(category=text)
        await state.set_state(CreateEvent.waiting_date)
        await message.answer("Дата?")

    elif await state.get_state() == CreateEvent.waiting_date:
        data = await state.get_data()
        category = data["category"]

        dt = parse_user_date(text, user_id)

        if not dt:
            await message.answer("Неверный формат")
            return

        cursor.execute(
            "INSERT INTO events(user_id,category,date) VALUES(?,?,?)",
            (user_id, category, dt.strftime("%Y-%m-%d %H:%M"))
        )
        conn.commit()

        schedule_event(message.chat.id, category, dt)

        await state.clear()
        await message.answer("Добавлено", reply_markup=build_menu(user_id))

    # МОИ СОБЫТИЯ
    elif text == "📅 Мои события":
        cursor.execute(
            "SELECT category,date FROM events WHERE user_id=?",
            (user_id,)
        )

        rows = cursor.fetchall()

        if not rows:
            await message.answer("Нет событий")
            return

        msg = ""
        for i, r in enumerate(rows):
            dt = datetime.strptime(r[1], "%Y-%m-%d %H:%M")
            msg += f"{i+1}. {r[0]} — {format_date(dt)}\n"

        await message.answer(msg)

    # УДАЛЕНИЕ СОБЫТИЯ
    elif text == "❌ Удалить событие":
        cursor.execute(
            "SELECT id,category,date FROM events WHERE user_id=?",
            (user_id,)
        )
        rows = cursor.fetchall()

        if not rows:
            await message.answer("Нет событий")
            return

        await state.set_state(DeleteEventState.choosing)
        await state.update_data(events=rows)

        msg = ""
        for i, r in enumerate(rows):
            dt = datetime.strptime(r[2], "%Y-%m-%d %H:%M")
            msg += f"{i+1}. {r[1]} {format_date(dt)}\n"

        await message.answer(msg)

    elif await state.get_state() == DeleteEventState.choosing:
        data = await state.get_data()
        rows = data["events"]

        try:
            index = int(text) - 1
            event_id = rows[index][0]

            cursor.execute(
                "DELETE FROM events WHERE id=?",
                (event_id,)
            )
            conn.commit()

            await state.clear()
            await message.answer("Удалено", reply_markup=build_menu(user_id))
        except:
            await message.answer("Ошибка")

# --- ЗАПУСК ---
async def main():
    scheduler.start()

    scheduler.add_job(
        send_daily_notifications,
        trigger="cron",
        minute=0
    )

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())