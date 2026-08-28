"""PDF de la ficha de inspección de una BIE — "vista de captura limpia"
del mockup, misma estructura que pdf_devolucion.py."""

import io

from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from app.pdf_base import ACCENT_SOFT, INK_MUTED, construir, crear_documento, estilo_tabla_encabezado, estilos


def generar_pdf_ficha_bie(equipo, inspeccion):
    buffer = io.BytesIO()
    doc = crear_documento(buffer)
    styles = estilos()
    titulo, subtitulo, h2, normal, celda = (
        styles["titulo"], styles["subtitulo"], styles["h2"], styles["normal"], styles["celda"],
    )

    instalacion = equipo.instalacion
    elementos = []

    elementos.append(Paragraph(f"Inspección de BIE — {equipo.nombre}", titulo))
    elementos.append(
        Paragraph(
            f"{instalacion.cliente.nombre} &middot; {instalacion.nombre} &middot; "
            f"Inspección del {inspeccion.fecha.strftime('%d/%m/%Y')}",
            subtitulo,
        )
    )
    elementos.append(Spacer(1, 0.6 * cm))

    elementos.append(Paragraph("Especificaciones de la boca y puntero", h2))
    filas = [
        ["Campo", "Valor"],
        ["Tipo de boca", equipo.tipo_bie or "-"],
        ["Diámetro nominal", equipo.diametro_nominal or "-"],
        ["Tipo de puntero", equipo.tipo_puntero or "-"],
        [
            "Última prueba de la boca",
            f"{inspeccion.fecha_prueba_boca.strftime('%d/%m/%Y')} — {inspeccion.resultado_prueba_boca}"
            if inspeccion.fecha_prueba_boca else "-",
        ],
    ]
    tabla = Table(filas, colWidths=[6.4 * cm, 10.9 * cm])
    tabla.setStyle(estilo_tabla_encabezado())
    elementos.append(tabla)

    elementos.append(Paragraph("Compatibilidad y estado del gabinete", h2))
    filas = [
        ["Campo", "Valor"],
        ["Tipo de racor", equipo.tipo_racor or "-"],
        ["Estado del racor", equipo.estado_racor or "-"],
        ["Llave spanner", "Presente" if equipo.llave_spanner else "Falta"],
        ["Válvula de maniobra", "Operable" if equipo.valvula_operable else "Trabada"],
        ["Manómetro", f"{equipo.manometro_bar} bar" if equipo.manometro_bar is not None else "-"],
        ["Estado del gabinete", equipo.estado_gabinete or "-"],
    ]
    tabla = Table(filas, colWidths=[6.4 * cm, 10.9 * cm])
    tabla.setStyle(estilo_tabla_encabezado())
    elementos.append(tabla)

    manguera = next((m for m in equipo.mangueras if m.activa), None)
    elementos.append(Paragraph("Manguera asignada &amp; control hidrostático", h2))
    if manguera:
        filas = [
            ["Campo", "Valor"],
            ["N° de serie", manguera.numero_serie],
            ["Última prueba hidrostática", manguera.fecha_ultima_ph.strftime("%d/%m/%Y") if manguera.fecha_ultima_ph else "-"],
            ["Próximo vencimiento", manguera.fecha_vencimiento_ph.strftime("%d/%m/%Y") if manguera.fecha_vencimiento_ph else "-"],
        ]
        tabla = Table(filas, colWidths=[6.4 * cm, 10.9 * cm])
        tabla.setStyle(estilo_tabla_encabezado())
        elementos.append(tabla)
    else:
        elementos.append(Paragraph("Sin manguera asignada.", normal))

    elementos.append(Paragraph("Veredicto", h2))
    estilo_veredicto = TableStyle([("BACKGROUND", (0, 0), (-1, -1), ACCENT_SOFT)]) if inspeccion.veredicto != "Apta / operativa" else None
    tabla_veredicto = Table([[inspeccion.veredicto]], colWidths=[17.3 * cm])
    if estilo_veredicto:
        tabla_veredicto.setStyle(estilo_veredicto)
    elementos.append(tabla_veredicto)
    if inspeccion.dictamen:
        elementos.append(Paragraph(inspeccion.dictamen, normal))

    elementos.append(Spacer(1, 1.2 * cm))
    firmas = Table(
        [["_______________________________", "_______________________________"],
         ["Firma inspector técnico", "Firma conformidad cliente"]],
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

    construir(doc, elementos, tipo_doc="Inspección BIE", empresa=instalacion.cliente.empresa)
    return buffer.getvalue()
