import psycopg2
conn = psycopg2.connect('postgresql://opsforge:opsforge_pass@localhost:5432/opsforge_db')
cur = conn.cursor()
cur.execute("SELECT action FROM audit_logs WHERE action = 'SECRET_CREATE_FAILED'")
print("SECRET_CREATE_FAILED events:", cur.fetchall())
conn.close()
