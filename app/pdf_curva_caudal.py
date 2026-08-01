"""Generación de PDF del ensayo de curva de caudal (NFPA 25): identificación
del ensayo, condiciones de prueba, tabla de la curva de fábrica, tabla del
ensayo, gráfico superpuesto, los 3 criterios de la norma como referencia
—sin un veredicto automático de aprobado/no aprobado, eso lo redacta el
Administrador/Jefe en Comentarios— y el estado de validación."""

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import Flowable, Image, Paragraph, Spacer, Table, TableStyle

from app.pdf_base import (
    ACCENT,
    ACCENT_SOFT,
    BORDE,
    INK,
    INK_MUTED,
    SURFACE_MUTED,
    VERDE,
    construir,
    crear_documento,
    estilo_tabla_encabezado,
    estilos,
)

OK_BG = colors.HexColor("#E8F7EE")
ANCHO_CONTENIDO = 18 * cm
MARGEN_LAT_ENSAYO = 1.5 * cm
ANCHO_PAGINA = A4[0]


class _BandaSeccion(Flowable):
    """Título de sección de punta a punta de la hoja (como el encabezado),
    no solo del ancho de contenido: dibuja directo sobre el canvas
    deshaciendo el margen lateral en vez de usar una tabla, que queda
    encajonada dentro del margen normal del documento."""

    ALTO = 0.85 * cm

    def __init__(self, texto):
        Flowable.__init__(self)
        self.texto = texto
        self.width = ANCHO_CONTENIDO
        self.height = self.ALTO

    def draw(self):
        c = self.canv
        c.saveState()
        c.translate(-MARGEN_LAT_ENSAYO, 0)
        c.setFillColor(colors.black)
        c.rect(0, 0, ANCHO_PAGINA, self.ALTO, stroke=0, fill=1)
        c.setFillColor(ACCENT)
        c.rect(0, -0.09 * cm, ANCHO_PAGINA, 0.09 * cm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(MARGEN_LAT_ENSAYO, self.ALTO / 2 - 3, self.texto.upper())
        c.restoreState()

NOMBRES_CRITERIO = {
    "criterio_1": "Presión a 0%",
    "criterio_2": "Presión a 100% (nominal)",
    "criterio_3": "Presión a 150% (sobrecarga)",
}


def _grafico_curvas(gpm, presiones_fabrica, presiones_ensayo_ajustadas, presiones_ensayo_sin_ajustar):
    """Dispersión (los 4 puntos reales) + curva suavizada (parábola
    ajustada, ver utils.curva_suavizada) para fábrica, ensayo ajustado a RPM
    nominal y ensayo tal cual se midió (sin ajuste), superpuestas."""
    from app.utils import curva_suavizada

    fig, ax = plt.subplots(figsize=(6.4, 3.4), dpi=150)

    xs_fabrica, ys_fabrica = curva_suavizada(gpm, presiones_fabrica)
    ax.plot(xs_fabrica, ys_fabrica, color="#1A2233", linewidth=2, label="Curva de fábrica")
    ax.scatter(gpm, presiones_fabrica, color="#1A2233", zorder=3)

    xs_sin_ajustar, ys_sin_ajustar = curva_suavizada(gpm, presiones_ensayo_sin_ajustar)
    ax.plot(xs_sin_ajustar, ys_sin_ajustar, color="#B5730A", linewidth=2, linestyle="--", label="Ensayo (sin ajustar)")
    ax.scatter(gpm, presiones_ensayo_sin_ajustar, color="#B5730A", zorder=3, marker="^")

    xs_ensayo, ys_ensayo = curva_suavizada(gpm, presiones_ensayo_ajustadas)
    ax.plot(xs_ensayo, ys_ensayo, color="#E2131D", linewidth=2, label="Ensayo (ajustado a RPM nominal)")
    ax.scatter(gpm, presiones_ensayo_ajustadas, color="#E2131D", zorder=3)

    # Referencias NFPA 25 — no son datos medidos, son los dos puntos que
    # define la norma: el punto nominal (100% del caudal, a la presión
    # nominal de fábrica) y el mínimo aprobado en sobrecarga (150% del
    # caudal, 65% de esa misma presión nominal). Se marcan con una cruz
    # en un color y símbolo que no usa ninguna otra serie del gráfico,
    # para que se lean como referencia y no como una curva más.
    gpm_nominal, presion_nominal = gpm[2], presiones_fabrica[2]
    gpm_sobrecarga = gpm[3]
    presion_minima_nfpa = presion_nominal * 0.65
    ax.scatter(
        [gpm_nominal, gpm_sobrecarga], [presion_nominal, presion_minima_nfpa],
        color="#6B32C9", marker="x", s=90, linewidths=2.2, zorder=5, label="Referencia",
    )
    ax.annotate(
        "100%", (gpm_nominal, presion_nominal), textcoords="offset points", xytext=(8, 6),
        fontsize=8, color="#6B32C9", fontweight="bold",
    )
    ax.annotate(
        "65%", (gpm_sobrecarga, presion_minima_nfpa), textcoords="offset points", xytext=(8, 6),
        fontsize=8, color="#6B32C9", fontweight="bold",
    )

    ax.set_xlabel("Caudal (GPM)")
    ax.set_ylabel("Presión neta (PSI)")
    ax.set_xticks(gpm)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(loc="upper right", fontsize=8)
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

    def titulo_seccion(texto):
        """Barra negra + filete rojo debajo, texto en blanco, de punta a
        punta de la hoja — calcada del encabezado del documento, igual que
        en las pantallas de carga/ficha."""
        return _BandaSeccion(texto)

    def tabla_identificacion(pares):
        """pares: lista de (label, valor) -> grilla de 2 columnas sin bordes,
        ancho total ANCHO_CONTENIDO (igual que el resto de las tablas del
        documento). Dos columnas en vez de tres para que "Lugar" (cliente
        + instalación, el valor más largo de la ficha) entre siempre en
        una sola línea."""
        filas, fila = [], []
        for label, valor in pares:
            fila.append(Paragraph(f"<font size=6.5 color='#6B7280'>{label.upper()}</font><br/><b>{valor}</b>", celda))
            if len(fila) == 2:
                filas.append(fila)
                fila = []
        if fila:
            fila += [""] * (2 - len(fila))
            filas.append(fila)
        t = Table(filas, colWidths=[ANCHO_CONTENIDO / 2] * 2)
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        return t

    elementos = []
    elementos.append(Paragraph("Ensayo de curva de caudal — NFPA 25", titulo))
    elementos.append(Spacer(1, 0.3 * cm))

    tipo_bomba = (equipo.tipo_motor or "-") + (f" · {equipo.motor_potencia_hp} HP" if equipo.motor_potencia_hp else "")
    elementos.append(titulo_seccion("Identificación del ensayo"))
    elementos.append(Spacer(1, 0.3 * cm))
    elementos.append(tabla_identificacion([
        ("Lugar", f"{instalacion.cliente.nombre} — {instalacion.nombre}"),
        ("Modelo", equipo.modelo or "-"),
        ("N° de serie", equipo.serie or "-"),
        ("Tipo de bomba", tipo_bomba),
        ("Fecha", ensayo.fecha_ensayo.strftime("%d/%m/%Y")),
        ("Inspector", (ensayo.creado_por.nombre_completo or ensayo.creado_por.username) if ensayo.creado_por else "-"),
    ]))

    condiciones = []
    if ensayo.temperatura_ambiente is not None:
        condiciones.append(("Temperatura ambiente", f"{ensayo.temperatura_ambiente} °C"))
    if ensayo.presion_atmosferica_mbar is not None:
        condiciones.append(("Presión atmosférica", f"{ensayo.presion_atmosferica_mbar} Mbar"))
    if ensayo.presion_succion_estatica is not None:
        condiciones.append(("Presión succión (estática)", f"{ensayo.presion_succion_estatica} PSI"))
    if condiciones:
        elementos.append(Spacer(1, 0.5 * cm))
        elementos.append(titulo_seccion("Condiciones de prueba"))
        elementos.append(Spacer(1, 0.3 * cm))
        elementos.append(tabla_identificacion(condiciones))
    if ensayo.normativa_aplicable:
        elementos.append(Paragraph(f"<b>Normativa aplicable:</b> {ensayo.normativa_aplicable}", celda))
    elementos.append(Spacer(1, 0.3 * cm))

    estilo_tabla_base = estilo_tabla_encabezado()

    # ---- Curva de fábrica (filas por punto, igual que la pantalla) ----
    if curva_fabrica:
        titulo_fabrica = f"Curva de fábrica (referencia) — RPM nominal: {curva_fabrica.rpm_nominal}"
        elementos.append(Spacer(1, 0.5 * cm))
        elementos.append(titulo_seccion(titulo_fabrica))
        elementos.append(Spacer(1, 0.3 * cm))
        _, presiones_fabrica = curva_fabrica.puntos()
        potencias_fabrica = curva_fabrica.potencias()
        filas_fabrica = [["Caudal (%)", "Caudal (GPM)", "RPM", "Presión neta (PSI)", "Potencia nominal (kW)"]]
        gpm_fabrica = []
        for i, (pct, factor) in enumerate([(0, 0), (50, 0.5), (100, 1), (150, 1.5)]):
            gpm_punto = round(equipo.caudal_nominal * factor, 0) if equipo.caudal_nominal else "-"
            gpm_fabrica.append(equipo.caudal_nominal * factor if equipo.caudal_nominal else pct)
            filas_fabrica.append([
                f"{pct}%", gpm_punto, curva_fabrica.rpm_nominal, presiones_fabrica[i],
                potencias_fabrica[i] if potencias_fabrica[i] is not None else "-",
            ])
        tabla_fabrica = Table(filas_fabrica, colWidths=[3.1 * cm, 3.3 * cm, 2.8 * cm, 4.4 * cm, 4.4 * cm])
        tabla_fabrica.setStyle(estilo_tabla_base)
        elementos.append(tabla_fabrica)
    else:
        presiones_fabrica = None
        gpm_fabrica = [0, 50, 100, 150]
        elementos.append(Spacer(1, 0.5 * cm))
        elementos.append(titulo_seccion("Curva de fábrica"))
        elementos.append(Spacer(1, 0.3 * cm))
        elementos.append(Paragraph("Este equipo todavía no tiene curva de fábrica cargada.", normal))

    # ---- Ensayo (filas por punto) ----
    elementos.append(Spacer(1, 0.5 * cm))
    elementos.append(titulo_seccion("Ensayo"))
    elementos.append(Spacer(1, 0.3 * cm))
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
    else:
        from app.utils import calcular_presion_ajustada

        ajustadas = [calcular_presion_ajustada(n, r, r) for n, r in zip(netas, rpm)]
        variaciones = [None] * 4

    gpm_ensayo = ensayo.puntos_gpm()
    potencias_absorbidas = ensayo.puntos_potencia_absorbida()

    # Encabezados cortos a propósito — con los 9 valores de una fila de
    # ensayo, la única forma de que entren en una sola línea sin agrandar
    # la tabla más allá del ancho del resto del documento es acortar el
    # texto y bajar la fuente; el pie de la tabla ya aclara las fórmulas.
    encabezado_ensayo = [
        "Caudal (%)", "Caudal (GPM)", "RPM", "P. descarga", "P. succión",
        "P. neta", "P. ajustada", "Variación", "Pot. abs.",
    ]
    filas_ensayo = [[Paragraph(f"<font size=7.5><b>{h}</b></font>", celda) for h in encabezado_ensayo]]
    for i, pct in enumerate([0, 50, 100, 150]):
        filas_ensayo.append([
            f"{pct}%",
            round(gpm_ensayo[i], 0) if gpm_ensayo[i] is not None else "-",
            rpm[i], descargas[i], succiones[i], round(netas[i], 1), ajustadas[i],
            f"{variaciones[i]:+.1f}%" if variaciones[i] is not None else "-",
            potencias_absorbidas[i] if potencias_absorbidas[i] is not None else "s/d",
        ])
    tabla_ensayo = Table(
        filas_ensayo,
        colWidths=[2 * cm, 2.2 * cm, 1.8 * cm, 2.2 * cm, 2 * cm, 2 * cm, 2.2 * cm, 1.8 * cm, 1.8 * cm],
    )
    tabla_ensayo.setStyle(estilo_tabla_base)
    elementos.append(tabla_ensayo)
    elementos.append(Paragraph(
        '<font size=7.5 color="#6B7280">Presión neta = descarga − succión &middot; Presión ajustada = neta × '
        "(RPM nominal / RPM ensayada)² &middot; Variación = (ajustada − fábrica) / fábrica.</font>", normal,
    ))
    elementos.append(Spacer(1, 0.3 * cm))

    # ---- Gráfico ----
    if curva_fabrica:
        netas_redondeadas = [round(n, 1) for n in netas]
        grafico_buffer = _grafico_curvas(gpm_fabrica, presiones_fabrica, ajustadas, netas_redondeadas)
        elementos.append(Spacer(1, 0.5 * cm))
        elementos.append(titulo_seccion("Curva Q–H"))
        elementos.append(Spacer(1, 0.3 * cm))
        elementos.append(Image(grafico_buffer, width=15.5 * cm, height=8 * cm))

    # ---- Criterios NFPA 25 ----
    # Solo se informan los valores medidos contra los límites de la norma —
    # NFPA 25 no "aprueba" nada, es un criterio de referencia. El resultado
    # (aprueba o no) lo redacta el Administrador/Jefe en Comentarios/Validación.
    elementos.append(Spacer(1, 0.5 * cm))
    elementos.append(titulo_seccion("Criterios NFPA 25"))
    elementos.append(Spacer(1, 0.3 * cm))
    validacion = ensayo.validacion_nfpa25()
    if validacion:
        filas_validacion = [["Criterio", "Fórmula", "Valor", "Límite", "Estado"]]
        estilos_fila = []
        for i, (clave, criterio) in enumerate(validacion.items(), start=1):
            estado = "✓ CUMPLE" if criterio["paso"] else "✗ NO CUMPLE"
            filas_validacion.append([
                Paragraph(f"<font size=8.5><b>{NOMBRES_CRITERIO.get(clave, clave)}</b></font>", celda),
                Paragraph(f"<font size=7.5 color='#6B7280'>{criterio['descripcion']}</font>", celda),
                f"{criterio['valor_ensayo']:.1f} PSI",
                f"{criterio['limite']:.1f} PSI",
                estado,
            ])
            color_texto = VERDE if criterio["paso"] else ACCENT
            color_fondo = OK_BG if criterio["paso"] else ACCENT_SOFT
            estilos_fila += [
                ("TEXTCOLOR", (4, i), (4, i), color_texto),
                ("FONTNAME", (4, i), (4, i), "Helvetica-Bold"),
                ("BACKGROUND", (4, i), (4, i), color_fondo),
            ]
        tabla_validacion = Table(filas_validacion, colWidths=[6 * cm, 5.3 * cm, 2.3 * cm, 2.2 * cm, 2.2 * cm])
        tabla_validacion.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), SURFACE_MUTED),
            ("TEXTCOLOR", (0, 0), (-1, 0), INK),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.4, BORDE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (2, 1), (4, -1), "CENTER"),
            *estilos_fila,
        ]))
        elementos.append(tabla_validacion)
    else:
        elementos.append(Paragraph("No se puede comparar contra NFPA 25 sin una curva de fábrica cargada.", normal))

    # ---- Comentarios ----
    if ensayo.comentarios:
        elementos.append(Spacer(1, 0.5 * cm))
        elementos.append(titulo_seccion("Comentarios"))
        elementos.append(Spacer(1, 0.3 * cm))
        elementos.append(Paragraph(ensayo.comentarios.replace("\n", "<br/>"), normal))

    # ---- Validación del Jefe/Administrador (independiente del cálculo) ----
    elementos.append(Spacer(1, 0.5 * cm))
    elementos.append(titulo_seccion("Validación"))
    elementos.append(Spacer(1, 0.3 * cm))
    if ensayo.validado_por:
        validado_por = ensayo.validado_por.nombre_completo or ensayo.validado_por.username
        fecha_val = ensayo.fecha_validacion.strftime("%d/%m/%Y") if ensayo.fecha_validacion else "-"
    else:
        validado_por, fecha_val = "—", "—"
    tabla_validacion_final = Table(
        [["Estado", "Validado por", "Fecha"], [ensayo.estado_revision, validado_por, fecha_val]],
        colWidths=[ANCHO_CONTENIDO / 3] * 3,
    )
    tabla_validacion_final.setStyle(estilo_tabla_base)
    elementos.append(tabla_validacion_final)

    construir(doc, elementos, tipo_doc="Ensayo de curva de caudal")
    return buffer.getvalue()
