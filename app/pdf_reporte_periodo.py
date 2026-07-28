"""PDF de cumplimiento por período para un cliente (pensado para 6 meses,
pero acepta cualquier rango): servicios ejecutados en el período y estado
de las deficiencias, encontradas en el período y las que siguen abiertas
hoy. Es un resumen fáctico — no declara "conforme/no conforme": ese
juicio queda para quien lo lee, no para un veredicto automático (mismo
criterio que ya usamos en la curva de caudal)."""

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

AZUL = colors.HexColor("#1B3A5C")
GRIS = colors.HexColor("#5B6673")
BORDE = colors.HexColor("#D9DEE3")
ROJO_SUAVE = colors.HexColor("#FBEAE7")
ROJO = colors.HexColor("#B3261E")


def generar_pdf_reporte_periodo(cliente, fecha_desde, fecha_hasta, resumen_servicios, deficiencias_periodo, deficiencias_abiertas):
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

    elementos = []
    elementos.append(Paragraph("IPM Service", subtitulo))
    elementos.append(Paragraph("Reporte de cumplimiento", titulo))
    elementos.append(
        Paragraph(
            f"{cliente.nombre} &middot; Período {fecha_desde.strftime('%d/%m/%Y')} a {fecha_hasta.strftime('%d/%m/%Y')}",
            subtitulo,
        )
    )
    elementos.append(Spacer(1, 0.6 * cm))

    elementos.append(Paragraph("Servicios ejecutados en el período", h2))
    if resumen_servicios:
        filas = [["Instalación", "Total", "Cumplidos", "Pendientes", "Cancelados", "% cumplimiento"]]
        for r in resumen_servicios:
            filas.append([
                Paragraph(r["instalacion"], celda), str(r["total"]), str(r["cumplidos"]),
                str(r["pendientes"]), str(r["cancelados"]), f"{r['pct']}%",
            ])
        tabla = Table(filas, colWidths=[6.5 * cm, 1.7 * cm, 2 * cm, 2 * cm, 2 * cm, 2.3 * cm])
        tabla.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F4F6F8")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), AZUL),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.4, BORDE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        elementos.append(tabla)
    else:
        elementos.append(Paragraph("No hubo visitas planificadas en este período.", normal))

    elementos.append(Paragraph("Deficiencias encontradas en el período", h2))
    if deficiencias_periodo:
        filas = [["Fecha", "Instalación", "Clasificación", "Estado", "Descripción"]]
        estilos_fila = []
        for i, o in enumerate(deficiencias_periodo, start=1):
            estado = "Resuelta" if o.resuelto else ("Aprobada" if o.estado_revision == "Aprobada" else "Pendiente de revisión")
            filas.append([
                o.fecha_carga.strftime("%d/%m/%Y"), Paragraph(o.instalacion.nombre, celda),
                Paragraph(o.clasificacion, celda), estado, Paragraph(o.descripcion, celda),
            ])
            if o.clasificacion == "Deficiencia crítica":
                estilos_fila.append(("BACKGROUND", (0, i), (-1, i), ROJO_SUAVE))
        tabla = Table(filas, colWidths=[2.2 * cm, 3.3 * cm, 3 * cm, 2.8 * cm, 5.2 * cm])
        tabla.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F4F6F8")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), AZUL),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("GRID", (0, 0), (-1, -1), 0.4, BORDE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    *estilos_fila,
                ]
            )
        )
        elementos.append(tabla)
    else:
        elementos.append(Paragraph("No se registraron deficiencias nuevas en este período.", normal))

    elementos.append(Paragraph("Deficiencias abiertas hoy (todas las pendientes, no solo las del período)", h2))
    if deficiencias_abiertas:
        elementos.append(
            Paragraph("Las críticas se listan primero, resaltadas; dentro de cada grupo, de más a menos antigua.", subtitulo)
        )
        elementos.append(Spacer(1, 0.15 * cm))
        filas = [["Instalación", "Clasificación", "Antigüedad", "Fecha de carga", "Descripción"]]
        estilos_fila = []
        for i, o in enumerate(deficiencias_abiertas, start=1):
            filas.append([
                Paragraph(o.instalacion.nombre, celda), Paragraph(o.clasificacion, celda),
                f"{o.dias_abierta} día(s)", o.fecha_carga.strftime("%d/%m/%Y"), Paragraph(o.descripcion, celda),
            ])
            if o.clasificacion == "Deficiencia crítica":
                estilos_fila.append(("BACKGROUND", (0, i), (-1, i), ROJO_SUAVE))
                estilos_fila.append(("TEXTCOLOR", (2, i), (2, i), ROJO))
                estilos_fila.append(("FONTNAME", (2, i), (2, i), "Helvetica-Bold"))
        tabla = Table(filas, colWidths=[3.3 * cm, 3 * cm, 2.3 * cm, 2.7 * cm, 5.2 * cm])
        tabla.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F4F6F8")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), AZUL),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("GRID", (0, 0), (-1, -1), 0.4, BORDE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    *estilos_fila,
                ]
            )
        )
        elementos.append(tabla)
    else:
        elementos.append(Paragraph("No hay deficiencias abiertas para este cliente.", normal))

    doc.build(elementos)
    return buffer.getvalue()
