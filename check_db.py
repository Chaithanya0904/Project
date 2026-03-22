import sqlite3
conn = sqlite3.connect('database.db')
conn.row_factory = sqlite3.Row
try:
    rows = conn.execute('SELECT id, title, result, status FROM complients ORDER BY id DESC LIMIT 10').fetchall()
    for r in rows:
        print(f"ID: {r['id']}, Title: {r['title']}, Result: {r['result']}, Status: {r['status']}")
except Exception as e:
    print(f"Error: {e}")
conn.close()
