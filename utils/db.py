import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")

def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS checks (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id SERIAL PRIMARY KEY,
            check_id INTEGER REFERENCES checks(id) ON DELETE CASCADE,
            date DATE NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            sum INTEGER NOT NULL
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

def save_items_to_db(items, db_path=None):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("INSERT INTO checks DEFAULT VALUES RETURNING id;")
    new_check_id = cur.fetchone()[0]
    for item in items:
        cur.execute(
            "INSERT INTO items (check_id, date, name, category, sum) VALUES (%s, %s, %s, %s, %s)",
            (new_check_id, item["date"], item["name"], item["category"], item["sum"])
        )
    conn.commit()
    cur.close()
    conn.close()
    return new_check_id

def get_report(db_path, period, from_date=None, to_date=None):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    if period == "day":
        cur.execute("""
            SELECT category, SUM(sum) AS total
            FROM items
            WHERE date = CURRENT_DATE
            GROUP BY category;
        """)
    elif period == "week":
        cur.execute("""
            SELECT category, SUM(sum) AS total
            FROM items
            WHERE date >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY category;
        """)
    elif period == "month":
        cur.execute("""
            SELECT category, SUM(sum) AS total
            FROM items
            WHERE date >= date_trunc('month', CURRENT_DATE)
            GROUP BY category;
        """)
    elif period == "custom" and from_date and to_date:
        cur.execute("""
            SELECT category, SUM(sum) AS total
            FROM items
            WHERE date BETWEEN %s AND %s
            GROUP BY category;
        """, (from_date, to_date))
    else:
        cur.execute("SELECT category, SUM(sum) AS total FROM items GROUP BY category;")

    rows = cur.fetchall()
    conn.close()
    return {row["category"]: row["total"] for row in rows}

def get_debug_info(db_path=None):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM checks;")
    checks_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM items;")
    items_count = cur.fetchone()[0]
    conn.close()
    return {"checks": checks_count, "items": items_count}

def delete_check_by_id(db_path, check_id):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("DELETE FROM checks WHERE id = %s RETURNING id;", (check_id,))
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return bool(deleted)

def delete_item_by_id(db_path, item_id):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("DELETE FROM items WHERE id = %s RETURNING id;", (item_id,))
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return bool(deleted)
