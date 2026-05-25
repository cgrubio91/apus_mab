"""
🧪 APU Extractor Test Suite
Validates modules, extraction, formatting, and database service functions.
"""

import os
import sys
from dotenv import load_dotenv

# Ensure root directory is on PATH for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

# Import the module
try:
    import apu_extractor
    print("✅ Módulo 'apu_extractor' importado correctamente.")
except ImportError as err:
    print(f"❌ Error al importar 'apu_extractor': {err}")
    sys.exit(1)

def test_formatting():
    print("\n--- 🧪 PROBANDO FORMATEADORES ---")
    
    # Test number formatting
    test_numbers = [
        (1234567, "1.234.567"),
        (0.25, "0,25"),
        (2846877.012, "2.846.877,012"),
        ("12.500,50", "12.500,5"),  # Parses and formats
        ("$45,000.5", "45.000,5"),
        (None, "–"),
        ("–", "–")
    ]
    
    for val, expected in test_numbers:
        res = apu_extractor.format_latin_number(val)
        print(f"   format_latin_number({val}) -> '{res}' (Esperado: '{expected}')")
        
    # Test date formatting
    test_dates = [
        ("2026-05-25", "2026-05-25"),
        ("25/05/2026", "2026-05-25"),
        ("05-25-2026", "2026-05-25"),
        ("2026/05/25", "2026-05-25"),
        ("N/A", "–"),
        (None, "–")
    ]
    
    for val, expected in test_dates:
        res = apu_extractor.format_date(val)
        print(f"   format_date({val}) -> '{res}' (Esperado: '{expected}')")

def test_tsv_generation():
    print("\n--- 🧪 PROBANDO GENERACIÓN DE TABLA DE COPIADO ---")
    mock_insumos = [
        {
            "fecha_aprobacion_apu": "2026-05-25",
            "fecha_analisis_apu": "2026-05-20",
            "ciudad": "Bogotá",
            "pais": "Colombia",
            "entidad": "IDU",
            "contratista": "Consorcio Vial 2026",
            "nombre_proyecto": "Carrera 7 Reparación",
            "numero_contrato": "IDU-001",
            "item": "1.1",
            "items_descripcion": "Excavación de roca",
            "item_unidad": "M3",
            "precio_unitario": 85400.50,
            "precio_unitario_sin_aiu": 78000.00,
            "codigo_insumo": "EQ-003",
            "tipo_insumo": "Equipos",
            "insumo_descripcion": "Retroexcavadora",
            "insumo_unidad": "H-M",
            "rendimiento_insumo": 0.05,
            "precio_unitario_apu": 120000.00,
            "precio_parcial_apu": 6000.00,
            "observacion": "",
            "link_documento": "carrera7_apu.pdf"
        },
        {
            "fecha_aprobacion_apu": "2026-05-25",
            "fecha_analisis_apu": "2026-05-20",
            "ciudad": "Bogotá",
            "pais": "Colombia",
            "entidad": "IDU",
            "contratista": "Consorcio Vial 2026",
            "nombre_proyecto": "Carrera 7 Reparación",
            "numero_contrato": "IDU-001",
            "item": "1.1",
            "items_descripcion": "Excavación de roca",
            "item_unidad": "M3",
            "precio_unitario": 85400.50,
            "precio_unitario_sin_aiu": 78000.00,
            "codigo_insumo": "MAT-005",
            "tipo_insumo": "Materiales",
            "insumo_descripcion": "Piedra media",
            "insumo_unidad": "M3",
            "rendimiento_insumo": 1.10,
            "precio_unitario_apu": 45000.00,
            "precio_parcial_apu": 49500.00,
            "observacion": "Con acarreo",
            "link_documento": "carrera7_apu.pdf"
        }
    ]
    
    table_str = apu_extractor.generate_copy_paste_table(mock_insumos, include_proyecto_col=True)
    print("📋 Vista previa de la tabla tabulada (Google Sheets):")
    print("-" * 80)
    print(table_str)
    print("-" * 80)

def test_database_connection():
    print("\n--- 🧪 PROBANDO CONEXIÓN A BASE DE DATOS Y SERVICIOS ---")
    try:
        from db_config import test_connection
        db_res = test_connection()
        print(f"🔌 Conexión DB: {db_res['status']} ({db_res.get('message')})")
        
        if db_res['status'] == "success":
            projects = apu_extractor.get_unique_projects()
            print(f"📊 Proyectos únicos encontrados en DB: {len(projects)}")
            for idx, p in enumerate(projects[:5], 1):
                print(f"   {idx}. {p}")
            if len(projects) > 5:
                print("   ...")
                
            # Test getting APUs
            apus_res = apu_extractor.get_apus(limit=2)
            print(f"📊 Registros APUs totales en DB: {apus_res['total']}")
            print(f"   Registros obtenidos en prueba: {len(apus_res['data'])}")
    except Exception as e:
        print(f"⚠️ Error al conectar o consultar DB: {e}")

if __name__ == "__main__":
    print("🧪 INICIANDO PRUEBAS DE APU EXTRACTOR 🧪")
    test_formatting()
    test_tsv_generation()
    test_database_connection()
    print("\n✨ Pruebas finalizadas.")
