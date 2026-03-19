import sqlite3

conn = sqlite3.connect("users.db")
c = conn.cursor()

c.execute("PRAGMA table_info(users)")
cols = [col[1] for col in c.fetchall()]

def add(col, sql):
    if col not in cols:
        c.execute(sql)
        print(f"✅ Added {col}")

add("email_verified", "ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0")
add("child_age", "ALTER TABLE users ADD COLUMN child_age INTEGER")
add("relationship", "ALTER TABLE users ADD COLUMN relationship TEXT")
add("consent", "ALTER TABLE users ADD COLUMN consent INTEGER DEFAULT 0")
add("test_video", "ALTER TABLE users ADD COLUMN test_video INTEGER DEFAULT 0")

conn.commit()
conn.close()
print("🎉 Database upgraded successfully")
