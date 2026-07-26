"""Generación de PDF para Órdenes de Trabajo."""

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

AZUL = colors.HexColor("#1B3A5C")
GRIS = colors.HexColor("#5B6673")
BORDE = colors.HexColor("#D9DEE3")


def generar_pdf_ot(ot):
    """Arma el PDF de una orden de trabajo y devuelve los bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
    )

    styles = getSampleStyleSheet()
    titulo = ParagraphStyle("Titulo", parent=styles["Title"], textColor=AZUL, fontSize=20, spaceAfter=2)
    subtitulo = ParagraphStyle("Subtitulo", parent=styles["Normal"], textColor=GRIS, fontSize=10)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=AZUL, fontSize=12, spaceBefore=14, spaceAfter=6)
    normal = styles["Normal"]

    elementos = []

    elementos.append(Paragraph("IPM Service", subtitulo))
    elementos.append(Paragraph(f"Orden de trabajo {ot.numero}", titulo))
    elementos.append(Paragraph(f"{ot.tipo} &middot; Prioridad {ot.prioridad} &middot; Estado {ot.estado}", subtitulo))
    elementos.append(Spacer(1, 0.6 * cm))

    datos_generales = [
        ["Cliente", ot.instalacion.cliente.nombre],
        ["Instalación", ot.instalacion.nombre],
        ["Dirección", ot.instalacion.direccion or "-"],
        ["Técnico asignado", ot.nombre_tecnico],
        ["Fecha de apertura", ot.fecha_apertura.strftime("%d/%m/%Y")],
        ["Fecha de cierre", ot.fecha_cierre.strftime("%d/%m/%Y") if ot.fecha_cierre else "-"],
    ]
    tabla_datos = Table(datos_generales, colWidths=[4.5 * cm, 11.5 * cm])
    tabla_datos.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (0, -1), GRIS),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDE),
            ]
        )
    )
    elementos.append(tabla_datos)

    elementos.append(Paragraph("Descripción del trabajo", h2))
    elementos.append(Paragraph(ot.descripcion or "-", normal))

    # Checklist de servicios, solo para OT preventivas ligadas a una visita
    if ot.visita and ot.visita.items:
        elementos.append(Paragraph("Servicios de esta visita", h2))
        filas = [["Servicio", "Completado"]]
        for item in ot.visita.items:
            filas.append([item.servicio.nombre, "[ ] Sí   [ ] No"])
        tabla_servicios = Table(filas, colWidths=[11 * cm, 5 * cm])
        tabla_servicios.setStyle(_estilo_tabla_con_encabezado())
        elementos.append(tabla_servicios)

    # Repuestos utilizados
    if ot.repuestos_usados:
        elementos.append(Paragraph("Repuestos utilizados", h2))
        filas = [["Repuesto", "Cantidad"]]
        for uso in ot.repuestos_usados:
            filas.append([uso.repuesto.nombre, f"{uso.cantidad} {uso.repuesto.unidad}"])
        tabla_repuestos = Table(filas, colWidths=[11 * cm, 5 * cm])
        tabla_repuestos.setStyle(_estilo_tabla_con_encabezado())
        elementos.append(tabla_repuestos)

    if ot.observaciones:
        elementos.append(Paragraph("Observaciones", h2))
        elementos.append(Paragraph(ot.observaciones, normal))

    # Espacio de firmas
    elementos.append(Spacer(1, 2.2 * cm))
    firmas = Table(
        [["_______________________________"], ["Firma técnico"]],
        colWidths=[16 * cm],
    )
    firmas.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 1), (-1, 1), GRIS),
                ("TOPPADDING", (0, 1), (-1, 1), 2),
            ]
        )
    )
    elementos.append(firmas)

    doc.build(elementos)
    return buffer.getvalue()


def _estilo_tabla_con_encabezado():
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F4F6F8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), AZUL),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDE),
        ]
    )
