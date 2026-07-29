import sqlite3

def check_db(path):
    print(f'Checking {path}')
    try:
        conn = sqlite3.connect(path)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = c.fetchall()
        print('Tables:', tables)
        if ('users',) in tables or ('user',) in tables:
            t = 'users' if ('users',) in tables else 'user'
            c.execute(f"SELECT COUNT(*) FROM {t}")
            print(f'User count: {c.fetchone()[0]}')
    except Exception as e:
        print('Error:', e)

check_db('opsforge.db')
check_db('instance/opsforge.db')
