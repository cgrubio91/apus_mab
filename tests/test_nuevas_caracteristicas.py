"""
Pruebas unitarias para las nuevas características implementadas:
1. Generador de Memoria Justificativa en PDF (reportlab).
2. Generador de APU en Excel con fórmulas vivas (openpyxl).
3. Cálculo paramétrico de cascada de A.I.U.
"""

import io
import pytest
import openpyxl
from src.infrastructure.reporting.memoria_pdf import generar_memoria_pdf
from src.infrastructure.reporting.apu_excel_formulado import generar_apu_excel_formulado
from src.application.use_cases.constructor_apu import calcular_desglose_aiu


def test_calcular_desglose_aiu_defaults():
    costo_directo = 100000.0
    desglose = calcular_desglose_aiu(costo_directo, proyecto_id=None)

    assert desglose["costo_directo"] == 100000.0
    # Defaults: adm 15%, imp 3%, ut 5%, iva 19%
    assert desglose["porcentajes"]["administracion"] == 15.0
    assert desglose["valores"]["administracion"] == 15000.0

    assert desglose["porcentajes"]["imprevistos"] == 3.0
    assert desglose["valores"]["imprevistos"] == 3000.0

    assert desglose["porcentajes"]["utilidad"] == 5.0
    assert desglose["valores"]["utilidad"] == 5000.0

    # IVA 19% sobre Utilidad: 5000 * 0.19 = 950
    assert desglose["porcentajes"]["iva_utilidad"] == 19.0
    assert desglose["valores"]["iva_utilidad"] == 950.0

    # Subtotal AIU: 15000 + 3000 + 5000 + 950 = 23950
    assert desglose["subtotal_aiu"] == 23950.0
    # Total: 100000 + 23950 = 123950
    assert desglose["costo_total"] == 123950.0


def test_generar_memoria_pdf():
    solicitud = {
        "id": 99,
        "descripcion": "Construcción de bordillo en concreto 2500 PSI",
        "unidad": "m",
        "rendimiento": 12.5,
        "tipo_obra": "Vial / Urbanismo",
        "ciudad": "Bogotá",
        "justificacion_tecnica": "Requerido por modificación en trazado geométrico según acta de vecindad.",
        "localizacion_obra": "K0+500 al K1+200 Calzada Izquierda",
        "numero_acta_aprobacion": "ACTA-INT-042",
        "fecha_aprobacion_entidad": "2026-09-03",
        "estado_incorporacion": "aprobado_entidad",
        "insumos": [
            {
                "tipo": "material",
                "descripcion": "Concreto 2500 PSI premezclado",
                "unidad": "m3",
                "cantidad": 0.08,
                "precio_unitario": 380000,
                "subtotal": 30400,
                "fuente": "CYPE Colombia 2026"
            },
            {
                "tipo": "mano_obra",
                "descripcion": "Oficial de albañilería + 2 ayudantes",
                "unidad": "d",
                "cantidad": 0.08,
                "precio_unitario": 185000,
                "subtotal": 14800,
                "fuente": "SECOP II Contrato 2025-104"
            }
        ]
    }

    desglose_aiu = {
        "costo_directo": 45200.0,
        "porcentajes": {"administracion": 15.0, "imprevistos": 3.0, "utilidad": 5.0, "iva_utilidad": 19.0},
        "valores": {"administracion": 6780.0, "imprevistos": 1356.0, "utilidad": 2260.0, "iva_utilidad": 429.4},
        "subtotal_aiu": 10825.4,
        "costo_total": 56025.4
    }

    pdf_bytes = generar_memoria_pdf(
        solicitud=solicitud,
        desglose_aiu=desglose_aiu,
        proyecto={"nombre": "Corredor Vial del Norte", "entidad": "IDU"}
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")


def test_generar_excel_apu_formulado():
    solicitud = {
        "id": 101,
        "descripcion": "Excavación manual en zanja h=1.5m",
        "unidad": "m3",
        "rendimiento": 2.5,
        "tipo_obra": "Alcantarillado",
        "ciudad": "Medellín",
        "insumos": [
            {
                "tipo": "mano_obra",
                "descripcion": "Cuadrilla excavación (1 Ayudante)",
                "unidad": "d",
                "cantidad": 0.4,
                "precio_unitario": 95000,
                "subtotal": 38000,
                "fuente": "SECOP II"
            },
            {
                "tipo": "herramienta",
                "descripcion": "Herramienta menor (% MO)",
                "unidad": "%",
                "cantidad": 5.0,
                "precio_unitario": 380,
                "subtotal": 1900,
                "fuente": "Calculado"
            }
        ]
    }

    desglose_aiu = {
        "costo_directo": 39900.0,
        "porcentajes": {"administracion": 12.0, "imprevistos": 2.0, "utilidad": 4.0, "iva_utilidad": 19.0},
        "valores": {"administracion": 4788.0, "imprevistos": 798.0, "utilidad": 1596.0, "iva_utilidad": 303.24},
        "subtotal_aiu": 7485.24,
        "costo_total": 47385.24
    }

    xlsx_bytes = generar_apu_excel_formulado(
        solicitud=solicitud,
        desglose_aiu=desglose_aiu,
        proyecto={"nombre": "Optimización Red Hidráulica", "entidad": "EPM"}
    )

    assert isinstance(xlsx_bytes, bytes)
    assert len(xlsx_bytes) > 2000

    # Validar que es un Excel válido que openpyxl puede cargar
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=False)
    sheet = wb.active

    # Buscar si contiene fórmulas
    formulas = []
    for row in sheet.iter_rows(values_only=False):
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("="):
                formulas.append(cell.value)

    assert len(formulas) > 0, "El archivo debe contener fórmulas dinámicas"
    # Debe haber fórmulas de multiplicación y de suma
    assert any("*" in f for f in formulas), "Debe haber fórmulas de multiplicación"
    assert any("SUM(" in f for f in formulas), "Debe haber fórmulas de SUM(...)"
