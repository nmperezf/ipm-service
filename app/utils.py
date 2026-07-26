from datetime import date

from app import db
from app.models import Contrato, Visita


def actualizar_vencimientos(hoy=None):
    """Recorre visitas y contratos y actualiza su estado si vencieron.
    Se llama al entrar a cualquier vista de planificación/dashboard, así
    el estado siempre refleja la realidad sin intervención manual."""
    hoy = hoy or date.today()
    for visita in Visita.query.all():
        visita.actualizar_estado_por_vencimiento(hoy=hoy)
    for contrato in Contrato.query.filter_by(activo=True).all():
        contrato.actualizar_estado_por_vencimiento(hoy=hoy)
    db.session.commit()


# ---------------------------------------------------------------------------
# Histórico/trazabilidad de un equipo — compartido entre la ficha interna
# (equipos.detalle, ve todo apenas se carga) y el portal de cliente
# (portal.equipo_detalle, solo ve lo de visitas Cerradas y con OT Finalizada).
# ---------------------------------------------------------------------------


def serie_numerica(formularios, nombre_campo):
    """(fecha, valor) para un campo numérico, en orden cronológico,
    ignorando los formularios donde ese campo quedó vacío o no numérico."""
    serie = []
    for f in formularios:
        valor = f.datos().get(nombre_campo)
        try:
            valor_float = float(valor)
        except (TypeError, ValueError):
            continue
        serie.append((f.fecha_creacion.date(), valor_float))
    return serie


def polilinea_svg(serie, ancho=520, alto=90, padding=12):
    """Puntos para un <polyline> de una gráfica simple, sin dependencias
    de JS: solo necesita al menos 2 valores numéricos para dibujar algo."""
    if len(serie) < 2:
        return None, None, None
    valores = [v for _, v in serie]
    minimo, maximo = min(valores), max(valores)
    rango = (maximo - minimo) or 1
    n = len(serie)
    puntos = []
    for i, (_, v) in enumerate(serie):
        x = padding + (ancho - 2 * padding) * (i / (n - 1))
        y = alto - padding - (alto - 2 * padding) * ((v - minimo) / rango)
        puntos.append(f"{x:.1f},{y:.1f}")
    return " ".join(puntos), minimo, maximo


def construir_secciones_historico(formularios):
    """A partir de una lista de Formulario (ya filtrada por quien llama —
    todos para la ficha interna, solo los de visitas Cerradas+Finalizadas
    para el portal), arma las secciones agrupadas por tipo de formulario
    con su gráfico/tabla de evolución por campo."""
    por_tipo = {}
    for formulario in formularios:
        por_tipo.setdefault(formulario.tipo_formulario, []).append(formulario)

    secciones = []
    for tipo_formulario, lista in por_tipo.items():
        campos_numericos = []
        campos_otros = []
        for campo in tipo_formulario.campos():
            if campo["tipo"] == "numero":
                serie = serie_numerica(lista, campo["campo"])
                puntos, minimo, maximo = polilinea_svg(serie)
                campos_numericos.append(
                    {"label": campo["label"], "serie": serie, "puntos": puntos, "minimo": minimo, "maximo": maximo}
                )
            else:
                historial = [(f.fecha_creacion, f.datos().get(campo["campo"])) for f in reversed(lista)]
                campos_otros.append({"label": campo["label"], "historial": historial})
        secciones.append(
            {"tipo_formulario": tipo_formulario, "campos_numericos": campos_numericos, "campos_otros": campos_otros}
        )
    return secciones


def checklists_aprobados_de_equipo(equipo):
    """Formularios de este equipo que ya pasaron el doble candado del
    portal: la visita que los generó está Cerrada y su OT Finalizada."""
    from app.models import Formulario

    formularios = Formulario.query.filter_by(equipo_id=equipo.id).order_by(Formulario.fecha_creacion).all()
    return [
        f
        for f in formularios
        if f.item_visita
        and f.item_visita.visita.cerrada
        and f.item_visita.visita.orden_trabajo
        and f.item_visita.visita.orden_trabajo.estado == "Finalizada"
    ]


# ---------------------------------------------------------------------------
# Constructor dinámico de campos — compartido entre TipoFormulario (por
# cliente) y ServicioTipo (catálogo por empresa, se importa a un cliente).
# ---------------------------------------------------------------------------

TIPOS_CAMPO = [
    ("texto", "Texto corto"),
    ("texto_largo", "Texto largo"),
    ("numero", "Número"),
    ("fecha", "Fecha"),
    ("booleano", "Sí / No"),
    ("seleccion", "Selección (una opción)"),
    ("multi_seleccion", "Checklist (varias opciones)"),
]


def slugify_campo(texto):
    """Convierte una etiqueta libre en una clave interna segura (sin
    acentos, espacios ni mayúsculas) para usar como nombre de campo."""
    import re
    import unicodedata

    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    texto = texto.lower().strip()
    texto = re.sub(r"[^a-z0-9]+", "_", texto).strip("_")
    return texto or "campo"


# ---------------------------------------------------------------------------
# Curva de caudal (NFPA 25) — cálculos compartidos entre las rutas de
# equipos/curvas y la ficha de sala de bombas.
# ---------------------------------------------------------------------------


def calcular_presion_ajustada(presion_neta, rpm_ensayada, rpm_nominal_fabrica):
    """Corrige la presión neta medida en campo a la RPM nominal de la curva
    de fábrica, por la ley de afinidad de bombas centrífugas (P ∝ RPM²) —
    así se puede comparar un ensayo hecho a otra velocidad. Si la RPM
    ensayada coincide con la de fábrica, es el caso trivial: el ajuste no
    cambia nada."""
    if not rpm_ensayada:
        return round(presion_neta, 1)
    factor = (rpm_nominal_fabrica / rpm_ensayada) ** 2
    return round(presion_neta * factor, 1)


def validar_nfpa25(presiones_netas_ajustadas, presiones_netas_fabrica):
    """Los 3 criterios de aceptación de NFPA 25 para un ensayo de curva de
    caudal, sobre presiones netas ya corregidas a RPM nominal (ver
    calcular_presion_ajustada). Ambas listas van en el orden
    [0%, 50%, 100%, 150%]."""
    p0, _p50, p100, p150 = presiones_netas_ajustadas
    _f0, _f50, f100, _f150 = presiones_netas_fabrica

    limite_1 = round(1.4 * p100, 1)
    limite_2 = round(0.95 * f100, 1)
    limite_3 = round(0.65 * p100, 1)

    return {
        "criterio_1": {
            "paso": p0 <= limite_1,
            "descripcion": "P@0% ≤ 1.4 × P@100%",
            "valor_ensayo": p0,
            "limite": limite_1,
        },
        "criterio_2": {
            "paso": p100 >= limite_2,
            "descripcion": "P@100% ≥ 0.95 × P_fábrica@100%",
            "valor_ensayo": p100,
            "limite": limite_2,
        },
        "criterio_3": {
            "paso": p150 >= limite_3,
            "descripcion": "P@150% ≥ 0.65 × P@100%",
            "valor_ensayo": p150,
            "limite": limite_3,
        },
    }


def _ultimo_ensayo(equipo):
    if not equipo.ensayos_caudal:
        return None
    return max(equipo.ensayos_caudal, key=lambda e: e.fecha_ensayo)


def obtener_resumen_sala(sala_id):
    """Tarjetas superiores de la ficha de sala: cuenta cada bomba una sola
    vez, según el resultado NFPA 25 de su ensayo más reciente."""
    from app.models import SalaBombas

    sala = SalaBombas.query.get(sala_id)
    if not sala:
        return {
            "total_equipos": 0,
            "equipos_aprobados": 0,
            "equipos_rechazados": 0,
            "deficiencias_abiertas": 0,
            "fecha_ultima_inspeccion": None,
        }

    equipos = sala.bombas
    aprobados = 0
    rechazados = 0
    for equipo in equipos:
        ultimo = _ultimo_ensayo(equipo)
        if ultimo is None:
            continue
        resultado = ultimo.resultado_nfpa25()
        if resultado is True:
            aprobados += 1
        elif resultado is False:
            rechazados += 1

    deficiencias_abiertas = sum(
        1 for equipo in equipos for obs in equipo.deficiencias if not obs.resuelto
    )

    return {
        "total_equipos": len(equipos),
        "equipos_aprobados": aprobados,
        "equipos_rechazados": rechazados,
        "deficiencias_abiertas": deficiencias_abiertas,
        "fecha_ultima_inspeccion": sala.fecha_ultima_inspeccion,
    }


def obtener_ultimos_ensayos_por_bomba(sala_id, limit=3):
    """Para la tabla de histórico de cada bomba en la ficha de sala."""
    from app.models import SalaBombas

    sala = SalaBombas.query.get(sala_id)
    if not sala:
        return []

    resultado = []
    for equipo in sala.bombas:
        ensayos_ordenados = sorted(equipo.ensayos_caudal, key=lambda e: e.fecha_ensayo, reverse=True)[:limit]
        lista_ensayos = []
        for ensayo in ensayos_ordenados:
            resultado_nfpa = ensayo.resultado_nfpa25()
            var_pct = None
            if equipo.curva_fabrica and equipo.curva_fabrica.punto_100_presion:
                ajustada_100 = ensayo.puntos_ajustados(equipo.curva_fabrica.rpm_nominal)[2]
                var_pct = round(
                    (ajustada_100 - equipo.curva_fabrica.punto_100_presion)
                    / equipo.curva_fabrica.punto_100_presion
                    * 100,
                    1,
                )
            if resultado_nfpa is True:
                estado = "Aprobado"
            elif resultado_nfpa is False:
                estado = "Rechazado"
            else:
                estado = "Sin curva de fábrica"
            lista_ensayos.append(
                {
                    "fecha": ensayo.fecha_ensayo,
                    "presion_100": ensayo.presion_neta_punto_100,
                    "var_pct": var_pct,
                    "estado": estado,
                    "ensayo_id": ensayo.id,
                }
            )
        resultado.append({"bomba_id": equipo.id, "bomba_nombre": equipo.nombre, "ensayos": lista_ensayos})
    return resultado


def obtener_datos_grafico_evolucion(sala_id):
    """Serie por bomba de la presión neta @100% por año (el último ensayo
    de cada año, si hubo más de uno), para el gráfico de tendencia."""
    from app.models import SalaBombas

    sala = SalaBombas.query.get(sala_id)
    if not sala:
        return {"bombas": [], "años": [], "datos": {}}

    años = set()
    por_bomba = {}
    for equipo in sala.bombas:
        por_año = {}
        for ensayo in equipo.ensayos_caudal:
            año = ensayo.fecha_ensayo.year
            if año not in por_año or ensayo.fecha_ensayo > por_año[año].fecha_ensayo:
                por_año[año] = ensayo
        if not por_año:
            continue
        por_bomba[equipo.nombre] = por_año
        años.update(por_año.keys())

    años_ordenados = sorted(años)
    datos = {
        nombre: [por_año[a].presion_neta_punto_100 if a in por_año else None for a in años_ordenados]
        for nombre, por_año in por_bomba.items()
    }
    return {"bombas": list(por_bomba.keys()), "años": años_ordenados, "datos": datos}


def obtener_acciones_recomendadas(sala_id):
    """Heurística simple para la sección "Acciones recomendadas" de la
    ficha de sala: no hay un modelo de "acción" separado, se infiere de los
    ensayos/curvas ya cargados (rechazado -> urgente, sin ensayo este año
    -> programar, sin curva de fábrica -> revisión)."""
    from app.models import SalaBombas

    sala = SalaBombas.query.get(sala_id)
    if not sala:
        return {"urgentes": [], "programadas": [], "en_revision": []}

    hoy = date.today()
    urgentes, programadas, en_revision = [], [], []
    for equipo in sala.bombas:
        if not equipo.curva_fabrica:
            en_revision.append(
                {
                    "equipo": equipo.nombre,
                    "motivo": "Sin curva de fábrica cargada — no se puede validar contra NFPA 25.",
                    "plazo": "Antes del próximo ensayo",
                }
            )
            continue

        ultimo = _ultimo_ensayo(equipo)
        if ultimo and ultimo.resultado_nfpa25() is False:
            urgentes.append(
                {
                    "equipo": equipo.nombre,
                    "motivo": f"El ensayo del {ultimo.fecha_ensayo.strftime('%d/%m/%Y')} no aprobó NFPA 25.",
                    "plazo": "Inmediato",
                }
            )
        if not ultimo or ultimo.fecha_ensayo.year < hoy.year:
            programadas.append(
                {
                    "equipo": equipo.nombre,
                    "motivo": "Sin ensayo de caudal registrado este año.",
                    "plazo": f"Antes de fin de {hoy.year}",
                }
            )
    return {"urgentes": urgentes, "programadas": programadas, "en_revision": en_revision}


def armar_campos_desde_formulario(form):
    """Reconstruye la lista de campos (schema_json) a partir de los inputs
    repetidos del constructor dinámico."""
    labels = form.getlist("campo_label")
    tipos = form.getlist("campo_tipo")
    opciones_list = form.getlist("campo_opciones")

    campos = []
    usados = set()
    for label, tipo, opciones_str in zip(labels, tipos, opciones_list):
        label = (label or "").strip()
        if not label:
            continue
        slug_base = slugify_campo(label)
        slug = slug_base
        n = 1
        while slug in usados:
            n += 1
            slug = f"{slug_base}_{n}"
        usados.add(slug)

        campo = {"campo": slug, "tipo": tipo, "label": label}
        if tipo in ("seleccion", "multi_seleccion") and opciones_str.strip():
            campo["opciones"] = [o.strip() for o in opciones_str.split(",") if o.strip()]
        campos.append(campo)
    return campos
