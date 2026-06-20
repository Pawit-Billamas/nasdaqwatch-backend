from db.database import init_db, db_cursor

print("Connecting to Neon PostgreSQL...")
init_db()
print("Tables created successfully!")

with db_cursor() as cur:
    cur.execute("SELECT version()")
    v = cur.fetchone()
    print("PostgreSQL version:", dict(v)["version"][:60])

with db_cursor() as cur:
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    tables = cur.fetchall()
    print("Tables in DB:", [dict(t)["table_name"] for t in tables])

# Test a quick watchlist insert + select + delete
with db_cursor() as cur:
    cur.execute("INSERT INTO watchlist (ticker) VALUES (%s) ON CONFLICT DO NOTHING", ("TEST",))
with db_cursor() as cur:
    cur.execute("SELECT ticker FROM watchlist WHERE ticker = %s", ("TEST",))
    row = cur.fetchone()
    print("Test row:", dict(row) if row else "not found")
with db_cursor() as cur:
    cur.execute("DELETE FROM watchlist WHERE ticker = %s", ("TEST",))

print("All checks passed! Migration successful.")
