"""
Infrastructure: Generador de Memoria Técnica Justificativa de Ítem No Previsto en PDF
Formato oficial institucional con desglose de insumos, A.I.U. y cuadro de firmas.
"""

import io
from datetime import date
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def generar_memoria_pdf(solicitud: dict, desglose_aiu: dict, proyecto: Optional[dict] = None) -> bytes:
    """Genera el documento PDF formal de la Memoria Justificativa de Ítem No Previsto."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    primary_color = colors.HexColor("#1e3a8a")
    secondary_color = colors.HexColor("#334155")
    bg_header = colors.HexColor("#f1f5f9")
    border_color = colors.HexColor("#cbd5e1")

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=primary_color,
        alignment=1,  # Center
    )
    subtitle_style = ParagraphStyle(
        "DocSubTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=secondary_color,
        alignment=1,
    )
    section_style = ParagraphStyle(
        "SectionHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=colors.white,
    )
    body_style = ParagraphStyle(
        "BodyTextCustom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#1e293b"),
    )
    body_bold = ParagraphStyle(
        "BodyBoldCustom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#1e293b"),
    )
    cell_right = ParagraphStyle(
        "CellRight",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        alignment=2,
    )
    cell_right_bold = ParagraphStyle(
        "CellRightBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        alignment=2,
    )

    elements = []

    # ── ENCABEZADO INSTITUCIONAL ──
    elements.append(Paragraph("SISTEMA DE GESTIÓN Y AUDITORÍA DE PRECIOS UNITARIOS — MAPUS", title_style))
    elements.append(Paragraph("MEMORIA TÉCNICA JUSTIFICATIVA DE ÍTEM NO PREVISTO (APU)", subtitle_style))
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceAfter=8))

    # ── TABLA DE DATOS GENERALES ──
    nombre_proy = (proyecto.get("descripcion") if proyecto else None) or solicitud.get("nombre_proyecto") or "Proyecto de Obra Civil"
    codigo_item = solicitud.get("codigo_item") or f"NPC-{solicitud.get('id', '')}"
    actividad = solicitud.get("descripcion_actividad") or "Ítem no previsto"
    unidad = solicitud.get("unidad_actividad") or "und"
    ciudad = solicitud.get("ciudad") or "Colombia"
    fecha_entidad = str(solicitud.get("fecha_aprobacion_entidad") or date.today().isoformat())
    acta = solicitud.get("numero_acta_aprobacion") or "Pendiente de radicación"
    localizacion = solicitud.get("localizacion_obra") or "Según abscisado y planos de obra"

    datos_generales = [
        [Paragraph("<b>PROYECTO:</b>", body_style), Paragraph(nombre_proy, body_style),
         Paragraph("<b>SOLICITUD #:</b>", body_style), Paragraph(str(solicitud.get("id", "")), body_bold)],
        [Paragraph("<b>ÍTEM / CÓDIGO:</b>", body_style), Paragraph(f"<b>{codigo_item}</b> — {actividad}", body_style),
         Paragraph("<b>UNIDAD:</b>", body_style), Paragraph(unidad, body_bold)],
        [Paragraph("<b>CIUDAD / ZONA:</b>", body_style), Paragraph(ciudad, body_style),
         Paragraph("<b>LOCALIZACIÓN:</b>", body_style), Paragraph(localizacion, body_style)],
        [Paragraph("<b>ACTA / OFICIO:</b>", body_style), Paragraph(acta, body_style),
         Paragraph("<b>FECHA:</b>", body_style), Paragraph(fecha_entidad, body_style)],
    ]

    t_gen = Table(datos_generales, colWidths=[80, 240, 75, 145])
    t_gen.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg_header),
        ("BOX", (0, 0), (-1, -1), 0.5, border_color),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, border_color),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(t_gen)
    elements.append(Spacer(1, 10))

    # ── JUSTIFICACIÓN TÉCNICA ──
    justificacion = solicitud.get("justificacion_tecnica") or (
        f"Durante la ejecución de las obras surgió la necesidad técnica imperiosa de ejecutar la actividad "
        f"'{actividad}', requerida para garantizar la estabilidad, funcionalidad y continuidad del proyecto. "
        f"El presente Análisis de Precios Unitarios fue estructurado por la Interventoría, analizando rendimientos "
        f"de cuadrillas y cotizaciones de mercado, y cuenta con la aprobación correspondiente."
    )
    t_just_title = Table([[Paragraph("1. JUSTIFICACIÓN TÉCNICA DE LA NECESIDAD EN OBRA", section_style)]], colWidths=[540])
    t_just_title.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), primary_color),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(t_just_title)

    t_just_content = Table([[Paragraph(justificacion, body_style)]], colWidths=[540])
    t_just_content.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, border_color),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(t_just_content)
    elements.append(Spacer(1, 10))

    # ── MATRIZ DETALLADA DE INSUMOS ──
    t_ins_title = Table([[Paragraph("2. MATRIZ DE ANÁLISIS DE PRECIOS UNITARIOS (COSTO DIRECTO)", section_style)]], colWidths=[540])
    t_ins_title.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), primary_color),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(t_ins_title)

    insumos = solicitud.get("insumos") or []
    tabla_insumos_data = [
        [
            Paragraph("<b>Tipo</b>", body_bold),
            Paragraph("<b>Descripción del Insumo</b>", body_bold),
            Paragraph("<b>Und</b>", body_bold),
            Paragraph("<b>Rend.</b>", cell_right_bold),
            Paragraph("<b>Precio Unit. ($)</b>", cell_right_bold),
            Paragraph("<b>Parcial ($)</b>", cell_right_bold),
        ]
    ]

    for ins in insumos:
        p_u = float(ins.get("precio_unitario_apu") or ins.get("precio_banco") or 0)
        rend = float(ins.get("rendimiento_insumo") or 1)
        parcial = p_u * rend
        tipo = (ins.get("tipo_insumo") or "Materiales")[:12]
        desc = ins.get("insumo_descripcion") or "Insumo"
        und = ins.get("insumo_unidad") or "und"

        tabla_insumos_data.append([
            Paragraph(tipo, body_style),
            Paragraph(desc, body_style),
            Paragraph(und, body_style),
            Paragraph(f"{rend:,.3f}", cell_right),
            Paragraph(f"${p_u:,.2f}", cell_right),
            Paragraph(f"${parcial:,.2f}", cell_right),
        ])

    cd = desglose_aiu.get("costo_directo") or 0.0
    tabla_insumos_data.append([
        Paragraph("<b>TOTAL COSTO DIRECTO</b>", body_bold),
        "", "", "", "",
        Paragraph(f"<b>${cd:,.2f}</b>", cell_right_bold),
    ])

    t_ins = Table(tabla_insumos_data, colWidths=[65, 235, 35, 55, 75, 75])
    t_ins.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), bg_header),
        ("BOX", (0, 0), (-1, -1), 0.5, border_color),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, border_color),
        ("SPAN", (0, -1), (4, -1)),
        ("BACKGROUND", (0, -1), (-1, -1), bg_header),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(t_ins)
    elements.append(Spacer(1, 10))

    # ── DESGLOSE DE A.I.U. ──
    t_aiu_title = Table([[Paragraph("3. DESGLOSE DE FACTORES DE A.I.U. (COSTO INDIRECTO)", section_style)]], colWidths=[540])
    t_aiu_title.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), primary_color),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(t_aiu_title)

    pcts = desglose_aiu.get("porcentajes") or {}
    vals = desglose_aiu.get("valores") or {}

    p_a = pcts.get("administracion", 15.0)
    p_i = pcts.get("imprevistos", 3.0)
    p_u = pcts.get("utilidad", 5.0)
    p_iva = pcts.get("iva_utilidad", 19.0)

    v_a = vals.get("administracion", 0.0)
    v_i = vals.get("imprevistos", 0.0)
    v_u = vals.get("utilidad", 0.0)
    v_iva = vals.get("iva_utilidad", 0.0)
    total_aiu = vals.get("total_aiu", 0.0)
    total_apu = vals.get("costo_total", 0.0)

    tabla_aiu_data = [
        [Paragraph("<b>Concepto</b>", body_bold), Paragraph("<b>Base de Cálculo</b>", body_bold),
         Paragraph("<b>Porcentaje (%)</b>", cell_right_bold), Paragraph("<b>Valor ($ COP)</b>", cell_right_bold)],
        [Paragraph("Administración (A)", body_style), Paragraph("Costo Directo", body_style),
         Paragraph(f"{p_a:.2f}%", cell_right), Paragraph(f"${v_a:,.2f}", cell_right)],
        [Paragraph("Imprevistos (I)", body_style), Paragraph("Costo Directo", body_style),
         Paragraph(f"{p_i:.2f}%", cell_right), Paragraph(f"${v_i:,.2f}", cell_right)],
        [Paragraph("Utilidad (U)", body_style), Paragraph("Costo Directo", body_style),
         Paragraph(f"{p_u:.2f}%", cell_right), Paragraph(f"${v_u:,.2f}", cell_right)],
        [Paragraph("IVA sobre Utilidad", body_style), Paragraph("Valor de la Utilidad (U)", body_style),
         Paragraph(f"{p_iva:.2f}%", cell_right), Paragraph(f"${v_iva:,.2f}", cell_right)],
        [Paragraph("<b>TOTAL A.I.U.</b>", body_bold), "",
         Paragraph(f"<b>{pcts.get('aiu_total_porcentaje', 0):.2f}%</b>", cell_right_bold),
         Paragraph(f"<b>${total_aiu:,.2f}</b>", cell_right_bold)],
        [Paragraph("<b>PRECIO UNITARIO TOTAL (COSTO DIRECTO + A.I.U.)</b>", body_bold), "", "",
         Paragraph(f"<b>${total_apu:,.2f}</b>", cell_right_bold)],
    ]

    t_aiu = Table(tabla_aiu_data, colWidths=[180, 140, 100, 120])
    t_aiu.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), bg_header),
        ("BOX", (0, 0), (-1, -1), 0.5, border_color),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, border_color),
        ("SPAN", (0, 5), (1, 5)),
        ("BACKGROUND", (0, 5), (-1, 5), bg_header),
        ("SPAN", (0, 6), (2, 6)),
        ("BACKGROUND", (0, 6), (-1, 6), colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(t_aiu)
    elements.append(Spacer(1, 15))

    # ── BLOQUE DE FIRMAS FORMALES ──
    firmas_data = [
        [
            Paragraph("<b>ELABORÓ:</b><br/><br/><br/><br/>_______________________________<br/><b>Residente Técnico de Interventoría</b><br/>Mat. Prof.: ____________________", body_style),
            Paragraph("<b>REVISÓ Y APROBÓ:</b><br/><br/><br/><br/>_______________________________<br/><b>Director de Interventoría</b><br/>Mat. Prof.: ____________________", body_style),
            Paragraph("<b>VISTO BUENO:</b><br/><br/><br/><br/>_______________________________<br/><b>Supervisor / Delegado de la Entidad</b><br/>IDU / Invías / Entidad Contratante", body_style),
        ]
    ]
    t_firmas = Table(firmas_data, colWidths=[180, 180, 180])
    t_firmas.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, border_color),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))

    elements.append(KeepTogether([
        Paragraph("4. CONTROL DE APROBACIONES Y RESPONSABILIDADES", subtitle_style),
        Spacer(1, 4),
        t_firmas,
    ]))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
