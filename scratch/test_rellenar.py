import sys
import os

# Add repo root to sys.path
sys.path.insert(0, r"c:\Users\cgrub\OneDrive\Documents\apus_mab")

from src.application.use_cases.constructor_apu import _rellenar_precios_reales

propuesta_test = {
    "insumos": [
        {"tipo_insumo": "Materiales", "descripcion": "Concreto 3000 PSI", "unidad": "m3", "rendimiento": 1.05, "precio": None, "fuente": "Sin referencia disponible"},
        {"tipo_insumo": "Materiales", "descripcion": "Acero de refuerzo figurado y colocado", "unidad": "kg", "rendimiento": 120, "precio": None, "fuente": "Sin referencia disponible"},
        {"tipo_insumo": "Materiales", "descripcion": "Madera para encofrado (tablas, listones)", "unidad": "pie2", "rendimiento": 5, "precio": None, "fuente": "Sin referencia disponible"},
        {"tipo_insumo": "Mano de obra", "descripcion": "Cuadrilla de construcción (Oficial + Ayudante)", "unidad": "h", "rendimiento": 8, "precio": None, "fuente": "Sin referencia disponible"},
        {"tipo_insumo": "Equipos", "descripcion": "Vibrador de concreto", "unidad": "h", "rendimiento": 1, "precio": 11000.0, "fuente": "Banco: REFERENCIA · INVIAS"},
        {"tipo_insumo": "Herramienta", "descripcion": "Herramienta menor", "unidad": "%", "rendimiento": 0.1, "precio": 48230.0, "fuente": "Banco: REFERENCIA · INVIAS"},
        {"tipo_insumo": "Indirectos", "descripcion": "Administración", "unidad": "%", "rendimiento": 0.2, "precio": 104551.0, "fuente": "Banco: REFERENCIA · INVIAS"}
    ]
}

print("=== EJECUTANDO _rellenar_precios_reales ===")
resultado = _rellenar_precios_reales(propuesta_test, ciudad="Bogota")
for ins in resultado["insumos"]:
    print(f"{ins['tipo_insumo']} | {ins['descripcion']} | {ins['unidad']} | PRECIO: ${ins['precio']:,.2f} | FUENTE: {ins['fuente']}")
