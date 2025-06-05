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

def get_report(path, period, from_date=None, to_date=None):
    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    if period == "day":
        date_filter = f"date = '{datetime.now().date()}'"
    elif period == "week":
        start = datetime.now().date() - timedelta(days=7)
        date_filter = f"date >= '{start}'"
    elif period == "month":
        start = datetime.now().replace(day=1).date()
        date_filter = f"date >= '{start}'"
    elif period == "custom":
        date_filter = f"date BETWEEN '{from_date}' AND '{to_date}'"
    else:
        date_filter = "1=1"

    cursor.execute(f"""
    SELECT category, SUM(sum) FROM items
    WHERE {date_filter}
    GROUP BY category
    """)
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

def get_debug_info(path):
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM checks")
    checks = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM items")
    items = cursor.fetchone()[0]
    conn.close()
    return {"checks": checks, "items": items}

def delete_check_by_id(path, check_id):
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM items WHERE check_id = ?", (check_id,))
    cursor.execute("DELETE FROM checks WHERE id = ?", (check_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted > 0

def delete_item_by_id(path, item_id):
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted > 0
