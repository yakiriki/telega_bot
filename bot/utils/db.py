import sqlite3
from datetime import datetime, timedelta

def init_db(path):
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        check_id INTEGER,
        date TEXT,
        name TEXT,
        category TEXT,
        sum INTEGER,
        FOREIGN KEY(check_id) REFERENCES checks(id)
    )""")
    conn.commit()
    conn.close()

def save_items_to_db(items, path):
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("INSERT INTO checks (date) VALUES (?)", (now,))
    check_id = cursor.lastrowid
    for item in items:
        cursor.execute("""
        INSERT INTO items (check_id, date, name, category, sum)
        VALUES (?, ?, ?, ?, ?)
        """, (
            check_id,
            item.get("date", now),
            item["name"],
            item["category"],
            item["sum"]
        ))
    conn.commit()
    conn.close()
    return check_id

def get_report(path, period, from_date=None, to
