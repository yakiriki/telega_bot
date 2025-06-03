
import sqlite3
from datetime import datetime

def init_db():
    conn = sqlite3.connect("expenses.db")
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            price REAL,
            category TEXT,
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()

def insert_expense(user_id, name, price, category):
    conn = sqlite3.connect("expenses.db")
    cur = conn.cursor()
    cur.execute("INSERT INTO expenses (user_id, name, price, category, date) VALUES (?, ?, ?, ?, ?)",
                (user_id, name, price, category, datetime.now().strftime("%Y-%m-%d")))
    conn.commit()
    conn.close()

def get_daily_summary(user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect("expenses.db")
    cur = conn.cursor()
    cur.execute("SELECT category, SUM(price) FROM expenses WHERE user_id=? AND date=? GROUP BY category", (user_id, today))
    data = cur.fetchall()
    conn.close()
    return data
