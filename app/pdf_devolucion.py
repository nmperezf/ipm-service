"""PDF de devolución al cliente: se genera cuando se cierra una visita.
Es un resumen ejecutivo (por categoría + deficiencias aprobadas de esa
visita puntual), no un volcado de cada equipo — ese detalle vive en los
reportes por categoría (ver pdf_reporte.py) y, más adelante, en el
portal del cliente."""

import base64
import io

from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

from app.pdf_base import INK_MUTED, construir, crear_documento, estilo_tabla_encabezado, estilos


def generar_pdf_devolucion(visita, resumen_categorias, deficiencias):
    buffer = io.BytesIO()
    doc = crear_documento(buffer)
    styles = estilos()
    titulo, subtitulo, h2, normal, celda = (
        styles["titulo"], styles["subtitulo"], styles["h2"], styles["normal"], styles["celda"],
    )

    instalacion = visita.instalacion
    elementos = []

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
        filas = [["Área", "Equipos revisados"]]
        for r in resumen_categorias:
            filas.append([r["categoria"], str(r["equipos_revisados"])])
        tabla_resumen = Table(filas, colWidths=[11.5 * cm, 5 * cm])
        tabla_resumen.setStyle(estilo_tabla_encabezado())
        elementos.append(tabla_resumen)
    else:
        elementos.append(Paragraph("Sin checklists de equipos cargados en esta visita.", normal))

    elementos.append(Paragraph("Deficiencias encontradas en esta visita", h2))
    if deficiencias:
        filas = [["Clasificación", "Equipo", "Descripción"]]
        for d in deficiencias:
            filas.append([
                Paragraph(d.clasificacion, celda),
                Paragraph(d.equipo.nombre if d.equipo else "-", celda),
                Paragraph(d.descripcion, celda),
            ])
        tabla_def = Table(filas, colWidths=[3.5 * cm, 3.5 * cm, 9.5 * cm])
        tabla_def.setStyle(estilo_tabla_encabezado())
        elementos.append(tabla_def)
    else:
        elementos.append(Paragraph("No se registraron deficiencias en esta visita.", normal))

    deficiencias_con_presupuesto = [d for d in deficiencias if d.requiere_presupuesto and d.presupuesto]
    if deficiencias_con_presupuesto:
        elementos.append(Paragraph("Deficiencias que requieren acción", h2))
        filas = [["Código", "Descripción", "Estado"]]
        for d in deficiencias_con_presupuesto:
            filas.append([d.presupuesto.codigo, Paragraph(d.descripcion, celda), d.presupuesto.estado])
        tabla_presupuestos = Table(filas, colWidths=[3.5 * cm, 10 * cm, 3 * cm])
        tabla_presupuestos.setStyle(estilo_tabla_encabezado())
        elementos.append(tabla_presupuestos)
        elementos.append(
            Paragraph(
                "Para solicitar el presupuesto formalmente, mencione el código correspondiente en un mail a "
                "presupuestos@andrewittenberger.com.uy",
                normal,
            )
        )

    elementos.append(Paragraph("Observaciones del técnico", h2))
    elementos.append(Paragraph(visita.notas_cierre or "-", normal))

    elementos.append(Spacer(1, 1.2 * cm))

    def _celda_firma(firma_b64):
        if not firma_b64:
            return "_______________________________"
        try:
            _, datos_b64 = firma_b64.split(",", 1)
            imagen_bytes = base64.b64decode(datos_b64)
            return Image(io.BytesIO(imagen_bytes), width=6 * cm, height=2.2 * cm)
        except Exception:
            return "_______________________________"

    celda_firma_tecnico = _celda_firma(visita.firma_tecnico)
    celda_firma_cliente = _celda_firma(visita.firma_cliente)

    firmas = Table(
        [[celda_firma_tecnico, celda_firma_cliente], ["Firma técnico", "Firma cliente / conformidad"]],
        colWidths=[8 * cm, 8 * cm],
    )
    firmas.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 1), (-1, 1), INK_MUTED),
                ("TOPPADDING", (0, 1), (-1, 1), 2),
            ]
        )
    )
    elementos.append(firmas)

    construir(doc, elementos, tipo_doc="Reporte de visita")
    return buffer.getvalue()
