from src.infrastructure.database.connection import execute_query

r = execute_query("SELECT COUNT(*) as cnt FROM solicitudes_apu")
print("solicitudes_apu count:", r)

# Check if origen column exists and its values
try:
    r = execute_query("SELECT origen, COUNT(*) as cnt FROM solicitudes_apu GROUP BY origen")
    print("origen distribution:", r)
except Exception as e:
    print("Error:", e)