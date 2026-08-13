"""Generación de PDF del ensayo de curva de caudal (NFPA 25): identificación
del ensayo, condiciones de prueba, tabla combinada de fábrica + ensayo,
criterios de la norma junto al gráfico —sin un veredicto automático de
aprobado/no aprobado, eso lo redacta el Administrador/Jefe en Comentarios—
y el estado de validación."""

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Flowable, Image, KeepTogether, Paragraph, Spacer, Table, TableStyle

from app.pdf_base import (
    ACCENT,
    BORDE,
    BORDE_FUERTE,
    SLATE,
    SLATE_SOFT,
    construir,
    crear_documento,
    estilos,
)

ANCHO_CONTENIDO = 18 * cm
ANCHO_PAGINA = A4[0]

# Mismo factor que ya usa la pantalla de carga del ensayo (ver
# formulario_ensayo.html: PSI_A_FT) -- se agrega como referencia chica
# debajo de cada valor CALCULADO de presión (fábrica, neta, ajustada,
# criterios), no de las lecturas crudas de manómetro (descarga/succión),
# porque es contra esos calculados que se cruza la curva que da el
# fabricante, casi siempre publicada en ft Head.
FT_POR_PSI = 2.307

INK_FAINT_HEX = "#9AA1AC"
INK_MUTED_HEX = "#5B6773"

NOMBRES_CRITERIO = {
    "criterio_1": "Presión a 0%",
    "criterio_2": "Presión a 100% (nominal)",
    "criterio_3": "Presión a 150% (sobrecarga)",
}


class _RotuloSeccion(Flowable):
    """Tick de color + rótulo en mayúsculas + filete fino hasta el borde
    del contenido -- reemplaza la franja negra de antes. Gris azulado
    (SLATE) para las secciones de datos, rojo de acento para las dos que
    hay que leer con atención (Criterios, Validación)."""

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


def _grafico_curvas(gpm, presiones_fabrica, presiones_ensayo_ajustadas, presiones_ensayo_sin_ajustar):
    """Dispersión (los 4 puntos reales) + curva suavizada (parábola
    ajustada, ver utils.curva_suavizada) para fábrica, ensayo ajustado a RPM
    nominal y ensayo tal cual se midió (sin ajuste), superpuestas. Eje de
    presión en ft Head (lo que publica el fabricante), no PSI."""
    from app.utils import curva_suavizada

    # El punto de fábrica a 50% puede no existir (ver CurvaFabrica) -- se
    # arma con None en su posición y se descarta antes de ajustar la
    # parábola / dibujar el scatter, sin perder el resto de los índices.
    fabrica_ft = [p * FT_POR_PSI if p is not None else None for p in presiones_fabrica]
    ajustada_ft = [p * FT_POR_PSI for p in presiones_ensayo_ajustadas]
    sin_ajustar_ft = [p * FT_POR_PSI for p in presiones_ensayo_sin_ajustar]

    fig, ax = plt.subplots(figsize=(9.4, 3.4), dpi=150)

    gpm_fab_validos = [g for g, p in zip(gpm, fabrica_ft) if p is not None]
    fabrica_ft_validos = [p for p in fabrica_ft if p is not None]
    xs_fabrica, ys_fabrica = curva_suavizada(gpm_fab_validos, fabrica_ft_validos)
    ax.plot(xs_fabrica, ys_fabrica, color="#14181F", linewidth=1.8, label="Curva de fábrica")
    ax.scatter(gpm_fab_validos, fabrica_ft_validos, color="#14181F", zorder=3, s=22)

    xs_sin_ajustar, ys_sin_ajustar = curva_suavizada(gpm, sin_ajustar_ft)
    ax.plot(xs_sin_ajustar, ys_sin_ajustar, color="#B5730A", linewidth=1.8, linestyle="--", label="Ensayo (sin ajustar)")
    ax.scatter(gpm, sin_ajustar_ft, color="#B5730A", zorder=3, marker="^", s=22)

    xs_ensayo, ys_ensayo = curva_suavizada(gpm, ajustada_ft)
    ax.plot(xs_ensayo, ys_ensayo, color="#E2131D", linewidth=1.8, label="Ensayo (ajustado a RPM nominal)")
    ax.scatter(gpm, ajustada_ft, color="#E2131D", zorder=3, s=22)

    # Referencias NFPA 25 — no son datos medidos, son los dos puntos que
    # define la norma: el punto nominal (100% del caudal, a la presión
    # nominal de fábrica) y el mínimo aprobado en sobrecarga (150% del
    # caudal, 65% de esa misma presión nominal). Se marcan con una cruz
    # en un color y símbolo que no usa ninguna otra serie del gráfico,
    # para que se lean como referencia y no como una curva más.
    gpm_nominal, presion_nominal = gpm[2], fabrica_ft[2]
    gpm_sobrecarga = gpm[3]
    presion_minima_nfpa = presion_nominal * 0.65
    ax.scatter(
        [gpm_nominal, gpm_sobrecarga], [presion_nominal, presion_minima_nfpa],
        color="#6B32C9", marker="x", s=70, linewidths=2, zorder=5, label="Referencia",
    )
    ax.annotate(
        "100%", (gpm_nominal, presion_nominal), textcoords="offset points", xytext=(7, 5),
        fontsize=7.5, color="#6B32C9", fontweight="bold",
    )
    ax.annotate(
        "65%", (gpm_sobrecarga, presion_minima_nfpa), textcoords="offset points", xytext=(7, 5),
        fontsize=7.5, color="#6B32C9", fontweight="bold",
    )

    ax.set_xlabel("Caudal (GPM)", fontsize=8.5, color="#5B6773")
    ax.set_ylabel("Presión (ft Head)", fontsize=8.5, color="#5B6773")
    ax.set_xticks(gpm)
    ax.tick_params(labelsize=7.5, colors="#5B6773")
    ax.grid(True, linestyle="--", alpha=0.35)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(loc="upper right", fontsize=6.8, frameon=False)
    fig.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png")
    plt.close(fig)
    buffer.seek(0)
    return buffer


def generar_pdf_ensayo(ensayo):
    """ensayo: EnsayoCaudal (con equipo y equipo.curva_fabrica ya cargados).
    Devuelve los bytes del PDF."""
    equipo = ensayo.equipo
    curva_fabrica = equipo.curva_fabrica
    instalacion = equipo.instalacion

    buffer = io.BytesIO()
    doc = crear_documento(buffer, margen_izq=1.5 * cm, margen_der=1.5 * cm)
    styles = estilos()
    titulo, normal, celda = styles["titulo"], styles["normal"], styles["celda"]

    celda_num = ParagraphStyle("CeldaNum", parent=celda, alignment=2)  # 2 = right
    celda_num_bold = ParagraphStyle("CeldaNumBold", parent=celda_num, fontName="Helvetica-Bold")
    celda_encabezado = ParagraphStyle(
        "CeldaEncabezado", parent=celda, fontSize=6.9, textColor=colors.HexColor(INK_FAINT_HEX),
        fontName="Helvetica-Bold",
    )
    celda_encabezado_der = ParagraphStyle("CeldaEncabezadoDer", parent=celda_encabezado, alignment=2)
    nota_style = ParagraphStyle("Nota", parent=normal, fontSize=6.9, textColor=colors.HexColor(INK_FAINT_HEX), leading=10)

    def titulo_seccion(texto, veredicto=False):
        return _RotuloSeccion(texto, veredicto=veredicto)

    def con_ft(valor, unidad="PSI"):
        """Valor en PSI arriba, ft Head chico debajo (ver FT_POR_PSI)."""
        ft = valor * FT_POR_PSI
        return f"{valor:.1f} {unidad}<br/><font size=6.2 color='{INK_FAINT_HEX}'>{ft:.1f} ft Head</font>"

    def tabla_identificacion(pares, columnas=2):
        """pares: lista de (label, valor) -> grilla sin bordes, ancho total
        ANCHO_CONTENIDO. Dos columnas por defecto para que "Lugar" (cliente
        + instalación, el valor más largo de la ficha) entre en una línea.
        Fila compacta a propósito: esta tabla convive con otras tres
        secciones más el gráfico grande en la misma hoja."""
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

    def estilo_hairline(filas_totales, columnas_totales):
        """Filete bajo el encabezado (más marcado) y bajo cada fila de
        datos (más suave) -- sin grilla vertical ni relleno de color,
        como una hoja de datos, no una tabla de UI. Filas apretadas por la
        misma razón que tabla_identificacion."""
        estilo = [
            ("LINEBELOW", (0, 0), (-1, 0), 0.75, BORDE_FUERTE),
            ("TOPPADDING", (0, 0), (-1, -1), 2.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 2.2),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
        for fila in range(1, filas_totales):
            estilo.append(("LINEBELOW", (0, fila), (-1, fila), 0.5, BORDE))
            estilo.append(("BOTTOMPADDING", (0, fila), (-1, fila), 2.2))
        return TableStyle(estilo)

    elementos = []
    elementos.append(Paragraph("Ensayo de curva de caudal — NFPA 25", titulo))
    elementos.append(Paragraph(
        f"{instalacion.cliente.nombre.upper()} · {instalacion.nombre.upper()} · {ensayo.fecha_ensayo.strftime('%d/%m/%Y')}",
        ParagraphStyle("Meta", parent=normal, fontSize=8.3, textColor=colors.HexColor(INK_MUTED_HEX), fontName="Courier"),
    ))
    elementos.append(Spacer(1, 0.35 * cm))

    elementos.append(titulo_seccion("Identificación del ensayo"))
    elementos.append(Spacer(1, 0.2 * cm))
    elementos.append(tabla_identificacion([("Lugar", f"{instalacion.cliente.nombre} — {instalacion.nombre}")], columnas=1))
    elementos.append(Spacer(1, 0.1 * cm))
    elementos.append(tabla_identificacion([
        ("Fecha", ensayo.fecha_ensayo.strftime("%d/%m/%Y")),
        ("Inspector", (ensayo.creado_por.nombre_completo or ensayo.creado_por.username) if ensayo.creado_por else "-"),
    ]))
    elementos.append(Spacer(1, 0.15 * cm))
    # Fila de 4 + fila de 4, mismo ancho de columna en las dos -- para que
    # los datos de bomba y los de placa queden alineados en una grilla.
    elementos.append(tabla_identificacion([
        ("Tipo de bomba", equipo.tipo),
        ("Modelo", equipo.modelo or "-"),
        ("N° de serie", equipo.serie or "-"),
        ("Caudal diseño", f"{equipo.caudal_nominal} GPM" if equipo.caudal_nominal else "-"),
        ("PSI MAX", equipo.presion_maxima if equipo.presion_maxima else "-"),
        ("PSIG", equipo.presion_diseno if equipo.presion_diseno else "-"),
        ("PSI 1.5", equipo.presion_sobrecarga if equipo.presion_sobrecarga else "-"),
        ("RPM nominal", equipo.rpm_nominal or "-"),
    ], columnas=4))

    condiciones = []
    if ensayo.temperatura_ambiente is not None:
        condiciones.append(("Temperatura ambiente", f"{ensayo.temperatura_ambiente} °C"))
    if ensayo.presion_atmosferica_mbar is not None:
        condiciones.append(("Presión atmosférica", f"{ensayo.presion_atmosferica_mbar} Mbar"))
    if ensayo.presion_succion_estatica is not None:
        condiciones.append(("Presión succión (estática)", f"{ensayo.presion_succion_estatica} PSI"))
    if condiciones:
        elementos.append(Spacer(1, 0.4 * cm))
        elementos.append(titulo_seccion("Condiciones de prueba"))
        elementos.append(Spacer(1, 0.2 * cm))
        elementos.append(tabla_identificacion(condiciones, columnas=3))
    if ensayo.normativa_aplicable:
        elementos.append(Spacer(1, 0.15 * cm))
        elementos.append(Paragraph(f"<b>Normativa aplicable:</b> {ensayo.normativa_aplicable}", celda))

    # ---- Curva de fábrica y ensayo, en una sola tabla ----
    # Antes eran dos tablas separadas (una la referencia de fábrica, otra
    # el ensayo) repitiendo Caudal/GPM/RPM en las dos -- acá la presión de
    # fábrica es una columna más al lado de cada punto del ensayo, para
    # comparar en la misma fila y no tener que ir y volver entre tablas.
    elementos.append(Spacer(1, 0.4 * cm))
    elementos.append(titulo_seccion("Curva de fábrica y ensayo"))
    elementos.append(Spacer(1, 0.2 * cm))
    if curva_fabrica:
        elementos.append(Paragraph(f"RPM nominal de fábrica: {curva_fabrica.rpm_nominal}", nota_style))
        elementos.append(Spacer(1, 0.15 * cm))
        _, presiones_fabrica = curva_fabrica.puntos()
    else:
        presiones_fabrica = None

    rpm = ensayo.puntos_rpm()
    netas = ensayo.puntos_netos()
    descargas = [
        ensayo.presion_descarga_punto_0, ensayo.presion_descarga_punto_50,
        ensayo.presion_descarga_punto_100, ensayo.presion_descarga_punto_150,
    ]
    succiones = [
        ensayo.presion_succion_punto_0, ensayo.presion_succion_punto_50,
        ensayo.presion_succion_punto_100, ensayo.presion_succion_punto_150,
    ]

    if curva_fabrica:
        ajustadas = ensayo.puntos_ajustados(curva_fabrica.rpm_nominal)
        variaciones = [
            round((aj - fab) / fab * 100, 1) if fab else None for aj, fab in zip(ajustadas, presiones_fabrica)
        ]
        gpm_fabrica = [equipo.caudal_nominal * factor if equipo.caudal_nominal else pct
                       for pct, factor in [(0, 0), (50, 0.5), (100, 1), (150, 1.5)]]
    else:
        from app.utils import calcular_presion_ajustada

        ajustadas = [calcular_presion_ajustada(n, r, r) for n, r in zip(netas, rpm)]
        variaciones = [None] * 4
        gpm_fabrica = [0, 50, 100, 150]

    gpm_ensayo = ensayo.puntos_gpm()

    encabezados = ["Caudal", "P. fábrica", "RPM ens.", "P. desc.", "P. succ.", "P. neta", "P. ajust.", "Variación"]
    filas = [[Paragraph(h, celda_encabezado if i == 0 else celda_encabezado_der) for i, h in enumerate(encabezados)]]
    for i, pct in enumerate([0, 50, 100, 150]):
        gpm_txt = round(gpm_ensayo[i], 0) if gpm_ensayo[i] is not None else "-"
        caudal_cell = Paragraph(f"<b>{pct}%</b><br/><font size=6.2 color='{INK_FAINT_HEX}'>{gpm_txt} GPM</font>", celda)
        fabrica_cell = Paragraph(
            con_ft(presiones_fabrica[i]) if presiones_fabrica and presiones_fabrica[i] is not None else "-", celda_num
        )
        neta_cell = Paragraph(con_ft(round(netas[i], 1)), celda_num)
        ajust_cell = Paragraph(con_ft(round(ajustadas[i], 1)), celda_num)
        variacion_txt = f"{variaciones[i]:+.1f}%" if variaciones[i] is not None else "-"
        filas.append([
            caudal_cell, fabrica_cell, Paragraph(str(rpm[i]), celda_num),
            Paragraph(f"{descargas[i]:.1f} PSI", celda_num), Paragraph(f"{succiones[i]:.1f} PSI", celda_num),
            neta_cell, ajust_cell, Paragraph(variacion_txt, celda_num),
        ])
    tabla_datos = Table(
        filas, colWidths=[2.6 * cm, 2.6 * cm, 1.8 * cm, 2.0 * cm, 2.0 * cm, 2.4 * cm, 2.4 * cm, 2.2 * cm],
        repeatRows=1,
    )
    tabla_datos.setStyle(estilo_hairline(len(filas), len(encabezados)))
    elementos.append(tabla_datos)
    elementos.append(Spacer(1, 0.1 * cm))
    elementos.append(Paragraph(
        f"Presión neta = descarga − succión &middot; Presión ajustada = neta × (RPM nominal / RPM ensayada)² &middot; "
        f"Variación = (ajustada − fábrica) / fábrica &middot; ft Head = PSI × {FT_POR_PSI}", nota_style,
    ))

    # ---- Gráfico, protagonista a ancho completo ----
    elementos.append(Spacer(1, 0.5 * cm))
    elementos.append(titulo_seccion("Representación del ensayo"))
    elementos.append(Spacer(1, 0.3 * cm))
    if curva_fabrica:
        netas_redondeadas = [round(n, 1) for n in netas]
        grafico_buffer = _grafico_curvas(gpm_fabrica, presiones_fabrica, ajustadas, netas_redondeadas)
        elementos.append(Image(grafico_buffer, width=ANCHO_CONTENIDO, height=6.5 * cm))
    else:
        elementos.append(Paragraph("Sin curva de fábrica cargada para graficar.", normal))

    # ---- Criterios NFPA 25 (debajo del gráfico) ----
    # KeepTogether: si el título y la tabla no entran enteros en lo que
    # queda de la hoja, pasan juntos a la siguiente en vez de dejar el
    # título huérfano arriba y la tabla cortada abajo.
    bloque_criterios = [Spacer(1, 0.5 * cm), titulo_seccion("Criterios NFPA 25", veredicto=True), Spacer(1, 0.25 * cm)]
    validacion = ensayo.validacion_nfpa25()
    if validacion:
        filas_crit = [[
            Paragraph("Criterio", celda_encabezado), Paragraph("Valor", celda_encabezado_der),
            Paragraph("Límite", celda_encabezado_der), Paragraph("Estado", celda_encabezado),
        ]]
        formulas = []
        for i, (clave, criterio) in enumerate(validacion.items(), start=1):
            nombre = NOMBRES_CRITERIO.get(clave, clave)
            formulas.append(f"{nombre}: {criterio['descripcion']}")
            if criterio["paso"]:
                estado_cell = Paragraph("<font color='#1F8A54'><b>OK</b></font>", celda)
            else:
                estado_cell = Paragraph("<font color='#E2131D'><b>NO CUMPLE</b></font>", celda)
            filas_crit.append([
                Paragraph(f"<b>{nombre}</b>", celda),
                Paragraph(con_ft(criterio["valor_ensayo"]), celda_num),
                Paragraph(con_ft(criterio["limite"]), celda_num),
                estado_cell,
            ])
        tabla_crit = Table(filas_crit, colWidths=[6 * cm, 4.6 * cm, 4.4 * cm, 3 * cm], repeatRows=1)
        tabla_crit.setStyle(estilo_hairline(len(filas_crit), 4))
        bloque_criterios.append(tabla_crit)
        bloque_criterios.append(Spacer(1, 0.1 * cm))
        bloque_criterios.append(Paragraph(" &middot; ".join(formulas), nota_style))
    else:
        bloque_criterios.append(Paragraph("No se puede comparar contra NFPA 25 sin una curva de fábrica cargada.", normal))
    elementos.append(KeepTogether(bloque_criterios))

    # ---- Comentarios ----
    # Siempre se reserva el espacio para esta sección, aunque no haya
    # comentario cargado -- antes desaparecía del todo y parecía que no
    # había lugar para escribir uno.
    elementos.append(Spacer(1, 0.75 * cm))
    elementos.append(titulo_seccion("Comentarios"))
    elementos.append(Spacer(1, 0.35 * cm))
    if ensayo.comentarios:
        caja_comentario = Table(
            [[Paragraph(ensayo.comentarios.replace("\n", "<br/>"), celda)]], colWidths=[ANCHO_CONTENIDO],
        )
        caja_comentario.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), SLATE_SOFT),
            ("LINEBEFORE", (0, 0), (0, 0), 2, SLATE),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ]))
        elementos.append(caja_comentario)
    else:
        elementos.append(Paragraph("Sin comentarios.", nota_style))

    # ---- Validación del Jefe/Administrador (independiente del cálculo) ----
    elementos.append(Spacer(1, 0.9 * cm))
    elementos.append(titulo_seccion("Validación", veredicto=True))
    elementos.append(Spacer(1, 0.35 * cm))
    if ensayo.validado_por:
        validado_por = ensayo.validado_por.nombre_completo or ensayo.validado_por.username
        fecha_val = ensayo.fecha_validacion.strftime("%d/%m/%Y") if ensayo.fecha_validacion else "-"
    else:
        validado_por, fecha_val = "—", "—"
    elementos.append(tabla_identificacion(
        [("Estado", ensayo.estado_revision), ("Validado por", validado_por), ("Fecha", fecha_val)], columnas=3,
    ))

    construir(doc, elementos, tipo_doc="Ensayo de curva de caudal")
    return buffer.getvalue()
