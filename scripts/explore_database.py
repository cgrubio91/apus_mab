"""
📋 Database Explorer Script
Interactive tool to explore PostgreSQL database tables and content
"""

from db_config import get_db_connection, execute_query
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime


def list_all_tables():
    """Lista todas las tablas en el esquema público."""
    query = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """
    
    try:
        tables = execute_query(query, dict_cursor=False)
        
        print("\n" + "="*60)
        print("📋 TABLAS EN LA BASE DE DATOS")
        print("="*60)
        
        if tables:
            for idx, (table_name,) in enumerate(tables, 1):
                print(f"{idx}. {table_name}")
            return [table[0] for table in tables]
        else:
            print("⚠️  No se encontraron tablas en el esquema 'public'.")
            return []
            
    except Exception as e:
        print(f"❌ Error al listar tablas: {e}")
        return []


def describe_table(table_name):
    """Muestra la estructura de una tabla específica."""
    query = """
        SELECT 
            column_name,
            data_type,
            character_maximum_length,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' 
        AND table_name = %s
        ORDER BY ordinal_position;
    """
    
    try:
        columns = execute_query(query, params=(table_name,), dict_cursor=False)
        
        print("\n" + "="*60)
        print(f"🔍 ESTRUCTURA DE LA TABLA: {table_name}")
        print("="*60)
        print(f"{'Columna':<25} {'Tipo':<20} {'Nullable':<10} {'Default'}")
        print("-"*60)
        
        for col_name, data_type, max_length, nullable, default in columns:
            type_str = data_type
            if max_length:
                type_str += f"({max_length})"
            default_str = str(default) if default else ""
            print(f"{col_name:<25} {type_str:<20} {nullable:<10} {default_str}")
            
    except Exception as e:
        print(f"❌ Error al describir tabla '{table_name}': {e}")


def query_table_content(table_name, limit=10):
    """Consulta y muestra el contenido de una tabla."""
    try:
        # Primero, obtener el conteo total
        count_query = f"SELECT COUNT(*) as total FROM {table_name};"
        count_result = execute_query(count_query, dict_cursor=True)
        total_rows = count_result[0]['total']
        
        # Luego, obtener los primeros registros
        query = f"SELECT * FROM {table_name} LIMIT %s;"
        rows = execute_query(query, params=(limit,), dict_cursor=True)
        
        print("\n" + "="*60)
        print(f"📊 CONTENIDO DE LA TABLA: {table_name}")
        print(f"Total de registros: {total_rows}")
        print(f"Mostrando los primeros {min(limit, total_rows)} registros")
        print("="*60)
        
        if rows:
            for idx, row in enumerate(rows, 1):
                print(f"\n--- Registro {idx} ---")
                for key, value in row.items():
                    print(f"  {key}: {value}")
        else:
            print("⚠️  La tabla está vacía.")
            
        return rows
            
    except Exception as e:
        print(f"❌ Error al consultar tabla '{table_name}': {e}")
        return []


def export_table_to_json(table_name, output_file=None):
    """Exporta el contenido completo de una tabla a JSON."""
    try:
        query = f"SELECT * FROM {table_name};"
        rows = execute_query(query, dict_cursor=True)
        
        # Convertir datetime y otros tipos no serializables
        def json_serial(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")
        
        if output_file is None:
            output_file = f"{table_name}_export.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(rows, f, indent=2, default=json_serial, ensure_ascii=False)
        
        print(f"✅ Tabla '{table_name}' exportada a '{output_file}' ({len(rows)} registros)")
        
    except Exception as e:
        print(f"❌ Error al exportar tabla '{table_name}': {e}")


def explore_all_tables(show_content=True, content_limit=5):
    """Explora todas las tablas de la base de datos."""
    print("\n" + "🔎 EXPLORACIÓN COMPLETA DE LA BASE DE DATOS".center(60, "="))
    
    # Listar todas las tablas
    tables = list_all_tables()
    
    if not tables:
        return
    
    # Para cada tabla, mostrar estructura y contenido
    for table_name in tables:
        describe_table(table_name)
        
        if show_content:
            query_table_content(table_name, limit=content_limit)
    
    print("\n" + "="*60)
    print("✨ Exploración completada")
    print("="*60)


def interactive_menu():
    """Menú interactivo para explorar la base de datos."""
    while True:
        print("\n" + "="*60)
        print("🗄️  EXPLORADOR DE BASE DE DATOS POSTGRESQL")
        print("="*60)
        print("1. Listar todas las tablas")
        print("2. Ver estructura de una tabla")
        print("3. Ver contenido de una tabla")
        print("4. Explorar toda la base de datos")
        print("5. Exportar tabla a JSON")
        print("0. Salir")
        print("="*60)
        
        choice = input("\nSelecciona una opción: ").strip()
        
        if choice == "1":
            list_all_tables()
            
        elif choice == "2":
            table_name = input("Nombre de la tabla: ").strip()
            if table_name:
                describe_table(table_name)
            
        elif choice == "3":
            table_name = input("Nombre de la tabla: ").strip()
            if table_name:
                try:
                    limit = int(input("¿Cuántos registros mostrar? (default 10): ").strip() or "10")
                except ValueError:
                    limit = 10
                query_table_content(table_name, limit=limit)
            
        elif choice == "4":
            try:
                limit = int(input("¿Cuántos registros mostrar por tabla? (default 5): ").strip() or "5")
            except ValueError:
                limit = 5
            explore_all_tables(show_content=True, content_limit=limit)
            
        elif choice == "5":
            table_name = input("Nombre de la tabla a exportar: ").strip()
            if table_name:
                output_file = input("Nombre del archivo (Enter para default): ").strip() or None
                export_table_to_json(table_name, output_file)
            
        elif choice == "0":
            print("\n👋 ¡Hasta pronto!")
            break
            
        else:
            print("⚠️  Opción no válida. Intenta de nuevo.")


if __name__ == "__main__":
    # Opción 1: Menú interactivo
    interactive_menu()
    
    # Opción 2: Exploración automática (comenta la línea anterior y descomenta esta)
    # explore_all_tables(show_content=True, content_limit=5)
