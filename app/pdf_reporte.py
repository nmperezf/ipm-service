"""Generación de PDF de reporte consolidado: una fila por equipo (BIE, ECA,
etc.), con el resultado de su checklist, para enviar al cliente."""

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from app.pdf_base import BORDE, INK, SURFACE_MUTED, construir, crear_documento, estilos


def _valor_texto(valor):
    if valor is None or valor == "":
        return "-"
    if isinstance(valor, list):
        return ", ".join(valor) if valor else "-"
    return str(valor)


def generar_pdf_reporte_equipos(item, tipo, formularios):
    """item: ItemVisita (el servicio/ronda de inspección).
    tipo: TipoFormulario (el checklist, ej. 'Checklist de BIE').
    formularios: lista de Formulario ya completados, uno por equipo."""
    buffer = io.BytesIO()
    doc = crear_documento(buffer, pagesize=landscape(A4), margen_izq=1.5 * cm, margen_der=1.5 * cm)
    styles = estilos()
    titulo, subtitulo = styles["titulo"], styles["subtitulo"]
    celda_texto = ParagraphStyle("Celda", parent=styles["normal"], fontSize=8, leading=10)

    instalacion = item.visita.instalacion
    elementos = []
    elementos.append(Paragraph(tipo.nombre, titulo))
    elementos.append(
        Paragraph(
            f"{instalacion.cliente.nombre} &middot; {instalacion.nombre} &middot; "
            f"Visita del {item.visita.fecha.strftime('%d/%m/%Y')}",
            subtitulo,
        )
    )
    elementos.append(Spacer(1, 0.5 * cm))

    campos = tipo.campos()
    encabezado = ["Equipo"] + [Paragraph(c["label"], celda_texto) for c in campos]
    filas = [encabezado]

    for formulario in formularios:
        datos = formulario.datos()
        fila = [Paragraph(formulario.equipo.nombre if formulario.equipo else "-", celda_texto)]
        for campo in campos:
            fila.append(Paragraph(_valor_texto(datos.get(campo["campo"])), celda_texto))
        filas.append(fila)

    if len(filas) == 1:
        elementos.append(Paragraph("Todavía no hay checklists completados para este reporte.", styles["normal"]))
    else:
        ancho_equipo = 3.5 * cm
        ancho_disponible = landscape(A4)[0] - 3 * cm - ancho_equipo
        ancho_columna = ancho_disponible / max(len(campos), 1)
        tabla = Table(filas, colWidths=[ancho_equipo] + [ancho_columna] * len(campos), repeatRows=1)
        tabla.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), SURFACE_MUTED),
                    ("TEXTCOLOR", (0, 0), (-1, 0), INK),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.4, BORDE),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFBFC")]),
                ]
            )
        )
        elementos.append(tabla)

    construir(doc, elementos, tipo_doc="Reporte de equipos")
    return buffer.getvalue()
