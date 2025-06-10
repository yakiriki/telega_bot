def save_items_to_db(items, db_path=None):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("INSERT INTO checks DEFAULT VALUES RETURNING id;")
    new_check_id = cur.fetchone()[0]
    item_ids = []
    for item in items:
        cur.execute(
            "INSERT INTO items (check_id, date, name, category, sum) VALUES (%s, %s, %s, %s, %s) RETURNING id;",
            (new_check_id, item["date"], item["name"], item["category"], item["sum"])
        )
        item_id = cur.fetchone()[0]
        item_ids.append(item_id)
    conn.commit()
    cur.close()
    conn.close()
    return new_check_id, item_ids
