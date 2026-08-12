from datetime import date

from flask import request
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Contrato, Foto, Formulario, Presupuesto, Visita, categorias_equipo_agrupadas


def es_ajax():
    """True cuando el pedido viene del JS de ventana flotante (ver
    static/js/modal-form.js), no de una navegación de página completa —
    para que la misma ruta pueda devolver el formulario/resultado como
    fragmento (sin el layout de base.html) o como página entera."""
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


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
        if isinstance(valor, dict):
            valor = valor.get("valor")
        try:
            valor_float = float(valor)
        except (TypeError, ValueError):
            continue
        serie.append((f.fecha_creacion.date(), valor_float))
    return serie


MESES_ABREV = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def polilinea_svg(serie, ancho=520, alto=90, padding=12):
    """Puntos para el gráfico de evolución de un campo: la línea, el
    relleno de área (mismo trazado cerrado contra la base), las
    coordenadas del último punto para destacarlo, y el detalle de cada
    punto (x/y + mes abreviado, para poner una referencia debajo de cada
    uno). Solo necesita al menos 2 valores numéricos para dibujar algo —
    si no, todo queda en None."""
    if len(serie) < 2:
        return None, None, None, None, None, []
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
    puntos_detalle = [
        {"x": round(x, 1), "y": round(y, 1), "mes": MESES_ABREV[fecha.month - 1]}
        for (fecha, _), (x, y) in zip(serie, coords)
    ]
    return puntos, minimo, maximo, area, punto_final, puntos_detalle


def resumen_visita_por_categoria(visita):
    """Cuántos equipos se revisaron (tienen al menos un formulario cargado
    en esta visita) por categoría, sin repetir el detalle equipo por
    equipo — usado en el cierre de visita, el PDF de devolución y el
    portal del cliente."""
    ids_items = [it.id for it in visita.items]
    formularios = Formulario.query.filter(Formulario.item_visita_id.in_(ids_items)).all() if ids_items else []

    resumen = []
    for nombre_categoria, tipos_equipo in categorias_equipo_agrupadas():
        equipos_ids = {
            f.equipo_id for f in formularios if f.equipo and f.equipo.tipo in tipos_equipo
        }
        if equipos_ids:
            resumen.append({"categoria": nombre_categoria, "equipos_revisados": len(equipos_ids)})

    # Formularios generales (no ligados a un equipo puntual, ej. checklist mensual)
    generales = [f for f in formularios if not f.equipo_id]
    if generales:
        resumen.append({"categoria": "Otros formularios", "equipos_revisados": len(generales)})

    return resumen


def filas_checklist(formularios, incluir_equipo=False):
    """A partir de formularios de UN equipo (o de una visita puntual, si
    incluir_equipo=True) ya filtrados y ordenados ascendente por fecha
    por quien llama, arma un bloque por tipo de checklist: una tabla con
    una fila por carga (más reciente arriba) y, para cada campo
    numérico, los datos ya listos para el gráfico de evolución — pensado
    para mostrar el histórico entero "uno atrás de otro" sin tener que
    entrar a cada checklist por separado.

    incluir_equipo agrega el equipo de cada fila al resultado, para
    vistas que mezclan varios equipos (ej. los checklists de una visita
    puntual, donde un mismo tipo de formulario puede repetirse por
    varios equipos del mismo tipo)."""
    por_tipo = {}
    for formulario in formularios:
        por_tipo.setdefault(formulario.tipo_formulario, []).append(formulario)

    # Fotos ligadas a un punto puntual (campo_formulario) de alguno de estos
    # formularios, agrupadas por (item_visita, equipo, campo) -- una sola
    # consulta acá en vez de una por cada campo con foto de cada fila.
    item_visita_ids = {f.item_visita_id for f in formularios}
    fotos_por_clave = {}
    if item_visita_ids:
        for foto in Foto.query.filter(
            Foto.item_visita_id.in_(item_visita_ids), Foto.campo_formulario.isnot(None)
        ).all():
            fotos_por_clave.setdefault((foto.item_visita_id, foto.equipo_id, foto.campo_formulario), []).append(foto)

    grupos = []
    for tipo_formulario, lista in por_tipo.items():
        campos = tipo_formulario.campos()

        filas = []
        for f in reversed(lista):
            datos = f.datos()
            valores = [(campo, datos.get(campo["campo"])) for campo in campos]
            fotos = {
                campo["campo"]: fotos_por_clave[(f.item_visita_id, f.equipo_id, campo["campo"])]
                for campo in campos
                if (f.item_visita_id, f.equipo_id, campo["campo"]) in fotos_por_clave
            }
            filas.append({"formulario": f, "equipo": f.equipo, "valores": valores, "fotos": fotos})

        # El gráfico asume una sola serie por campo evolucionando en el
        # tiempo — no tiene sentido si incluir_equipo mezcla varios
        # equipos del mismo tipo en la misma visita (compararía lecturas
        # de equipos distintos como si fueran el mismo a través del
        # tiempo). Se omite directamente en ese caso.
        campos_numericos = []
        if not incluir_equipo:
            for campo in campos:
                if campo["tipo"] != "numero":
                    continue
                serie = serie_numerica(lista, campo["campo"])
                puntos, minimo, maximo, area, punto_final, puntos_detalle = polilinea_svg(serie)
                if not puntos:
                    continue
                campos_numericos.append({"label": campo["label"], "area": area, "puntos_detalle": puntos_detalle})

        grupos.append(
            {
                "tipo_formulario": tipo_formulario,
                "campos": campos,
                "filas": filas,
                "campos_numericos": campos_numericos,
                "incluir_equipo": incluir_equipo,
            }
        )
    return grupos


def bloques_equipos_historico(equipos, obtener_formularios):
    """Un bloque por equipo (con sus grupos de filas_checklist), para
    listar el histórico de una categoría entera —Sala de bombas, ECA,
    etc.— uno atrás de otro. obtener_formularios(equipo) define qué
    formularios entran: todos para la ficha interna, solo los de
    visitas Cerradas+Finalizadas para el portal (ver
    checklists_aprobados_de_equipo)."""
    bloques = []
    for equipo in equipos:
        formularios = obtener_formularios(equipo)
        bloques.append(
            {
                "equipo": equipo,
                "grupos": filas_checklist(formularios),
                "ultimo": max((f.fecha_creacion for f in formularios), default=None),
            }
        )
    return bloques


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
    ("estado", "Punto de inspección (Aprobado/Observado/Deficiencia/N-A)"),
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
    repetidos del constructor dinámico. con_estado viene de un <select>
    Sí/No (no un checkbox) para que getlist() no pierda la alineación por
    índice con el resto de las filas -- un checkbox sin marcar no manda
    ningún valor, lo que correría el resto de las columnas de esa fila."""
    labels = form.getlist("campo_label")
    tipos = form.getlist("campo_tipo")
    opciones_list = form.getlist("campo_opciones")
    normas_list = form.getlist("campo_norma")
    descripciones_list = form.getlist("campo_descripcion")
    unidades_list = form.getlist("campo_unidad")
    con_estado_list = form.getlist("campo_con_estado")
    requiere_foto_list = form.getlist("campo_requiere_foto")

    campos = []
    usados = set()
    filas = zip(
        labels, tipos, opciones_list, normas_list, descripciones_list, unidades_list,
        con_estado_list, requiere_foto_list,
    )
    for label, tipo, opciones_str, norma, descripcion, unidad, con_estado, requiere_foto in filas:
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
        if descripcion and descripcion.strip():
            campo["descripcion"] = descripcion.strip()
        if tipo == "numero" and unidad and unidad.strip():
            campo["unidad"] = unidad.strip()
        if tipo in ("numero", "texto") and con_estado == "1":
            campo["con_estado"] = True
        if requiere_foto == "1":
            campo["requiere_foto"] = True
        campos.append(campo)
    return campos
