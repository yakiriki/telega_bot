import sqlite3
from datetime import datetime

conn = sqlite3.connect("expenses.db", check_same_thread=False)
cur = conn.cursor()

def init_db():
    cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            name TEXT,
            price REAL,
            category TEXT,
            date TEXT,
            receipt_id TEXT
        )
    """)
    conn.commit()

def insert_expense(user_id, name, price, category, receipt_id):
    date = datetime.now().strftime("%Y-%m-%d")
    cur.execute("""
        INSERT INTO expenses (user_id, name, price, category, date, receipt_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, name, price, category, date, receipt_id))
    conn.commit()

def get_summary(user_id, start_date):
    cur.execute("""
        SELECT category, SUM(price)
        FROM expenses
        WHERE user_id = ? AND date >= ?
        GROUP BY category
    """, (user_id, start_date))
    return cur.fetchall()

def delete_item(item_id):
    cur.execute("DELETE FROM expenses WHERE id = ?", (item_id,))
    conn.commit()

def delete_receipt(receipt_id):
    cur.execute("DELETE FROM expenses WHERE receipt_id = ?", (receipt_id,))
    conn.commit()
