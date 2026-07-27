"""Generación de PDF del ensayo de curva de caudal (NFPA 25): tabla de la
curva de fábrica, tabla del ensayo, gráfico superpuesto y los 3 criterios
de la norma como referencia — sin un veredicto automático de aprobado/no
aprobado (eso lo redacta el Administrador/Jefe en Comentarios)."""

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.utils import calcular_presion_ajustada, curva_suavizada

AZUL = colors.HexColor("#1A2233")
GRIS = colors.HexColor("#5B6673")
BORDE = colors.HexColor("#D9DEE3")
VERDE = colors.HexColor("#1F8A54")
ROJO = colors.HexColor("#E2131D")


def _grafico_curvas(caudales, presiones_fabrica, presiones_ensayo_ajustadas, presiones_ensayo_sin_ajustar):
    """Dispersión (los 4 puntos reales) + curva suavizada (parábola
    ajustada, ver utils.curva_suavizada) para fábrica, ensayo ajustado a RPM
    nominal y ensayo tal cual se midió (sin ajuste), superpuestas."""
    fig, ax = plt.subplots(figsize=(6.4, 3.6), dpi=150)

    xs_fabrica, ys_fabrica = curva_suavizada(caudales, presiones_fabrica)
    ax.plot(xs_fabrica, ys_fabrica, color="#1A2233", linewidth=2, label="Curva de fábrica")
    ax.scatter(caudales, presiones_fabrica, color="#1A2233", zorder=3)

    xs_sin_ajustar, ys_sin_ajustar = curva_suavizada(caudales, presiones_ensayo_sin_ajustar)
    ax.plot(xs_sin_ajustar, ys_sin_ajustar, color="#B5730A", linewidth=2, linestyle="--", label="Ensayo (sin ajustar)")
    ax.scatter(caudales, presiones_ensayo_sin_ajustar, color="#B5730A", zorder=3, marker="^")

    xs_ensayo, ys_ensayo = curva_suavizada(caudales, presiones_ensayo_ajustadas)
    ax.plot(xs_ensayo, ys_ensayo, color="#E2131D", linewidth=2, label="Ensayo (ajustado a RPM nominal)")
    ax.scatter(caudales, presiones_ensayo_ajustadas, color="#E2131D", zorder=3)

    ax.set_xlabel("Caudal (%)")
    ax.set_ylabel("Presión neta (PSI)")
    ax.set_xticks(caudales)
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
    empresa = instalacion.cliente.empresa

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm
    )

    styles = getSampleStyleSheet()
    titulo = ParagraphStyle("Titulo", parent=styles["Title"], textColor=AZUL, fontSize=17, spaceAfter=2)
    subtitulo = ParagraphStyle("Subtitulo", parent=styles["Normal"], textColor=GRIS, fontSize=10)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=AZUL, fontSize=12, spaceBefore=14, spaceAfter=6)

    elementos = []
    elementos.append(Paragraph(empresa.nombre if empresa else "IPM Service", subtitulo))
    elementos.append(Paragraph("Ensayo de curva de caudal — NFPA 25", titulo))
    elementos.append(
        Paragraph(
            f"{instalacion.cliente.nombre} &middot; {instalacion.nombre} &middot; "
            f"Bomba: {equipo.nombre}"
            + (f" &middot; Modelo {equipo.modelo}" if equipo.modelo else "")
            + (f" &middot; N&deg; serie {equipo.serie}" if equipo.serie else ""),
            subtitulo,
        )
    )
    elementos.append(Paragraph(f"Fecha de ensayo: {ensayo.fecha_ensayo.strftime('%d/%m/%Y')}", subtitulo))
    elementos.append(Spacer(1, 0.4 * cm))

    estilo_tabla_base = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F4F6F8")),
        ("TEXTCOLOR", (0, 0), (-1, 0), AZUL),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]

    caudales = [0, 50, 100, 150]

    # ---- Curva de fábrica ----
    elementos.append(Paragraph("Curva de fábrica", h2))
    if curva_fabrica:
        _, presiones_fabrica = curva_fabrica.puntos()
        filas_fabrica = [["Caudal (%)", "0%", "50%", "100%", "150%"], ["RPM"] + [curva_fabrica.rpm_nominal] * 4]
        filas_fabrica.append(["Presión neta (PSI)"] + presiones_fabrica)
        tabla_fabrica = Table(filas_fabrica, colWidths=[3.5 * cm] + [3.2 * cm] * 4)
        tabla_fabrica.setStyle(TableStyle(estilo_tabla_base))
        elementos.append(tabla_fabrica)
    else:
        presiones_fabrica = None
        elementos.append(Paragraph("Este equipo todavía no tiene curva de fábrica cargada.", styles["Normal"]))

    # ---- Ensayo ----
    elementos.append(Paragraph("Ensayo", h2))
    rpm = ensayo.puntos_rpm()
    netas = ensayo.puntos_netos()
    descargas = [
        ensayo.presion_descarga_punto_0,
        ensayo.presion_descarga_punto_50,
        ensayo.presion_descarga_punto_100,
        ensayo.presion_descarga_punto_150,
    ]
    succiones = [
        ensayo.presion_succion_punto_0,
        ensayo.presion_succion_punto_50,
        ensayo.presion_succion_punto_100,
        ensayo.presion_succion_punto_150,
    ]

    if curva_fabrica:
        ajustadas = ensayo.puntos_ajustados(curva_fabrica.rpm_nominal)
        variaciones = [
            round((aj - fab) / fab * 100, 1) if fab else None for aj, fab in zip(ajustadas, presiones_fabrica)
        ]
    else:
        ajustadas = [calcular_presion_ajustada(n, r, r) for n, r in zip(netas, rpm)]
        variaciones = [None] * 4

    filas_ensayo = [
        ["Caudal (%)", "0%", "50%", "100%", "150%"],
        ["RPM ensayada"] + rpm,
        ["Presión descarga (PSI)"] + descargas,
        ["Presión succión (PSI)"] + succiones,
        ["Presión neta (PSI)"] + [round(n, 1) for n in netas],
        ["Presión neta ajustada (PSI)"] + ajustadas,
        ["Variación vs fábrica"] + [f"{v:+.1f}%" if v is not None else "-" for v in variaciones],
    ]
    tabla_ensayo = Table(filas_ensayo, colWidths=[4 * cm] + [2.85 * cm] * 4)
    tabla_ensayo.setStyle(TableStyle(estilo_tabla_base))
    elementos.append(tabla_ensayo)
    elementos.append(Spacer(1, 0.4 * cm))

    # ---- Gráfico ----
    if curva_fabrica:
        netas_redondeadas = [round(n, 1) for n in netas]
        grafico_buffer = _grafico_curvas(caudales, presiones_fabrica, ajustadas, netas_redondeadas)
        elementos.append(Image(grafico_buffer, width=15 * cm, height=8.4 * cm))

    # ---- Criterios NFPA 25 ----
    # Solo se informan los valores medidos contra los límites de la norma —
    # NFPA 25 no "aprueba" nada, es un criterio de referencia. El resultado
    # (aprueba o no) lo redacta el Administrador/Jefe en Comentarios, más
    # abajo.
    elementos.append(Paragraph("Criterios NFPA 25 (referencia)", h2))
    validacion = ensayo.validacion_nfpa25()
    if validacion:
        filas_validacion = [["Criterio", "Valor del ensayo", "Límite"]]
        for criterio in validacion.values():
            filas_validacion.append(
                [
                    criterio["descripcion"],
                    f"{criterio['valor_ensayo']:.1f}",
                    f"{criterio['limite']:.1f}",
                ]
            )
        tabla_validacion = Table(filas_validacion, colWidths=[9 * cm] + [3.5 * cm] * 2)
        tabla_validacion.setStyle(TableStyle(estilo_tabla_base))
        elementos.append(tabla_validacion)
    else:
        elementos.append(
            Paragraph("No se puede comparar contra NFPA 25 sin una curva de fábrica cargada.", styles["Normal"])
        )

    # ---- Comentarios ----
    if ensayo.comentarios:
        elementos.append(Paragraph("Comentarios", h2))
        elementos.append(Paragraph(ensayo.comentarios.replace("\n", "<br/>"), styles["Normal"]))

    # ---- Validación del Jefe/Administrador (independiente del cálculo) ----
    elementos.append(Spacer(1, 0.4 * cm))
    if ensayo.estado_revision == "Validado":
        texto_revision = f"Validado por {ensayo.validado_por.nombre_completo or ensayo.validado_por.username}"
        color_revision = VERDE
    elif ensayo.estado_revision == "Rechazado":
        texto_revision = f"Rechazado por {ensayo.validado_por.nombre_completo or ensayo.validado_por.username}"
        color_revision = ROJO
    else:
        texto_revision = "Pendiente de revisión por Administrador/Jefe"
        color_revision = GRIS
    if ensayo.fecha_validacion:
        texto_revision += f" el {ensayo.fecha_validacion.strftime('%d/%m/%Y')}"
    estilo_revision = ParagraphStyle("Revision", parent=styles["Normal"], fontSize=9, textColor=color_revision, alignment=1)
    elementos.append(Paragraph(texto_revision, estilo_revision))

    doc.build(elementos)
    return buffer.getvalue()
