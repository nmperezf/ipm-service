"""PDF de devolución al cliente: se genera cuando se cierra una visita.
Es un resumen ejecutivo (por categoría + deficiencias aprobadas de esa
visita puntual), no un volcado de cada equipo — ese detalle vive en los
reportes por categoría (ver pdf_reporte.py) y, más adelante, en el
portal del cliente."""

import base64
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

AZUL = colors.HexColor("#1B3A5C")
GRIS = colors.HexColor("#5B6673")
BORDE = colors.HexColor("#D9DEE3")


def generar_pdf_devolucion(visita, resumen_categorias, deficiencias):
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
    celda = ParagraphStyle("Celda", parent=styles["Normal"], fontSize=9, leading=12)

    instalacion = visita.instalacion
    elementos = []

    elementos.append(Paragraph("IPM Service", subtitulo))
    elementos.append(Paragraph("Reporte de visita", titulo))
    elementos.append(
        Paragraph(
            f"{instalacion.cliente.nombre} &middot; {instalacion.nombre} &middot; "
            f"Visita del {visita.fecha.strftime('%d/%m/%Y')} &middot; "
            f"Cerrada el {visita.fecha_cierre.strftime('%d/%m/%Y') if visita.fecha_cierre else '-'}",
            subtitulo,
        )
    )
    elementos.append(Spacer(1, 0.6 * cm))

    elementos.append(Paragraph("Resumen del servicio", h2))
    if resumen_categorias:
        filas = [["Área", "Equipos / formularios revisados"]]
        for r in resumen_categorias:
            filas.append([r["categoria"], str(r["equipos_revisados"])])
        tabla_resumen = Table(filas, colWidths=[10 * cm, 6.5 * cm])
        tabla_resumen.setStyle(
            TableStyle(
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
        )
        elementos.append(tabla_resumen)
    else:
        elementos.append(Paragraph("Sin checklists de equipos cargados en esta visita.", normal))

    elementos.append(Paragraph("Deficiencias encontradas en esta visita", h2))
    if deficiencias:
        filas = [["Clasificación", "Descripción"]]
        for d in deficiencias:
            filas.append([Paragraph(d.clasificacion, celda), Paragraph(d.descripcion, celda)])
        tabla_def = Table(filas, colWidths=[4 * cm, 12.5 * cm])
        tabla_def.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F4F6F8")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), AZUL),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9.5),
                    ("GRID", (0, 0), (-1, -1), 0.4, BORDE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        elementos.append(tabla_def)
    else:
        elementos.append(Paragraph("No se registraron deficiencias en esta visita.", normal))

    elementos.append(Paragraph("Observaciones del técnico", h2))
    elementos.append(Paragraph(visita.notas_cierre or "-", normal))

    elementos.append(Spacer(1, 1.2 * cm))
    celda_firma_cliente = "_______________________________"
    if visita.firma_cliente:
        try:
            _, datos_b64 = visita.firma_cliente.split(",", 1)
            imagen_bytes = base64.b64decode(datos_b64)
            celda_firma_cliente = Image(io.BytesIO(imagen_bytes), width=6 * cm, height=2.2 * cm)
        except Exception:
            celda_firma_cliente = "_______________________________"

    firmas = Table(
        [["_______________________________", celda_firma_cliente], ["Firma técnico", "Firma cliente / conformidad"]],
        colWidths=[8 * cm, 8 * cm],
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
