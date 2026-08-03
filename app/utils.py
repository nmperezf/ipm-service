from datetime import date

from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Contrato, Presupuesto, Visita


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


def crear_presupuesto(observacion, usuario_id):
    """Crea el Presupuesto de una deficiencia marcada 'requiere
    presupuesto', con código único PRESUP-AAAA-NNNN (incremental por
    empresa y año — pensado para que el cliente lo mencione en el mail de
    solicitud). No hace commit: queda a cargo del caller, junto con el
    resto de los cambios de esa misma request.

    El código tiene un índice único a nivel de base — si dos altas chocan
    en el mismo segundo (condición de carrera improbable a la escala de
    esta app), se reintenta con el siguiente número en vez de romper con
    un error feo."""
    empresa_id = observacion.instalacion.cliente.empresa_id
    anio = date.today().year
    prefijo = f"PRESUP-{anio}-"

    ultimo_error = None
    for _ in range(3):
        ultimo = (
            Presupuesto.query.filter(Presupuesto.codigo.like(f"{prefijo}%"), Presupuesto.empresa_id == empresa_id)
            .order_by(Presupuesto.codigo.desc())
            .first()
        )
        numero = int(ultimo.codigo.rsplit("-", 1)[-1]) + 1 if ultimo else 1
        presupuesto = Presupuesto(
            codigo=f"{prefijo}{numero:04d}",
            empresa_id=empresa_id,
            observacion_id=observacion.id,
            creado_por_id=usuario_id,
        )
        try:
            with db.session.begin_nested():
                db.session.add(presupuesto)
            return presupuesto
        except IntegrityError as exc:
            ultimo_error = exc
    raise ultimo_error


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
    """Puntos para el gráfico de evolución de un campo: la línea, el
    relleno de área (mismo trazado cerrado contra la base) y las
    coordenadas del último punto para destacarlo. Solo necesita al menos
    2 valores numéricos para dibujar algo — si no, todo queda en None."""
    if len(serie) < 2:
        return None, None, None, None, None
    valores = [v for _, v in serie]
    minimo, maximo = min(valores), max(valores)
    rango = (maximo - minimo) or 1
    n = len(serie)
    base = alto - padding
    coords = []
    for i, (_, v) in enumerate(serie):
        x = padding + (ancho - 2 * padding) * (i / (n - 1))
        y = base - (alto - 2 * padding) * ((v - minimo) / rango)
        coords.append((x, y))
    puntos = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = f"{puntos} {coords[-1][0]:.1f},{base:.1f} {coords[0][0]:.1f},{base:.1f}"
    punto_final = {"x": round(coords[-1][0], 1), "y": round(coords[-1][1], 1)}
    return puntos, minimo, maximo, area, punto_final


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
                puntos, minimo, maximo, area, punto_final = polilinea_svg(serie)
                campos_numericos.append(
                    {
                        "label": campo["label"],
                        "serie": serie,
                        "puntos": puntos,
                        "minimo": minimo,
                        "maximo": maximo,
                        "area": area,
                        "punto_final": punto_final,
                    }
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


def curva_suavizada(caudales, presiones, n_puntos=40):
    """Ajusta una parábola (P = A + B·Q + C·Q², la forma típica de la curva
    de una bomba centrífuga) a los 4 puntos reales (0/50/100/150%) y
    devuelve (xs, ys) muestreados densamente, para dibujar una curva suave
    en vez de unir los puntos con líneas rectas. Se usa tanto en el PDF
    (matplotlib) como en los gráficos web (Chart.js le recibe estos mismos
    puntos ya calculados)."""
    import numpy as np

    coeficientes = np.polyfit(caudales, presiones, 2)
    xs = np.linspace(min(caudales), max(caudales), n_puntos)
    ys = np.polyval(coeficientes, xs)
    return xs.tolist(), [round(float(y), 2) for y in ys]


def equipos_por_categoria(instalacion):
    """Equipos de la instalación agrupados por categoría de TipoEquipo
    (misma agrupación que categorias_equipo_agrupadas), para las tarjetas
    de 'Información de Instalación'. Cada tarjeta es solo un título con la
    cantidad — el detalle de cada equipo vive en su propia ficha."""
    from app.models import CATEGORIAS_EQUIPO_ORDEN, TipoEquipo

    tipo_a_categoria = {t.nombre: t.categoria for t in TipoEquipo.query.all()}
    grupos = {}
    for equipo in instalacion.equipos:
        categoria = tipo_a_categoria.get(equipo.tipo, "Otros equipos")
        grupos.setdefault(categoria, []).append(equipo)

    orden = [c for c in CATEGORIAS_EQUIPO_ORDEN if c in grupos]
    orden += sorted(c for c in grupos if c not in CATEGORIAS_EQUIPO_ORDEN)
    return [(categoria, grupos[categoria]) for categoria in orden]


def armar_campos_desde_formulario(form):
    """Reconstruye la lista de campos (schema_json) a partir de los inputs
    repetidos del constructor dinámico."""
    labels = form.getlist("campo_label")
    tipos = form.getlist("campo_tipo")
    opciones_list = form.getlist("campo_opciones")
    normas_list = form.getlist("campo_norma")

    campos = []
    usados = set()
    for label, tipo, opciones_str, norma in zip(labels, tipos, opciones_list, normas_list):
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
        if norma and norma.strip():
            campo["norma"] = norma.strip()
        campos.append(campo)
    return campos


def sugerir_referencia_nfpa(label, tipo_equipo=None, categoria=None):
    """Sugiere (vía IA) una referencia normativa NFPA para un campo de
    checklist, a partir de su etiqueta y del tipo/categoría de equipo al
    que aplica. Es solo un borrador para que quien arma el checklist lo
    revise contra la norma real antes de guardarlo — nunca se carga solo.
    Devuelve (cita, nota). Lanza RuntimeError con un mensaje ya pensado
    para mostrarle al usuario si no se pudo generar la sugerencia."""
    import json as json_module

    import anthropic
    from flask import current_app

    api_key = current_app.config.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("No hay una ANTHROPIC_API_KEY configurada en el servidor.")

    contexto = f'Campo del checklist: "{label}"'
    if tipo_equipo:
        contexto += f"\nTipo de equipo: {tipo_equipo}"
    if categoria:
        contexto += f"\nCategoría: {categoria}"

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=500,
            system=(
                "Sos un experto en normas NFPA para sistemas de protección contra "
                "incendios (NFPA 20, 25, 13, 14, 72), usadas como referencia en "
                "Uruguay. Te dan la etiqueta de un campo de un checklist de "
                "inspección/mantenimiento periódico, y el tipo/categoría de equipo "
                "al que aplica. Sugerí la referencia normativa (norma + "
                "artículo/sección) que más probablemente exige ese punto de "
                "verificación. Si no estás razonablemente seguro del número de "
                "artículo exacto, sugerí solo la norma general (ej. 'NFPA 25') sin "
                "inventar una sección, y decilo en la nota."
            ),
            output_config={
                "effort": "low",
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "cita": {
                                "type": "string",
                                "description": "Norma y, si corresponde, artículo/sección. Ej: 'NFPA 25 §8.3.1' o solo 'NFPA 25'.",
                            },
                            "nota": {
                                "type": "string",
                                "description": "Aclaración breve de por qué, o advertencia si no hay certeza del artículo exacto.",
                            },
                        },
                        "required": ["cita", "nota"],
                        "additionalProperties": False,
                    },
                },
            },
            messages=[{"role": "user", "content": contexto}],
        )
    except anthropic.APIError:
        raise RuntimeError("No se pudo consultar el modelo. Probá de nuevo en un momento.")

    if response.stop_reason == "refusal":
        raise RuntimeError("El modelo no pudo generar una sugerencia para este campo.")

    texto = next((b.text for b in response.content if b.type == "text"), None)
    if not texto:
        raise RuntimeError("El modelo no devolvió una sugerencia utilizable.")
    datos = json_module.loads(texto)
    return datos["cita"], datos.get("nota", "")
