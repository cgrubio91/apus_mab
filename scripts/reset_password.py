import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.presentation.auth import hash_password
import mysql.connector

new_hash = hash_password('crubio2026')
print(f'Hash: {new_hash}')

# Update interventoria.users
conn = mysql.connector.connect(host='127.0.0.1', port=3307, user='root', password='postgres', database='interventoria')
cursor = conn.cursor()
cursor.execute("UPDATE users SET password = %s WHERE email = %s", (new_hash, 'crubio@mab.com.co'))
conn.commit()
print(f'interventoria users updated: {cursor.rowcount}')
cursor.close()
conn.close()

# Add crubio to apus_mab.users (since app queries this table)
conn2 = mysql.connector.connect(host='127.0.0.1', port=3307, user='root', password='postgres', database='apus_mab')
cursor2 = conn2.cursor()
cursor2.execute("SELECT id FROM users WHERE email = %s OR phone = %s", ('crubio@mab.com.co', 'crubio@mab.com.co'))
existing = cursor2.fetchone()
if existing:
    cursor2.execute("UPDATE users SET password = %s WHERE email = %s OR phone = %s", (new_hash, 'crubio@mab.com.co', 'crubio@mab.com.co'))
    print(f'apus_mab users updated: {cursor2.rowcount}')
else:
    cursor2.execute(
        "INSERT INTO users (name, cc, email, password, phone, position, proyecto) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        ('Cristian Rubio', '1064112177', 'crubio@mab.com.co', new_hash, 'crubio@mab.com.co', 'Topografo', 'LOCAL'),
    )
    print(f'apus_mab users inserted: {cursor2.rowcount}')
conn2.commit()
cursor2.close()
conn2.close()

print('Done!')