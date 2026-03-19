import sqlite3


def init_db():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        text TEXT,
        date TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY
    )
    """)

    conn.commit()
    conn.close()


def add_user(user_id):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (user_id,))

    conn.commit()
    conn.close()


def add_event(user_id, text, date):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO events (user_id, text, date) VALUES (?, ?, ?)",
        (user_id, text, date)
    )

    conn.commit()
    conn.close()


def get_events(user_id):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT text, date FROM events WHERE user_id = ? ORDER BY date",
        (user_id,)
    )

    events = cur.fetchall()
    conn.close()
    return events