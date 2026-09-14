from src.infrastructure.database.connection import execute_query

# Check if records exist
r = execute_query("SELECT COUNT(*) as total FROM solicitudes_apu")
print("Total solicitudes_apu:", r)

# Check estructura
try:
    r = execute_query("DESCRIBE solicitudes_apu")
    print("Columnas:", [c['Field'] for c in r])
except Exception as e:
    print("Error describing:", e)

# Try selecting
try:
    r = execute_query("SELECT * FROM solicitudes_apu LIMIT 5")
    print("Muestra:", r)
except Exception as e:
    print("Error selecting:", e)

# Check origin column specifically
try:
    r = execute_query("SELECT origen FROM solicitudes_apu LIMIT 5")
    print("Origin values:", r)
except Exception as e:
    print("Error selecting origen:", e)