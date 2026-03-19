import sqlite3
conn = sqlite3.connect("users.db")
c = conn.cursor()
c.execute("UPDATE users SET status='pending' WHERE status IS NULL")
conn.commit()
conn.close()
print("Fixed old accounts")
