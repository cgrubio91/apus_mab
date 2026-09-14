from src.infrastructure.database.connection import execute_query

r = execute_query("SELECT DISTINCT nombre_proyecto FROM apus WHERE nombre_proyecto IS NOT NULL ORDER BY nombre_proyecto LIMIT 20")
print("Unique projects (first 20):", r)

# Count total unique projects
r2 = execute_query("SELECT COUNT(DISTINCT nombre_proyecto) as total FROM apus WHERE nombre_proyecto IS NOT NULL")
print("Total unique projects:", r2)