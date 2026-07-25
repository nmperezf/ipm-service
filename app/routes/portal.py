from datetime import date

from flask import Blueprint, abort, render_template
from flask_login import current_user

from app.auth_utils import rol_requerido
from app.models import CLASIFICACIONES_OBSERVACION, Visita

portal_bp = Blueprint("portal", __name__, url_prefix="/portal")


def _cliente_actual():
    cliente = current_user.cliente
    if not cliente:
        abort(404)
    return cliente


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
    y visitas Cerradas — nada que todavía esté en revisión o pendiente."""
    cliente = _cliente_actual()
    ids_instalaciones = [i.id for i in cliente.instalaciones]

    visitas = (
        Visita.query.filter(Visita.instalacion_id.in_(ids_instalaciones), Visita.cerrada == True)  # noqa: E712
        .order_by(Visita.fecha.desc())
        .all()
        if ids_instalaciones
        else []
    )

    observaciones = sorted(
        (o for inst in cliente.instalaciones for o in inst.deficiencias if o.estado_revision == "Aprobada"),
        key=lambda o: o.fecha_carga,
        reverse=True,
    )

    return render_template("portal/historico.html", cliente=cliente, visitas=visitas, observaciones=observaciones)
