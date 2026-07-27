from datetime import date

from flask import Blueprint, abort, render_template
from flask_login import current_user

from app.auth_utils import rol_requerido
from app.models import CLASIFICACIONES_OBSERVACION, Equipo, Visita, categorias_equipo_agrupadas
from app.utils import checklists_aprobados_de_equipo, construir_secciones_historico

portal_bp = Blueprint("portal", __name__, url_prefix="/portal")


def _cliente_actual():
    cliente = current_user.cliente
    if not cliente:
        abort(404)
    return cliente


def _checklists_visibles(visita):
    """El cliente ve el detalle de los checklists de una visita solo
    cuando se cumplen las dos cosas: la visita está Cerrada Y su OT
    asociada está Finalizada — no alcanza con una sola."""
    return bool(visita.cerrada and visita.orden_trabajo and visita.orden_trabajo.estado == "Finalizada")


@portal_bp.route("/")
@rol_requerido("Cliente")
def inicio():
    cliente = _cliente_actual()
    hoy = date.today()

    ids_instalaciones = [i.id for i in cliente.instalaciones]
    proximas_visitas = (
        Visita.query.filter(Visita.instalacion_id.in_(ids_instalaciones), Visita.fecha >= hoy).order_by(
            Visita.fecha
        )
        .all()
        if ids_instalaciones
        else []
    )

    return render_template(
        "portal/inicio.html",
        cliente=cliente,
        deficiencias=cliente.deficiencias_abiertas_aprobadas(),
        proximas_visitas=proximas_visitas,
        indicadores=cliente.indicadores(),
    )


@portal_bp.route("/deficiencias/<clasificacion>")
@rol_requerido("Cliente")
def deficiencias(clasificacion):
    if clasificacion not in CLASIFICACIONES_OBSERVACION:
        abort(404)
    cliente = _cliente_actual()
    observaciones = sorted(
        (
            o
            for inst in cliente.instalaciones
            for o in inst.deficiencias
            if not o.resuelto and o.estado_revision == "Aprobada" and o.clasificacion == clasificacion
        ),
        key=lambda o: o.fecha_carga,
        reverse=True,
    )
    return render_template(
        "portal/deficiencias.html", cliente=cliente, observaciones=observaciones, clasificacion=clasificacion
    )


@portal_bp.route("/historico")
@rol_requerido("Cliente")
def historico():
    """Solo lo que ya pasó el control de calidad: observaciones Aprobadas
    (acá, solo las abiertas — las resueltas tienen su propia página) y
    visitas Cerradas — nada que todavía esté en revisión o pendiente."""
    cliente = _cliente_actual()
    ids_instalaciones = [i.id for i in cliente.instalaciones]

    visitas = (
        Visita.query.filter(Visita.instalacion_id.in_(ids_instalaciones), Visita.cerrada == True)  # noqa: E712
        .order_by(Visita.fecha.desc())
        .all()
        if ids_instalaciones
        else []
    )
    for v in visitas:
        v.checklists_visibles = _checklists_visibles(v)

    observaciones_abiertas = sorted(
        (
            o
            for inst in cliente.instalaciones
            for o in inst.deficiencias
            if o.estado_revision == "Aprobada" and not o.resuelto
        ),
        key=lambda o: o.fecha_carga,
        reverse=True,
    )

    return render_template(
        "portal/historico.html", cliente=cliente, visitas=visitas, observaciones=observaciones_abiertas
    )


@portal_bp.route("/historico/resueltas")
@rol_requerido("Cliente")
def observaciones_resueltas():
    """Histórico aparte de observaciones ya resueltas (aprobadas), con su
    propio acceso directo al lado de 'Observaciones' en el histórico."""
    cliente = _cliente_actual()
    observaciones = sorted(
        (
            o
            for inst in cliente.instalaciones
            for o in inst.deficiencias
            if o.estado_revision == "Aprobada" and o.resuelto
        ),
        key=lambda o: o.fecha_resolucion,
        reverse=True,
    )
    return render_template("portal/observaciones_resueltas.html", cliente=cliente, observaciones=observaciones)


@portal_bp.route("/visita/<int:visita_id>")
@rol_requerido("Cliente")
def detalle_visita(visita_id):
    """Detalle de los checklists cargados en una visita — solo visible
    una vez que el Jefe/Administrador cerró la visita Y finalizó la OT."""
    cliente = _cliente_actual()
    visita = Visita.query.get_or_404(visita_id)
    if visita.instalacion.cliente_id != cliente.id:
        abort(403)
    if not _checklists_visibles(visita):
        abort(403)

    secciones = []
    for item in visita.items:
        formularios = []
        for f in item.formularios:
            campos = f.tipo_formulario.campos()
            datos = f.datos()
            valores = [(c["label"], datos.get(c["campo"])) for c in campos]
            formularios.append({"formulario": f, "valores": valores})
        secciones.append({"servicio": item.servicio.nombre, "formularios": formularios})

    return render_template("portal/visita_detalle.html", cliente=cliente, visita=visita, secciones=secciones)


def _grupos_categoria(instalacion):
    """Equipos activos de la instalación agrupados por categoría — mismo
    criterio que la navegación interna (categorias_equipo_agrupadas), pero
    acá se ocultan los equipos dados de baja."""
    categorias = categorias_equipo_agrupadas()
    grupos = {nombre: [] for nombre, _ in categorias}
    for equipo in instalacion.equipos:
        if not equipo.activo:
            continue
        for nombre_categoria, tipos in categorias:
            if equipo.tipo in tipos:
                grupos[nombre_categoria].append(equipo)
                break
    return {nombre: lista for nombre, lista in grupos.items() if lista}


@portal_bp.route("/equipos")
@rol_requerido("Cliente")
def equipos():
    """Una tarjeta por categoría de equipo (Bombas, ECA/Manifold, BIE,
    Otros) y por instalación — mismo lenguaje visual que las tarjetas de
    deficiencias del inicio. Cada tarjeta lleva al listado de esa
    categoría; el detalle de cada equipo vive en su propia ficha."""
    cliente = _cliente_actual()

    instalaciones_data = [
        {"instalacion": inst, "grupos": _grupos_categoria(inst)} for inst in cliente.instalaciones
    ]

    return render_template("portal/equipos.html", cliente=cliente, instalaciones_data=instalaciones_data)


@portal_bp.route("/equipos/instalacion/<int:instalacion_id>/<categoria>")
@rol_requerido("Cliente")
def equipos_categoria(instalacion_id, categoria):
    """Listado liviano (nombre + ubicación) de los equipos de una
    categoría, dentro de una instalación puntual del cliente."""
    cliente = _cliente_actual()
    instalacion = next((i for i in cliente.instalaciones if i.id == instalacion_id), None)
    if not instalacion:
        abort(404)

    grupos = _grupos_categoria(instalacion)
    if categoria not in grupos:
        abort(404)

    return render_template(
        "portal/equipos_categoria.html",
        cliente=cliente, instalacion=instalacion, categoria=categoria, equipos=grupos[categoria],
    )


@portal_bp.route("/equipos/<int:equipo_id>")
@rol_requerido("Cliente")
def equipo_detalle(equipo_id):
    """Ficha de trazabilidad de un equipo — mismo armado que la interna,
    pero solo con los checklists de visitas Cerradas y con OT Finalizada."""
    cliente = _cliente_actual()
    equipo = Equipo.query.get_or_404(equipo_id)
    if equipo.instalacion.cliente_id != cliente.id:
        abort(403)

    formularios = checklists_aprobados_de_equipo(equipo)
    secciones = construir_secciones_historico(formularios)

    deficiencias_abiertas = [
        o for o in equipo.deficiencias if not o.resuelto and o.estado_revision == "Aprobada"
    ]

    ultimos_ensayos = []
    if equipo.tipo == "Bomba":
        validados = [e for e in equipo.ensayos_caudal if e.estado_revision == "Validado"]
        ultimos_ensayos = sorted(validados, key=lambda e: e.fecha_ensayo, reverse=True)[:3]

    return render_template(
        "portal/equipo_detalle.html", cliente=cliente, equipo=equipo, secciones=secciones,
        deficiencias_abiertas=deficiencias_abiertas, ultimos_ensayos=ultimos_ensayos,
    )
