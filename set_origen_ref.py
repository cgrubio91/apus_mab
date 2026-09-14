from src.infrastructure.database.connection import execute_query
import logging

log = logging.getLogger("mapus.set_origen")

# Get all unique projects from APUs
r = execute_query("SELECT DISTINCT nombre_proyecto FROM apus WHERE nombre_proyecto IS NOT NULL ORDER BY nombre_proyecto")
projects = [p['nombre_proyecto'] for p in r]
print(f"Found {len(projects)} unique projects")

created = 0
skipped = 0

for proyecto in projects:
    # Check if a solicitud already exists for this project
    existing = execute_query(
        "SELECT id FROM solicitudes_apu WHERE nombre_proyecto = %s LIMIT 1",
        (proyecto,),
    )
    if existing:
        # Update existing to set origen = 'Referencia'
        execute_query(
            "UPDATE solicitudes_apu SET origen = 'Referencia' WHERE nombre_proyecto = %s",
            (proyecto,),
        )
        print(f"Updated existing solicitud for: {proyecto[:60]}...")
        skipped += 1
    else:
        # Create new solicitud with origen = 'Referencia'
        # Use the first APU's numero_contrato or a generic value as link_documento
        # Get a sample APU from this project to get contrato info
        sample_apu = execute_query(
            "SELECT numero_contrato FROM apus WHERE nombre_proyecto = %s LIMIT 1",
            (proyecto,),
        )
        contrato = sample_apu[0]['numero_contrato'] if sample_apu and sample_apu[0]['numero_contrato'] else f"REF-{proyecto[:30]}"
        
        query = (
            "INSERT INTO solicitudes_apu "
            "(link_documento, contratista, nombre_proyecto, fecha_solicitud, "
            "origen, descripcion_actividad, unidad_actividad, codigo_item, ciudad, estado) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        )
        params = (contrato[:100], "Importado", proyecto, None, "Referencia", proyecto, None, None, "Bogotá", "pendiente_analisis")
        
        execute_query(query, params)
        print(f"Created new solicitud with origen=Referencia for: {proyecto[:60]}...")
        created += 1

# Final verification
r = execute_query("SELECT origen, COUNT(*) as cnt FROM solicitudes_apu GROUP BY origen")
print("\nSolicitudes_apu origen distribution:")
for row in r:
    print(f"  {row['origen']}: {row['cnt']}")

r2 = execute_query("SELECT COUNT(*) as total FROM solicitudes_apu")
print(f"\nTotal solicitudes_apu: {r2[0]['total']}")