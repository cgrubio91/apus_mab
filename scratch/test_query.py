import sys
sys.path.insert(0, ".")
from src.infrastructure.database.connection import get_db_connection

with get_db_connection() as conn:
    with conn.cursor(dictionary=True) as c:
        c.execute("""
            SELECT codigo, descripcion, unidad, precio 
            FROM precio_referencia_externa 
            WHERE fuente = 'IDU' AND descripcion LIKE '%concreto%' AND descripcion LIKE '%3000%' 
            LIMIT 5
        """)
        for r in c.fetchall():
            print(f"[{r['codigo']}] {r['descripcion']} | {r['unidad']} | ${r['precio']:,.2f}")
