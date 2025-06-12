import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

DB_URL = None

def init_db(url: str):
    global DB_URL
    DB_URL = url

def get_connection():
    if not DB_URL:
        raise RuntimeError("DATABASE_URL не ініціалізовано! Викличте init_db(DATABASE_URL).")
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)

def save_items_to_db(items):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO checks DEFAULT VALUES RETURNING id;")
        check_id = cur.fetchone()['id']
        item_ids = []
        for item in items:
            cur.execute(
                'INSERT INTO items (check_id, date, name, category, "sum") '
                'VALUES (%s, %s, %s, %s, %s) RETURNING id',
                (check_id, item["date"], item["name"], item["category"], item["sum"]),
            )
            item_ids.append(cur.fetchone()['id'])
        conn.commit()
        return check_id, item_ids
    finally:
        cur.close()
        conn.close()

def get_report(period, from_date=None, to_date=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        if period == "day":
            cur.execute(
                'SELECT category, SUM("sum") AS total FROM items '
                'WHERE date = CURRENT_DATE GROUP BY category;'
            )
        elif period == "week":
            cur.execute(
                'SELECT category, SUM("sum") AS total FROM items '
                'WHERE date >= CURRENT_DATE - INTERVAL \'7 days\' GROUP BY category;'
            )
        elif period == "month":
            cur.execute(
                'SELECT category, SUM("sum") AS total FROM items '
                'WHERE date >= date_trunc(\'month\', CURRENT_DATE) GROUP BY category;'
            )
        elif period == "custom" and from_date and to_date:
            cur.execute(
                'SELECT category, SUM("sum") AS total FROM items '
                'WHERE date BETWEEN %s AND %s GROUP BY category;',
                (from_date, to_date),
            )
        else:
            cur.execute(
                'SELECT category, SUM("sum") AS total FROM items GROUP BY category;'
            )
        rows = cur.fetchall()
        return {row["category"]: row["total"] for row in rows}
    finally:
        cur.close()
        conn.close()

def get_debug_info():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS count FROM checks;")
        checks = cur.fetchone()["count"]
        cur.execute("SELECT COUNT(*) AS count FROM items;")
        items = cur.fetchone()["count"]
        return {"checks": checks, "items": items}
    finally:
        cur.close()
        conn.close()

def delete_check_by_id(check_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM checks WHERE id = %s RETURNING id;", (check_id,))
        deleted = cur.fetchone() is not None
        conn.commit()
        return deleted
    finally:
        cur.close()
        conn.close()

def delete_item_by_id(item_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM items WHERE id = %s RETURNING id;", (item_id,))
        deleted = cur.fetchone() is not None
        conn.commit()
        return deleted
    finally:
        cur.close()
        conn.close()
