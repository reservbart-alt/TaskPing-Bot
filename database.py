import sqlite3

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS categories(
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS events(
id INTEGER PRIMARY KEY AUTOINCREMENT,
category TEXT,
date TEXT,
chat_id INTEGER
)
""")

conn.commit()


def add_category(name):

    cursor.execute(
        "INSERT INTO categories(name) VALUES(?)",
        (name,)
    )

    conn.commit()


def get_categories():

    cursor.execute("SELECT name FROM categories")

    rows = cursor.fetchall()

    return [r[0] for r in rows]


def delete_category(name):

    cursor.execute(
        "DELETE FROM categories WHERE name=?",
        (name,)
    )

    conn.commit()


def add_event(category,date,chat_id):

    cursor.execute(
        "INSERT INTO events(category,date,chat_id) VALUES(?,?,?)",
        (category,date,chat_id)
    )

    conn.commit()


def get_events():

    cursor.execute("SELECT id,category,date FROM events")

    return cursor.fetchall()


def delete_event(event_id):

    cursor.execute(
        "DELETE FROM events WHERE id=?",
        (event_id,)
    )

    conn.commit()