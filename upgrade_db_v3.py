import sqlite3

conn = sqlite3.connect("users.db")
c = conn.cursor()

c.execute("PRAGMA table_info(users)")
cols = [col[1] for col in c.fetchall()]

def add(col, sql):
    if col not in cols:
        c.execute(sql)
        print(f"✅ Added {col}")

add("rejection_reason", "ALTER TABLE users ADD COLUMN rejection_reason TEXT")
add("reviewed_at", "ALTER TABLE users ADD COLUMN reviewed_at TEXT")

conn.commit()
conn.close()
print("🎉 Upgrade done")
