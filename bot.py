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
    managing = State()

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

# --- PARSING ---
def parse_timezone(text: str):
    text = text.strip().upper().replace(" ", "")
    match = re.match(r"(UTC)?([+-]?\d{1,2})", text)
    if not match:
        return None
    offset = int(match.group(2))
    return offset if -12 <= offset <= 14 else None

def parse_time(text):
    nums = list(map(int, re.findall(r"\d+", text)))
    if len(nums) < 2:
        return None
    return nums[0], nums[1]

def format_date(dt):
    return f"{dt.day} {months[dt.month]} в {dt.strftime('%H:%M')}"

# --- DATA ---
def get_categories(user_id):
    cursor.execute("SELECT name FROM categories WHERE user_id=?", (user_id,))
    return [r[0] for r in cursor.fetchall()]

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
        [KeyboardButton(text="📂 Категории")],
        [KeyboardButton(text="🌍 Часовой пояс")]
    ]
    for c in get_categories(user_id):
        kb.append([KeyboardButton(text=c)])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- HANDLER ---
@dp.message()
async def handler(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text

    add_user(user_id)

    if text == "/start":
        await state.clear()
        await message.answer("Меню", reply_markup=menu(user_id))

    # --- TZ ---
    elif text == "🌍 Часовой пояс":
        await state.set_state(TimezoneState.choosing)
        await message.answer("Введи: UTC+3 / 3 / -5")

    elif await state.get_state() == TimezoneState.choosing:
        offset = parse_timezone(text)

        if offset is None:
            await message.answer("❌ Пример: UTC+3 или 3")
            return

        set_user_timezone(user_id, offset)
        await state.clear()
        await message.answer(f"✅ UTC{offset:+}", reply_markup=menu(user_id))

    # --- CATEGORY ---
    elif text == "📂 Категории":
        await state.set_state(CategoryState.managing)
        await message.answer("Напиши название\nили -название для удаления")

    elif await state.get_state() == CategoryState.managing:
        if text.startswith("-"):
            cursor.execute(
                "DELETE FROM categories WHERE name=? AND user_id=?",
                (text[1:], user_id)
            )
            conn.commit()
            await message.answer("Удалено", reply_markup=menu(user_id))
        else:
            cursor.execute(
                "INSERT INTO categories(user_id,name) VALUES(?,?)",
                (user_id, text)
            )
            conn.commit()
            await message.answer("Добавлено", reply_markup=menu(user_id))

        await state.clear()

    # --- CREATE EVENT ---
    elif text == "➕ Создать событие":
        await message.answer("Выбери категорию")

    elif text in get_categories(user_id):
        await state.update_data(category=text)
        await state.set_state(CreateEvent.choosing_date)

        cal = SimpleCalendar()
        await message.answer("Дата:", reply_markup=await cal.start_calendar())

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

    # --- DELETE ---
    elif text == "❌ Удалить событие":
        cursor.execute("SELECT id,category,date FROM events WHERE user_id=?", (user_id,))
        rows = cursor.fetchall()

        if not rows:
            await message.answer("Нет событий")
            return

        await state.set_state(DeleteEventState.choosing)
        await state.update_data(events=rows)

        msg = "\n".join(
            f"{i+1}. {r[1]} {format_date(datetime.strptime(r[2], '%Y-%m-%d %H:%M'))}"
            for i, r in enumerate(rows)
        )

        await message.answer(msg)

    elif await state.get_state() == DeleteEventState.choosing:
        data = await state.get_data()

        try:
            event = data["events"][int(text)-1]
            cursor.execute("DELETE FROM events WHERE id=?", (event[0],))
            conn.commit()
            await message.answer("Удалено", reply_markup=menu(user_id))
            await state.clear()
        except:
            await message.answer("Ошибка")

    # --- EDIT ---
    elif text == "✏️ Редактировать событие":
        cursor.execute("SELECT id,category,date FROM events WHERE user_id=?", (user_id,))
        rows = cursor.fetchall()

        if not rows:
            await message.answer("Нет событий")
            return

        await state.set_state(EditEvent.choosing_event)
        await state.update_data(events=rows)

        msg = "\n".join(
            f"{i+1}. {r[1]} {format_date(datetime.strptime(r[2], '%Y-%m-%d %H:%M'))}"
            for i, r in enumerate(rows)
        )

        await message.answer(msg)

    elif await state.get_state() == EditEvent.choosing_event:
        data = await state.get_data()

        try:
            event = data["events"][int(text)-1]
            await state.update_data(event_id=event[0])
        except:
            await message.answer("Ошибка")
            return

        cal = SimpleCalendar()
        await message.answer("Новая дата:", reply_markup=await cal.start_calendar())

        await state.set_state(EditEvent.choosing_date)

# --- CALENDAR ---
@dp.callback_query(SimpleCalendarCallback.filter())
async def calendar_handler(callback: types.CallbackQuery, callback_data: dict, state: FSMContext):
    cal = SimpleCalendar()
    ok, date = await cal.process_selection(callback, callback_data)

    if ok:
        await state.update_data(date=date)
        await state.set_state(EditEvent.choosing_time)
        await callback.message.answer("Время (18:30):")

# --- TIME (CREATE + EDIT) ---
@dp.message(CreateEvent.choosing_time)
@dp.message(EditEvent.choosing_time)
async def time_handler(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    t = parse_time(message.text)

    if not t:
        await message.answer("Формат 18:30")
        return

    data = await state.get_data()
    tz = get_tz(user_id)

    dt = datetime(data["date"].year, data["date"].month, data["date"].day, t[0], t[1], tzinfo=tz)

    if "category" in data:
        cursor.execute(
            "INSERT INTO events(user_id,category,date) VALUES(?,?,?)",
            (user_id, data["category"], dt.strftime("%Y-%m-%d %H:%M"))
        )
        schedule_event(message.chat.id, data["category"], dt)
        await message.answer("Создано", reply_markup=menu(user_id))

    else:
        cursor.execute(
            "UPDATE events SET date=? WHERE id=?",
            (dt.strftime("%Y-%m-%d %H:%M"), data["event_id"])
        )
        await message.answer("Обновлено", reply_markup=menu(user_id))

    conn.commit()
    await state.clear()

# --- START ---
async def main():
    scheduler.start()
    scheduler.add_job(daily, "cron", minute=0)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
