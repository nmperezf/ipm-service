"""Generación de PDF para Órdenes de Trabajo."""

import io

from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from app.pdf_base import BORDE, INK_MUTED, construir, crear_documento, estilo_tabla_encabezado, estilos


def generar_pdf_ot(ot):
    """Arma el PDF de una orden de trabajo y devuelve los bytes."""
    buffer = io.BytesIO()
    doc = crear_documento(buffer)
    styles = estilos()
    titulo, subtitulo, h2, normal = styles["titulo"], styles["subtitulo"], styles["h2"], styles["normal"]

    elementos = []

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
                ("TEXTCOLOR", (0, 0), (0, -1), INK_MUTED),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDE),
            ]
        )
    )
    elementos.append(tabla_datos)

    # OT ligada a una visita: la "descripción libre" de siempre se
    # reemplaza por la lista real de servicios contratados de esa visita
    # (mismo criterio que ordenes_trabajo/_detalle_fragment.html). Las
    # OT correctivas (sin visita) siguen con su descripción de texto.
    if ot.visita_id:
        elementos.append(Paragraph("Servicios contratados de esta visita", h2))
        filas = [["Servicio", "Completado"]]
        for item in ot.visita.items:
            filas.append([item.nombre_mostrado, "[ ] Sí   [ ] No"])
        if len(filas) == 1:
            filas.append(["Sin servicios cargados.", ""])
        tabla_servicios = Table(filas, colWidths=[11 * cm, 5 * cm])
        tabla_servicios.setStyle(estilo_tabla_encabezado())
        elementos.append(tabla_servicios)
    else:
        elementos.append(Paragraph("Descripción del trabajo", h2))
        elementos.append(Paragraph(ot.descripcion or "-", normal))

    # Repuestos utilizados
    if ot.repuestos_usados:
        elementos.append(Paragraph("Repuestos utilizados", h2))
        filas = [["Repuesto", "Cantidad"]]
        for uso in ot.repuestos_usados:
            filas.append([uso.repuesto.nombre, f"{uso.cantidad} {uso.repuesto.unidad}"])
        tabla_repuestos = Table(filas, colWidths=[11 * cm, 5 * cm])
        tabla_repuestos.setStyle(estilo_tabla_encabezado())
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
                ("TEXTCOLOR", (0, 1), (-1, 1), INK_MUTED),
                ("TOPPADDING", (0, 1), (-1, 1), 2),
            ]
        )
    )
    elementos.append(firmas)

    construir(doc, elementos, tipo_doc="Orden de trabajo", empresa=ot.instalacion.cliente.empresa)
    return buffer.getvalue()
