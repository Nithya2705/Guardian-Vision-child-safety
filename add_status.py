import sqlite3

db = sqlite3.connect("users.db")
c = db.cursor()

c.execute("ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'pending'")
db.commit()
db.close()

print("Status column added")
