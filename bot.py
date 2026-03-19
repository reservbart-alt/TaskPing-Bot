import asyncio
import sqlite3
import re
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback

from config import TOKEN

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

# --- DB ---
cursor.execute("""CREATE TABLE IF NOT EXISTS categories(
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id INTEGER,
name TEXT)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS events(
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id INTEGER,
category TEXT,
date TEXT)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS users(
user_id INTEGER PRIMARY KEY,
timezone INTEGER DEFAULT 0)""")

conn.commit()

months = {
1:"января",2:"февраля",3:"марта",4:"апреля",
5:"мая",6:"июня",7:"июля",8:"августа",
9:"сентября",10:"октября",11:"ноября",12:"декабря"
}

# --- FSM ---
class CreateEvent(StatesGroup):
    choosing_date = State()
    choosing_time = State()

class EditEvent(StatesGroup):
    choosing_event = State()
    choosing_date = State()
    choosing_time = State()

class CategoryState(StatesGroup):
    create = State()
    delete = State()

class DeleteEventState(StatesGroup):
    choosing = State()

class TimezoneState(StatesGroup):
    choosing = State()

# --- USERS ---
def add_user(user_id):
    cursor.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)",(user_id,))
    conn.commit()

def set_user_timezone(user_id, offset):
    cursor.execute("UPDATE users SET timezone=? WHERE user_id=?",(offset,user_id))
    conn.commit()

def get_user_timezone(user_id):
    cursor.execute("SELECT timezone FROM users WHERE user_id=?",(user_id,))
    row = cursor.fetchone()
    return row[0] if row else 0

def get_tz(user_id):
    return timezone(timedelta(hours=get_user_timezone(user_id)))

# --- TZ PARSE ---
def parse_timezone(text: str):
    text = text.strip().upper().replace(" ", "")
    match = re.match(r"(UTC)?([+-]?\d{1,2})", text)

    if not match:
        return None

    offset = int(match.group(2))
    if offset < -12 or offset > 14:
        return None

    return offset

# --- UTILS ---
def format_date(dt):
    return f"{dt.day} {months[dt.month]} в {dt.strftime('%H:%M')}"

def parse_time(text):
    nums = list(map(int, re.findall(r"\d+", text)))
    if len(nums) < 2:
        return None
    return nums[0], nums[1]

# --- CATEGORY ---
def get_categories(user_id):
    cursor.execute("SELECT name FROM categories WHERE user_id=?", (user_id,))
    return [r[0] for r in cursor.fetchall()]

# --- EVENTS ---
def get_all_users():
    cursor.execute("SELECT user_id FROM users")
    return [r[0] for r in cursor.fetchall()]

def get_today_events(user_id):
    tz = get_tz(user_id)
    today = datetime.now(tz).date()

    cursor.execute("SELECT category,date FROM events WHERE user_id=?", (user_id,))
    result = []

    for r in cursor.fetchall():
        dt = datetime.strptime(r[1], "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        if dt.date() == today:
            result.append((r[0], dt))

    return sorted(result, key=lambda x: x[1])

# --- REMINDERS ---
async def send_reminder(chat_id, text):
    await bot.send_message(chat_id, f"⏰ Напоминание!\n\n{text}")

def schedule_event(chat_id, category, dt):
    scheduler.add_job(
        send_reminder,
        "date",
        run_date=dt - timedelta(hours=2),
        args=[chat_id, f"{category} — {format_date(dt)}"]
    )

async def daily():
    for user_id in get_all_users():
        tz = get_tz(user_id)
        if datetime.now(tz).hour != 7:
            continue

        events = get_today_events(user_id)
        if not events:
            continue

        msg = "📅 Сегодня:\n\n"
        for e in events:
            msg += f"• {e[0]} — {format_date(e[1])}\n"

        await bot.send_message(user_id, msg)

# --- MENU ---
def menu(user_id):
    kb = [
        [KeyboardButton(text="📅 Мои события")],
        [KeyboardButton(text="➕ Создать событие")],
        [KeyboardButton(text="✏️ Редактировать событие")],
        [KeyboardButton(text="❌ Удалить событие")],
        [KeyboardButton(text="🌍 Часовой пояс")]
    ]
    for c in get_categories(user_id):
        kb.append([KeyboardButton(text=c)])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- HANDLER ---
@dp.message()
async def msg(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text

    add_user(user_id)

    if text == "/start":
        await state.clear()
        await message.answer("Меню", reply_markup=menu(user_id))

    # --- TIMEZONE ---
    elif text == "🌍 Часовой пояс":
        await state.set_state(TimezoneState.choosing)
        await message.answer(
            "🌍 Введи часовой пояс\n\nПримеры:\nUTC+3\n+3\n3\nUTC-5"
        )

    elif await state.get_state() == TimezoneState.choosing:
        offset = parse_timezone(text)

        if offset is None:
            await message.answer(
                "❌ Не понял\nНапиши например: UTC+3 или 3"
            )
            return

        set_user_timezone(user_id, offset)
        await state.clear()
        await message.answer(
            f"✅ Часовой пояс: UTC{offset:+}",
            reply_markup=menu(user_id)
        )

    # --- CREATE EVENT ---
    elif text in get_categories(user_id):
        await state.update_data(category=text)
        await state.set_state(CreateEvent.choosing_date)

        cal = SimpleCalendar()
        await message.answer("Выбери дату:", reply_markup=await cal.start_calendar())

    elif text == "➕ Создать событие":
        await message.answer("Выбери категорию")

    # --- SHOW EVENTS ---
    elif text == "📅 Мои события":
        cursor.execute("SELECT category,date FROM events WHERE user_id=?", (user_id,))
        rows = cursor.fetchall()

        if not rows:
            await message.answer("Нет событий")
            return

        msg = ""
        for i, r in enumerate(rows):
            dt = datetime.strptime(r[1], "%Y-%m-%d %H:%M")
            msg += f"{i+1}. {r[0]} — {format_date(dt)}\n"

        await message.answer(msg)

# --- CALENDAR ---
@dp.callback_query(SimpleCalendarCallback.filter())
async def calendar(callback: types.CallbackQuery, callback_data: dict, state: FSMContext):
    cal = SimpleCalendar()
    ok, date = await cal.process_selection(callback, callback_data)

    if ok:
        await state.update_data(date=date)
        await state.set_state(CreateEvent.choosing_time)
        await callback.message.answer("Время? (18:30)")

# --- CREATE TIME ---
@dp.message(CreateEvent.choosing_time)
async def create_time(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    t = parse_time(message.text)

    if not t:
        await message.answer("Формат 18:30")
        return

    data = await state.get_data()
    tz = get_tz(user_id)

    dt = datetime(data["date"].year, data["date"].month, data["date"].day, t[0], t[1], tzinfo=tz)

    cursor.execute(
        "INSERT INTO events(user_id,category,date) VALUES(?,?,?)",
        (user_id, data["category"], dt.strftime("%Y-%m-%d %H:%M"))
    )
    conn.commit()

    schedule_event(message.chat.id, data["category"], dt)

    await state.clear()
    await message.answer("Создано", reply_markup=menu(user_id))

# --- START ---
async def main():
    scheduler.start()
    scheduler.add_job(daily, "cron", minute=0)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
