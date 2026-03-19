import sqlite3

conn = sqlite3.connect("users.db")
c = conn.cursor()

c.execute("PRAGMA table_info(users)")
cols = [x[1] for x in c.fetchall()]

def add(col, sql):
    if col not in cols:
        c.execute(sql)
        print(f"✅ {col} added")
    else:
        print(f"ℹ️ {col} already exists")

add("child_age", "ALTER TABLE users ADD COLUMN child_age INTEGER")
add("relationship", "ALTER TABLE users ADD COLUMN relationship TEXT")
add("consent", "ALTER TABLE users ADD COLUMN consent TEXT")
add("email_verified", "ALTER TABLE users ADD COLUMN email_verified TEXT DEFAULT 'no'")

conn.commit()
conn.close()

print("Done")
