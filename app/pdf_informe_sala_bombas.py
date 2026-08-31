"""PDF del informe oficial combinado de una categoría de equipo (hoy:
Sala de bombas) -- junta los checklists ya cargados vía
formularios.checklist_categoria (ver _secciones_categoria), el ensayo de
curva de caudal más reciente de cada bomba principal/respaldo y las
observaciones, en un solo documento con número propio y dos firmas. No
duplica esos datos, solo les agrega numeración y un dictamen final (ver
app.utils.obtener_o_crear_informe) -- el generador acá abajo solo
renderiza, no hace queries."""

import base64
import io

from reportlab.lib.units import cm
from reportlab.platypus import Flowable, Image, KeepTogether, Paragraph, Spacer, Table, TableStyle

from app.pdf_base import ACCENT, BORDE, BORDE_FUERTE, SLATE, SLATE_SOFT, construir, crear_documento, estilos
from app.pdf_checklist_tecnico import _fila_valores

ANCHO_CONTENIDO = 18 * cm

INK_FAINT_HEX = "#9AA1AC"
INK_MUTED_HEX = "#5B6773"

COLOR_ESTADO_HEX = {
    "Conforme": "#16A34A",
    "Observado": "#B45309",
    "Deficiencia": "#EA580C",
    "N/A": "#9AA1AC",
}


class _RotuloSeccion(Flowable):
    """Tick de color + rótulo en mayúsculas + filete fino -- mismo lenguaje
    que pdf_curva_caudal._RotuloSeccion (duplicado a propósito: son
    generadores independientes y ya quedó ajustado para esta hoja)."""

    ALTO = 0.55 * cm

    def __init__(self, texto, veredicto=False):
        Flowable.__init__(self)
        self.texto = texto.upper()
        self.color = ACCENT if veredicto else SLATE
        self.width = ANCHO_CONTENIDO
        self.height = self.ALTO

    def draw(self):
        c = self.canv
        c.saveState()
        tick_w, tick_h = 0.09 * cm, 0.34 * cm
        c.setFillColor(self.color)
        c.rect(0, (self.ALTO - tick_h) / 2, tick_w, tick_h, stroke=0, fill=1)

        c.setFont("Helvetica-Bold", 9.5)
        c.setFillColor(self.color)
        texto_x = tick_w + 0.2 * cm
        c.drawString(texto_x, (self.ALTO - 7) / 2, self.texto)

        linea_x = texto_x + c.stringWidth(self.texto, "Helvetica-Bold", 9.5) + 0.25 * cm
        c.setStrokeColor(BORDE)
        c.setLineWidth(0.6)
        c.line(linea_x, self.ALTO / 2, self.width, self.ALTO / 2)
        c.restoreState()


def generar_pdf_informe_categoria(item, categoria, secciones, ensayos, observaciones, informe):
    """item: ItemVisita. secciones: de formularios._secciones_categoria.
    ensayos: {Equipo: EnsayoCaudal más reciente} para las bombas
    principal/respaldo de esta categoría. observaciones: lista ya
    filtrada (aprobadas, no internas). informe: InformeGenerado (número +
    dictamen, ya creado/reutilizado por el caller)."""
    visita = item.visita
    instalacion = visita.instalacion

    buffer = io.BytesIO()
    doc = crear_documento(buffer)
    styles = estilos()
    titulo, normal, celda = styles["titulo"], styles["normal"], styles["celda"]

    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors as rl_colors

    celda_der = ParagraphStyle("CeldaDer", parent=celda, alignment=2)
    celda_encabezado = ParagraphStyle(
        "CeldaEncabezado", parent=celda, fontSize=6.9, textColor=rl_colors.HexColor(INK_FAINT_HEX),
        fontName="Helvetica-Bold",
    )
    celda_encabezado_der = ParagraphStyle("CeldaEncabezadoDer", parent=celda_encabezado, alignment=2)
    nota_style = ParagraphStyle("Nota", parent=normal, fontSize=6.9, textColor=rl_colors.HexColor(INK_FAINT_HEX), leading=10)

    def titulo_seccion(texto, veredicto=False):
        return _RotuloSeccion(texto, veredicto=veredicto)

    def tabla_identificacion(pares, columnas=2):
        filas, fila = [], []
        for label, valor in pares:
            fila.append(Paragraph(f"<font size=6.6 color='{INK_FAINT_HEX}'>{label.upper()}</font><br/><b>{valor}</b>", celda))
            if len(fila) == columnas:
                filas.append(fila)
                fila = []
        if fila:
            fila += [""] * (columnas - len(fila))
            filas.append(fila)
        t = Table(filas, colWidths=[ANCHO_CONTENIDO / columnas] * columnas)
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ]))
        return t

    def estilo_hairline(filas_totales):
        estilo = [
            ("LINEBELOW", (0, 0), (-1, 0), 0.75, BORDE_FUERTE),
            ("TOPPADDING", (0, 0), (-1, -1), 2.6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
        for fila in range(1, filas_totales):
            estilo.append(("LINEBELOW", (0, fila), (-1, fila), 0.5, BORDE))
        return TableStyle(estilo)

    def tabla_checklist(campos, datos):
        filas = [[Paragraph("Punto de inspección", celda_encabezado), Paragraph("Estado", celda_encabezado_der)]]
        for campo in campos:
            con_estado = campo["tipo"] == "estado" or campo.get("con_estado")
            texto_valor, estado_label, nota = _fila_valores(datos.get(campo["campo"]), campo)
            if not con_estado:
                filas.append([Paragraph(campo["label"], celda), Paragraph(texto_valor, celda_der)])
                continue
            if estado_label == "-":
                estado_txt, color_hex = "SIN CARGAR", INK_FAINT_HEX
            else:
                estado_txt, color_hex = estado_label.upper(), COLOR_ESTADO_HEX.get(estado_label, INK_FAINT_HEX)
            etiqueta = campo["label"] if texto_valor == "-" else (
                f"{campo['label']}<br/><font size=7 color='{INK_MUTED_HEX}'>{texto_valor}</font>"
            )
            estado_celda = f"<font color='{color_hex}'><b>{estado_txt}</b></font>"
            if nota:
                estado_celda += f"<br/><font size=6.6 color='{INK_MUTED_HEX}'>{nota}</font>"
            filas.append([Paragraph(etiqueta, celda), Paragraph(estado_celda, celda_der)])
        tabla = Table(filas, colWidths=[ANCHO_CONTENIDO - 4 * cm, 4 * cm], repeatRows=1)
        tabla.setStyle(estilo_hairline(len(filas)))
        return tabla

    def celda_firma(firma_b64):
        if not firma_b64:
            return "_______________________________"
        try:
            _, datos_b64 = firma_b64.split(",", 1)
            imagen_bytes = base64.b64decode(datos_b64)
            return Image(io.BytesIO(imagen_bytes), width=6 * cm, height=2 * cm)
        except Exception:
            return "_______________________________"

    elementos = []
    elementos.append(Paragraph(f"Informe — {categoria}", titulo))
    elementos.append(Paragraph(
        f"{instalacion.cliente.nombre.upper()} · {instalacion.nombre.upper()} · {visita.fecha.strftime('%d/%m/%Y')}",
        ParagraphStyle("Meta", parent=normal, fontSize=8.3, textColor=rl_colors.HexColor(INK_MUTED_HEX), fontName="Courier"),
    ))
    elementos.append(Spacer(1, 0.35 * cm))

    # ---- Identificación del informe ----
    elementos.append(titulo_seccion("Identificación del informe"))
    elementos.append(Spacer(1, 0.2 * cm))
    pares_id = [
        ("N° de informe", informe.numero),
        ("Fecha", visita.fecha.strftime("%d/%m/%Y")),
        ("Hora inicio — término", (
            f"{visita.hora_inicio.strftime('%H:%M')} — {visita.hora_termino.strftime('%H:%M')}"
            if visita.hora_inicio and visita.hora_termino else "-"
        )),
        ("Tag de sala", instalacion.tag_sala_bombas or "-"),
        ("Inspector", (visita.enviada_por.nombre_completo or visita.enviada_por.username) if visita.enviada_por else "-"),
        ("Matrícula / certificación", (visita.enviada_por.matricula_profesional if visita.enviada_por else None) or "-"),
        ("Aseguradora", instalacion.aseguradora or "-"),
        ("N° de póliza", instalacion.numero_poliza or "-"),
    ]
    elementos.append(tabla_identificacion(pares_id, columnas=4))

    # ---- Secciones de checklist (una por tipo/equipo) ----
    for seccion in secciones:
        if seccion["tipo"].por_equipo:
            for equipo in seccion["equipos"]:
                datos = seccion["formularios"][equipo.id].datos() if equipo.id in seccion["formularios"] else {}
                elementos.append(Spacer(1, 0.4 * cm))
                elementos.append(titulo_seccion(f"{seccion['tipo'].nombre} — {equipo.nombre}" if len(seccion["equipos"]) > 1 else seccion["tipo"].nombre))
                elementos.append(Spacer(1, 0.2 * cm))
                elementos.append(tabla_checklist(seccion["campos"], datos))

                ensayo = ensayos.get(equipo)
                if ensayo:
                    elementos.append(Spacer(1, 0.25 * cm))
                    bloque_churn = [Paragraph(
                        f"Churn test (punto 0%) — ensayo del {ensayo.fecha_ensayo.strftime('%d/%m/%Y')}"
                        + ("" if ensayo.fecha_ensayo == visita.fecha else ", no de esta visita"),
                        nota_style,
                    )]
                    validacion = ensayo.validacion_nfpa25()
                    criterio_0 = validacion.get("criterio_1") if validacion else None
                    if criterio_0:
                        estado_ok = criterio_0["paso"]
                        color_ok = "#16A34A" if estado_ok else "#EA580C"
                        texto_ok = "OK" if estado_ok else "NO CUMPLE"
                        bloque_churn.append(Paragraph(
                            f"Presión neta a churn: <b>{criterio_0['valor_ensayo']} PSI</b> "
                            f"(límite {criterio_0['limite']} PSI) — "
                            f"<font color='{color_ok}'><b>{texto_ok}</b></font>",
                            celda,
                        ))
                    elif ensayo.equipo_id and equipo.curva_fabrica is None:
                        bloque_churn.append(Paragraph("Sin curva de fábrica cargada para validar contra NFPA 25.", nota_style))
                    elementos.append(KeepTogether(bloque_churn))
        else:
            datos = seccion["formulario_general"].datos() if seccion.get("formulario_general") else {}
            elementos.append(Spacer(1, 0.4 * cm))
            elementos.append(titulo_seccion(seccion["tipo"].nombre))
            elementos.append(Spacer(1, 0.2 * cm))
            elementos.append(tabla_checklist(seccion["campos"], datos))

    # ---- Observaciones ----
    elementos.append(Spacer(1, 0.5 * cm))
    elementos.append(titulo_seccion("Deficiencias y observaciones"))
    elementos.append(Spacer(1, 0.2 * cm))
    if observaciones:
        filas_obs = [[
            Paragraph("Clasificación", celda_encabezado), Paragraph("Equipo", celda_encabezado),
            Paragraph("Descripción", celda_encabezado),
        ]]
        for o in observaciones:
            color_hex = "#EA580C" if o.clasificacion == "Deficiencia crítica" else INK_MUTED_HEX
            filas_obs.append([
                Paragraph(f"<font color='{color_hex}'><b>{o.clasificacion}</b></font>", celda),
                Paragraph(o.equipo.nombre if o.equipo else "-", celda),
                Paragraph(o.descripcion, celda),
            ])
        tabla_obs = Table(filas_obs, colWidths=[4 * cm, 4 * cm, ANCHO_CONTENIDO - 8 * cm], repeatRows=1)
        tabla_obs.setStyle(estilo_hairline(len(filas_obs)))
        elementos.append(tabla_obs)
    else:
        elementos.append(Paragraph("Sin deficiencias abiertas en esta categoría.", normal))

    # ---- Diagnóstico global ----
    elementos.append(Spacer(1, 0.5 * cm))
    elementos.append(titulo_seccion("Diagnóstico global", veredicto=True))
    elementos.append(Spacer(1, 0.25 * cm))
    caja = Table(
        [[Paragraph(
            (informe.dictamen or "Pendiente de redactar por Administrador/Jefe.").replace("\n", "<br/>"), celda
        )]],
        colWidths=[ANCHO_CONTENIDO],
    )
    caja.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SLATE_SOFT),
        ("LINEBEFORE", (0, 0), (0, 0), 2, SLATE),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    elementos.append(caja)

    # ---- Firmas ----
    elementos.append(Spacer(1, 0.9 * cm))
    elementos.append(titulo_seccion("Validación"))
    elementos.append(Spacer(1, 0.3 * cm))
    nombre_tecnico = (visita.enviada_por.nombre_completo or visita.enviada_por.username) if visita.enviada_por else "-"
    matricula_tecnico = (visita.enviada_por.matricula_profesional if visita.enviada_por else None) or ""
    pie_tecnico = f"{nombre_tecnico}<br/><font size=7 color='{INK_MUTED_HEX}'>{matricula_tecnico}</font>" if matricula_tecnico else nombre_tecnico
    pie_cliente_partes = [visita.nombre_representante_cliente or "-"]
    if visita.cargo_representante_cliente:
        pie_cliente_partes.append(f"<font size=7 color='{INK_MUTED_HEX}'>{visita.cargo_representante_cliente}</font>")
    pie_cliente = "<br/>".join(pie_cliente_partes)

    firmas = Table(
        [
            [celda_firma(visita.firma_tecnico), celda_firma(visita.firma_cliente)],
            [Paragraph("Inspector", celda_encabezado), Paragraph("Representante de planta", celda_encabezado)],
            [Paragraph(pie_tecnico, celda), Paragraph(pie_cliente, celda)],
        ],
        colWidths=[ANCHO_CONTENIDO / 2, ANCHO_CONTENIDO / 2],
    )
    firmas.setStyle(TableStyle([
        ("TOPPADDING", (0, 1), (-1, 1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
    ]))
    elementos.append(firmas)

    construir(doc, elementos, tipo_doc=f"Informe — {categoria}", empresa=instalacion.cliente.empresa)
    return buffer.getvalue()
