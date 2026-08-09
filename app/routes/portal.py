from datetime import date

from flask import Blueprint, abort, render_template
from flask_login import current_user

from app.auth_utils import rol_requerido
from app.models import (
    CLASIFICACIONES_OBSERVACION,
    TIPOS_BOMBA_PRINCIPAL,
    Equipo,
    Observacion,
    Visita,
    categorias_equipo_agrupadas,
)
from app.utils import (
    bloques_equipos_historico,
    checklists_aprobados_de_equipo,
    filas_checklist,
    resumen_visita_por_categoria,
)

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


def _panel_instalacion(instalacion, hoy):
    """Todo lo que necesita el Inicio del portal para una instalación: las
    tarjetas con modal que reemplazan 'Mis equipos'/'Mi contrato' (deficiencia
    crítica, última visita, próxima visita, categorías de equipo)."""
    def_criticas = sorted(
        (
            o
            for o in instalacion.deficiencias
            if not o.resuelto and o.estado_revision == "Aprobada" and o.clasificacion == "Deficiencia crítica"
        ),
        key=lambda o: o.fecha_carga,
        reverse=True,
    )

    ultima = None
    visita_cerrada = (
        Visita.query.filter_by(instalacion_id=instalacion.id, cerrada=True)
        .order_by(Visita.fecha.desc())
        .first()
    )
    if visita_cerrada:
        ids_items = [it.id for it in visita_cerrada.items]
        deficiencias_visita = (
            Observacion.query.filter(
                Observacion.item_visita_id.in_(ids_items), Observacion.estado_revision == "Aprobada"
            ).all()
            if ids_items
            else []
        )
        ultima = {
            "visita": visita_cerrada,
            "resumen": resumen_visita_por_categoria(visita_cerrada),
            "deficiencias": deficiencias_visita,
            "pdf_visible": _checklists_visibles(visita_cerrada),
        }

    proxima_visita = (
        Visita.query.filter(Visita.instalacion_id == instalacion.id, Visita.fecha >= hoy)
        .order_by(Visita.fecha)
        .first()
    )

    grupos_categoria = _grupos_categoria(instalacion)
    categorias = [(nombre, len(lista)) for nombre, lista in grupos_categoria.items()]

    return {
        "instalacion": instalacion,
        "def_criticas": def_criticas,
        "ultima": ultima,
        "proxima": proxima_visita,
        "categorias": categorias,
    }


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

    contratos_todos = [c for inst in cliente.instalaciones for c in inst.contratos]
    contratos_por_vencer = sum(
        1 for c in contratos_todos if c.estado == "Activo" and (c.fecha_fin - hoy).days <= 30
    )

    paneles = [_panel_instalacion(inst, hoy) for inst in cliente.instalaciones]

    return render_template(
        "portal/inicio.html",
        cliente=cliente,
        deficiencias=cliente.deficiencias_abiertas_aprobadas(),
        proximas_visitas=proximas_visitas,
        indicadores=cliente.indicadores(),
        contratos_por_vencer=contratos_por_vencer,
        paneles=paneles,
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


@portal_bp.route("/contratos")
@rol_requerido("Cliente")
def contratos():
    """Qué servicios tiene contratados el cliente y su vigencia, por
    instalación — de solo lectura, nada de edición acá."""
    cliente = _cliente_actual()
    instalaciones_data = [
        {"instalacion": inst, "contratos": sorted(inst.contratos, key=lambda c: c.fecha_inicio, reverse=True)}
        for inst in cliente.instalaciones
    ]
    return render_template("portal/contratos.html", cliente=cliente, instalaciones_data=instalaciones_data)


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

    formularios = sorted(
        (f for item in visita.items for f in item.formularios), key=lambda f: f.fecha_creacion
    )
    grupos = filas_checklist(formularios, incluir_equipo=True)

    return render_template("portal/visita_detalle.html", cliente=cliente, visita=visita, grupos=grupos)


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
    """Histórico de checklists de una categoría entera, un bloque
    colapsable por equipo, ordenados por visita — así no hace falta
    entrar equipo por equipo para ver qué se cargó."""
    cliente = _cliente_actual()
    instalacion = next((i for i in cliente.instalaciones if i.id == instalacion_id), None)
    if not instalacion:
        abort(404)

    grupos_categoria = _grupos_categoria(instalacion)
    if categoria not in grupos_categoria:
        abort(404)

    bloques = bloques_equipos_historico(grupos_categoria[categoria], checklists_aprobados_de_equipo)

    return render_template(
        "portal/equipos_categoria.html",
        cliente=cliente,
        instalacion=instalacion,
        categoria=categoria,
        categorias=[(nombre, len(lista)) for nombre, lista in grupos_categoria.items()],
        bloques=bloques,
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
    grupos = filas_checklist(formularios)

    deficiencias_abiertas = [
        o for o in equipo.deficiencias if not o.resuelto and o.estado_revision == "Aprobada"
    ]

    ultimos_ensayos = []
    if equipo.tipo in TIPOS_BOMBA_PRINCIPAL:
        validados = [e for e in equipo.ensayos_caudal if e.estado_revision == "Validado"]
        ultimos_ensayos = sorted(validados, key=lambda e: e.fecha_ensayo, reverse=True)[:3]

    return render_template(
        "portal/equipo_detalle.html", cliente=cliente, equipo=equipo, grupos=grupos,
        deficiencias_abiertas=deficiencias_abiertas, ultimos_ensayos=ultimos_ensayos,
    )
