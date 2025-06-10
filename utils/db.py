import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

DB_URL = None  # глобальна змінна, яку ініціалізуємо

def init_db(url):
    global DB_URL
    DB_URL = url

def get_connection():
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)

def save_items_to_db(items):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("INSERT INTO checks (created_at) VALUES (%s) RETURNING id", (datetime.now(),))
    check_id = cur.fetchone()["id"]

    item_ids = []
    for item in items:
        cur.execute(
            "INSERT INTO items (check_id, name, category, amount, date) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (check_id, item["name"], item["category"], item["sum"], item["date"]),
        )
        item_ids.append(cur.fetchone()["id"])

    conn.commit()
    cur.close()
    conn.close()
    return check_id, item_ids

def get_report(period, from_date=None, to_date=None):
    conn = get_connection()
    cur = conn.cursor()

    if period == "day":
        start_date = datetime.now().strftime("%Y-%m-%d")
        cur.execute("SELECT category, SUM(amount) FROM items WHERE date = %s GROUP BY category", (start_date,))
    elif period == "week":
        start = datetime.now() - timedelta(days=7)
        cur.execute("SELECT category, SUM(amount) FROM items WHERE date >= %s GROUP BY category", (start,))
    elif period == "month":
        start = datetime.now().replace(day=1)
        cur.execute("SELECT category, SUM(amount) FROM items WHERE date >= %s GROUP BY category", (start,))
    elif period == "custom" and from_date and to_date:
        cur.execute("SELECT category, SUM(amount) FROM items WHERE date BETWEEN %s AND %s GROUP BY category", (from_date, to_date))
    else:
        return {}

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return {row["category"]: row["sum"] for row in rows}

def get_debug_info():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM checks")
    checks = cur.fetchone()["count"]
    cur.execute("SELECT COUNT(*) FROM items")
    items = cur.fetchone()["count"]
    cur.close()
    conn.close()
    return {"checks": checks, "items": items}

def delete_check_by_id(check_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM items WHERE check_id = %s", (check_id,))
    cur.execute("DELETE FROM checks WHERE id = %s", (check_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    cur.close()
    conn.close()
    return deleted

def delete_item_by_id(item_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM items WHERE id = %s", (item_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    cur.close()
    conn.close()
    return deleted
