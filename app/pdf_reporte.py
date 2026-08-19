"""Generación de PDF de reporte consolidado, para enviar al cliente.
Dos formatos según el checklist: tabla ancha equipo×campos (BIE, ECA — muchos
equipos, pocos datos simples) o ficha vertical por equipo con fotos embebidas
(ej. desarme de bombas — pocos equipos, muchos puntos, cada uno con foto)."""

import io
import os

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, KeepTogether, Paragraph, Spacer, Table, TableStyle

from app.models import ESTADOS_CHECKLIST_LABEL, Foto
from app.pdf_base import ACCENT_SOFT, BORDE, INK, SURFACE_MUTED, construir, crear_documento, estilos


def _valor_texto(valor):
    if valor is None or valor == "":
        return "-"
    if isinstance(valor, list):
        return ", ".join(valor) if valor else "-"
    return str(valor)


def _fila_valores(valor, campo):
    """(texto del valor, label del estado, nota) de un campo ya cargado --
    unifica el campo simple (numero/texto sin estado, como los checklists
    de siempre) con el que tiene estado (con_estado=true o tipo='estado').
    Mismo criterio que pdf_checklist_tecnico._fila_valores."""
    con_estado = campo["tipo"] == "estado" or campo.get("con_estado")
    unidad = campo.get("unidad", "")

    def _fmt(v):
        if v is None or v == "":
            return "-"
        if isinstance(v, list):
            return ", ".join(v) if v else "-"
        return f"{v} {unidad}".strip()

    if not con_estado:
        return _fmt(valor), "-", ""
    if not valor:
        return "-", "-", ""
    estado = valor.get("estado") or ""
    estado_label = ESTADOS_CHECKLIST_LABEL.get(estado, "-" if not estado else estado)
    return _fmt(valor.get("valor")), estado_label, valor.get("nota") or ""


def _imagen_foto(foto, caja=2.6 * cm):
    """Image flowable ajustada dentro de una caja cuadrada, respetando el
    aspect ratio real del archivo -- None si el archivo no existe más en
    disco (no debería pasar, pero no vale la pena romper el PDF por eso)."""
    ruta = os.path.join(current_app.config["UPLOAD_FOLDER"], foto.nombre_archivo)
    try:
        ancho_real, alto_real = ImageReader(ruta).getSize()
    except Exception:
        return None
    escala = min(caja / ancho_real, caja / alto_real)
    return Image(ruta, width=ancho_real * escala, height=alto_real * escala)


def generar_pdf_reporte_equipos(item, tipo, formularios):
    """item: ItemVisita (el servicio/ronda de inspección).
    tipo: TipoFormulario (el checklist, ej. 'Checklist de BIE').
    formularios: lista de Formulario ya completados, uno por equipo."""
    campos = tipo.campos()
    tiene_fotos = any(c.get("requiere_foto") for c in campos)

    buffer = io.BytesIO()
    if tiene_fotos:
        doc = crear_documento(buffer)
    else:
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

    if not formularios:
        elementos.append(Paragraph("Todavía no hay checklists completados para este reporte.", styles["normal"]))
        construir(doc, elementos, tipo_doc="Reporte de equipos", empresa=instalacion.cliente.empresa)
        return buffer.getvalue()

    if tiene_fotos:
        _armar_ficha_por_equipo(elementos, item, formularios, campos, styles)
    else:
        _armar_tabla_ancha(elementos, formularios, campos, celda_texto)

    construir(doc, elementos, tipo_doc="Reporte de equipos", empresa=instalacion.cliente.empresa)
    return buffer.getvalue()


def _armar_tabla_ancha(elementos, formularios, campos, celda_texto):
    """Una fila por equipo, una columna por campo -- para checklists de
    muchos equipos y pocos datos simples (BIE, ECA). Formato de siempre."""
    encabezado = ["Equipo"] + [Paragraph(c["label"], celda_texto) for c in campos]
    filas = [encabezado]

    for formulario in formularios:
        datos = formulario.datos()
        fila = [Paragraph(formulario.equipo.nombre if formulario.equipo else "-", celda_texto)]
        for campo in campos:
            fila.append(Paragraph(_valor_texto(datos.get(campo["campo"])), celda_texto))
        filas.append(fila)

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


def _armar_ficha_por_equipo(elementos, item, formularios, campos, styles):
    """Un bloque por equipo, un punto por fila (etiqueta + valor a la
    izquierda, foto(s) del punto a la derecha si tiene) -- para checklists
    con pocos equipos y muchos puntos, cada uno con evidencia fotográfica
    (ej. desarme de bombas: acoplamiento, sello, rodamientos)."""
    h2, normal = styles["h2"], styles["normal"]
    nota_style = ParagraphStyle("Nota", parent=normal, fontSize=8.5, textColor=INK)
    valor_style = ParagraphStyle("Valor", parent=normal, fontSize=9.5, textColor=colors.HexColor("#565F6E"))

    fotos_por_punto = {}
    for foto in Foto.query.filter(
        Foto.item_visita_id == item.id, Foto.campo_formulario.isnot(None)
    ).all():
        fotos_por_punto.setdefault((foto.equipo_id, foto.campo_formulario), []).append(foto)

    ancho_texto = 12 * cm
    ancho_fotos = 5 * cm

    for formulario in formularios:
        datos = formulario.datos()
        bloque = [Paragraph(formulario.equipo.nombre if formulario.equipo else "-", h2)]

        filas = []
        for campo in campos:
            texto_valor, estado_label, nota = _fila_valores(datos.get(campo["campo"]), campo)
            texto = f"<b>{campo['label']}</b><br/>{texto_valor}"
            if estado_label != "-":
                texto += f" &middot; <b>{estado_label}</b>"
            partes = [Paragraph(texto, valor_style)]
            if nota:
                partes.append(Paragraph(nota, nota_style))
            celda_texto = partes if len(partes) > 1 else partes[0]

            fotos = fotos_por_punto.get((formulario.equipo_id, campo["campo"]), []) if campo.get("requiere_foto") else []
            imagenes = [img for f in fotos if (img := _imagen_foto(f, caja=2.3 * cm)) is not None]
            celda_fotos = Table([imagenes], colWidths=[2.3 * cm] * len(imagenes)) if imagenes else ""

            fila_tabla = Table(
                [[celda_texto, celda_fotos]],
                colWidths=[ancho_texto, ancho_fotos],
            )
            fila_tabla.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LINEBELOW", (0, 0), (-1, 0), 0.4, BORDE),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ("BACKGROUND", (0, 0), (-1, 0), ACCENT_SOFT if estado_label == "Deficiencia" else colors.white),
                    ]
                )
            )
            filas.append(fila_tabla)

        bloque.extend(filas)
        # KeepTogether con el título + primera fila: evita que el nombre
        # del equipo quede solo al final de una hoja, separado de su
        # propio contenido.
        elementos.append(KeepTogether(bloque[:2]) if len(bloque) > 1 else bloque[0])
        elementos.extend(bloque[2:])
        elementos.append(Spacer(1, 0.5 * cm))
