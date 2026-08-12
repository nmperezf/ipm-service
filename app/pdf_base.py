"""Encabezado y pie de página comunes a todos los PDFs de la app: la misma
franja negra con el logo y "IPM MANAGER" que la navbar, el mismo filete
rojo de acento, y un pie calcado del footer del sitio (con fecha de
generación y "Página X de Y", que ningún PDF tenía hasta ahora).

Cada generador arma su propio contenido (título del documento, tablas,
gráficos) como flowables normales; este módulo solo dibuja el molde que
se repite en cada hoja. Usar así:

    from app.pdf_base import crear_documento, construir, estilos, INK, INK_MUTED, BORDE, ACCENT

    doc = crear_documento(buffer)
    styles = estilos()
    elementos = [Paragraph("Título del documento", styles["titulo"]), ...]
    construir(doc, elementos, tipo_doc="Orden de trabajo")
"""

import os
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import SimpleDocTemplate

INK = colors.HexColor("#14181F")
INK_MUTED = colors.HexColor("#5B6773")
INK_FAINT = colors.HexColor("#9AA1AC")
BORDE = colors.HexColor("#DEE2D8")
BORDE_FUERTE = colors.HexColor("#C7CDC0")
SURFACE_MUTED = colors.HexColor("#F4F6F8")
ACCENT = colors.HexColor("#E2131D")
ACCENT_SOFT = colors.HexColor("#FBEAE7")
SLATE = colors.HexColor("#2B3D4F")
SLATE_SOFT = colors.HexColor("#EDF1F3")
VERDE = colors.HexColor("#1F8A54")
VERDE_SUAVE = colors.HexColor("#E6F4EB")

TAGLINE = "IPM Manager — Gestión de mantenimiento de sistemas contra incendio en Uruguay"

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "static", "img", "logo.png")
_LOGO_PROPORCION = 190 / 220  # ancho/alto real del archivo, para no deformarlo

MARGEN_LAT = 1.8 * cm
# El masthead pasa a ser una línea chica y apagada (chip con el logo +
# "IPM Manager" + tipo de documento, un filete fino debajo) en vez de la
# franja negra de antes -- ocupa mucho menos alto, así que el margen
# superior baja de 3cm a 1.9cm y cada documento gana esa diferencia de
# espacio útil.
MARGEN_SUP = 1.9 * cm
MARGEN_INF = 1.7 * cm  # deja lugar al pie
ALTO_MASTHEAD = 0.55 * cm  # alto del chip de logo -- define el resto del masthead


def estilos():
    """Estilos de párrafo base, con los colores reales de la app (antes
    cada PDF traía su propio azul, y no siempre el mismo)."""
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle(
            "PDFTitulo", parent=base["Title"], textColor=INK, fontName="Helvetica-Bold",
            fontSize=19, leading=22, spaceAfter=2, alignment=0,
        ),
        "subtitulo": ParagraphStyle("PDFSubtitulo", parent=base["Normal"], textColor=INK_MUTED, fontSize=9.5),
        "h2": ParagraphStyle(
            "PDFH2", parent=base["Heading2"], textColor=INK, fontSize=12, spaceBefore=14, spaceAfter=6
        ),
        "normal": base["Normal"],
        "celda": ParagraphStyle("PDFCelda", parent=base["Normal"], fontSize=9, leading=12),
    }


def estilo_tabla_encabezado():
    """TableStyle de uso general: fila de encabezado gris clara, texto
    tinta, grilla con el borde real de la app — la mayoría de las tablas
    de estos PDFs arrancan de acá."""
    from reportlab.platypus import TableStyle

    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), SURFACE_MUTED),
            ("TEXTCOLOR", (0, 0), (-1, 0), INK),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, BORDE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
    )


def _crear_canvas_numerado(tipo_doc):
    """Clase de Canvas que dibuja la franja negra + filete rojo + pie en
    cada hoja, con "Página X de Y". reportlab no sabe cuántas hojas va a
    tener el documento hasta terminar de armarlo, así que hay que guardar
    el estado de cada hoja según se van cerrando y recién completar el
    total al final — es el idiom estándar de reportlab para esto."""

    class _CanvasNumerado(Canvas):
        def __init__(self, *args, **kwargs):
            Canvas.__init__(self, *args, **kwargs)
            self._paginas_pendientes = []

        def showPage(self):
            self._paginas_pendientes.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._paginas_pendientes)
            for estado in self._paginas_pendientes:
                self.__dict__.update(estado)
                self._dibujar_marco(total)
                Canvas.showPage(self)
            Canvas.save(self)

        def _dibujar_marco(self, total_paginas):
            ancho, alto = self._pagesize  # respeta vertical u horizontal
            self.saveState()

            # Masthead chico y apagado: chip oscuro con el logo (el archivo
            # tiene partes blancas pensadas para un fondo oscuro, por eso el
            # chip) + "IPM Manager" en gris, tipo de documento a la derecha,
            # un filete fino abajo -- nada de franja a sangre ni bloque de
            # color grande. El contenido de cada PDF queda como protagonista.
            y_base = alto - MARGEN_SUP + 0.55 * cm
            x = MARGEN_LAT

            self.setFillColor(INK)
            self.roundRect(x, y_base, ALTO_MASTHEAD, ALTO_MASTHEAD, 1, stroke=0, fill=1)
            if os.path.exists(_LOGO_PATH):
                pad = 0.05 * cm
                alto_logo = ALTO_MASTHEAD - 2 * pad
                ancho_logo = alto_logo * _LOGO_PROPORCION
                self.drawImage(
                    _LOGO_PATH,
                    x + (ALTO_MASTHEAD - ancho_logo) / 2,
                    y_base + pad,
                    width=ancho_logo,
                    height=alto_logo,
                    mask="auto",
                    preserveAspectRatio=True,
                )
            x += ALTO_MASTHEAD + 0.25 * cm

            self.setFillColor(INK_MUTED)
            self.setFont("Helvetica-Bold", 8)
            self.drawString(x, y_base + ALTO_MASTHEAD / 2 - 3, "IPM MANAGER")

            self.setFillColor(INK_FAINT)
            self.setFont("Helvetica", 7.5)
            self.drawRightString(ancho - MARGEN_LAT, y_base + ALTO_MASTHEAD / 2 - 2.5, tipo_doc.upper())

            self.setStrokeColor(BORDE_FUERTE)
            self.setLineWidth(0.6)
            self.line(MARGEN_LAT, y_base - 0.18 * cm, ancho - MARGEN_LAT, y_base - 0.18 * cm)

            # Pie de página
            self.setStrokeColor(BORDE)
            self.setLineWidth(0.5)
            self.line(MARGEN_LAT, MARGEN_INF - 0.35 * cm, ancho - MARGEN_LAT, MARGEN_INF - 0.35 * cm)

            self.setFillColor(INK_FAINT)
            self.setFont("Helvetica", 7)
            self.drawString(MARGEN_LAT, MARGEN_INF - 0.7 * cm, TAGLINE)
            self.drawRightString(
                ancho - MARGEN_LAT,
                MARGEN_INF - 0.7 * cm,
                f"Generado {date.today().strftime('%d/%m/%Y')} · Página {self._pageNumber} de {total_paginas}",
            )
            self.restoreState()

    return _CanvasNumerado


def crear_documento(buffer, pagesize=A4, margen_izq=None, margen_der=None):
    """SimpleDocTemplate con los márgenes que dejan lugar al encabezado y
    pie comunes. El ancho de página (A4 vertical u horizontal) sigue
    siendo decisión de cada generador."""
    return SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        topMargin=MARGEN_SUP,
        bottomMargin=MARGEN_INF,
        leftMargin=margen_izq or MARGEN_LAT,
        rightMargin=margen_der or MARGEN_LAT,
    )


def construir(doc, elementos, tipo_doc):
    """Reemplaza a doc.build(elementos): arma el documento con el
    encabezado/pie comunes ya enganchados. tipo_doc es lo que se muestra
    a la derecha de la franja negra (ej. "Orden de trabajo")."""
    doc.build(elementos, canvasmaker=_crear_canvas_numerado(tipo_doc))
