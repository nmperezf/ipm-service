from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user

from app.auth_utils import clientes_visibles, destinatarios_posibles_mensaje, rol_requerido
from app.models import (
    CLASIFICACIONES_OBSERVACION,
    Cliente,
    Instalacion,
    ItemVisita,
    Mensaje,
    OrdenTrabajo,
    PRIORIDADES_OT,
    Repuesto,
    Visita,
)
from app.utils import actualizar_vencimientos

dashboard_bp = Blueprint("dashboard", __name__)

ORDEN_PRIORIDAD = {"Urgente": 0, "Alta": 1, "Media": 2, "Baja": 3}


def _visitas_visibles():
    """Visitas de los clientes visibles para el usuario logueado."""
    ids_clientes = [c.id for c in clientes_visibles().all()]
    return (
        Visita.query.join(Visita.instalacion)
        .filter(Instalacion.cliente_id.in_(ids_clientes))
    )


@dashboard_bp.route("/")
def inicio():
    if current_user.rol == "Super Admin":
        # El dashboard operativo mezcla datos de todas las empresas — no
        # tiene sentido para el rol de soporte. Su "inicio" es la lista
        # de empresas que administra.
        return redirect(url_for("empresas.listar"))

    if current_user.rol == "Cliente":
        return redirect(url_for("portal.inicio"))

    actualizar_vencimientos()
    hoy = date.today()

    clientes = clientes_visibles().all()

    # Resumen agregado de deficiencias: el detalle por clasificación vive
    # en la ficha de cada cliente; acá un radar general por cada tipo.
    clientes_con_novedad = {
        clasif: sum(1 for c in clientes if c.deficiencias_abiertas().get(clasif))
        for clasif in CLASIFICACIONES_OBSERVACION
    }

    visitas_vencidas = _visitas_visibles().filter(Visita.estado == "Vencido").count()

    inicio_mes = hoy.replace(day=1)
    fin_mes = inicio_mes + relativedelta(months=1) - timedelta(days=1)
    ids_visitas_visibles = [v.id for v in _visitas_visibles().all()]
    items_mes = (
        ItemVisita.query.join(Visita)
        .filter(Visita.id.in_(ids_visitas_visibles))
        .filter(Visita.fecha >= inicio_mes, Visita.fecha <= fin_mes)
        .all()
    )
    total_mes = len(items_mes)
    cumplidos_mes = sum(1 for it in items_mes if it.estado == "Cumplido")
    cumplimiento_pct = round((cumplidos_mes / total_mes) * 100, 1) if total_mes else 0.0

    agenda_semana = (
        _visitas_visibles()
        .filter(Visita.fecha >= hoy, Visita.fecha <= hoy + timedelta(days=7))
        .order_by(Visita.fecha)
        .all()
    )

    ot_query = OrdenTrabajo.query.join(Instalacion).filter(
        Instalacion.cliente_id.in_([c.id for c in clientes]),
        OrdenTrabajo.estado.notin_(["Finalizada", "Cancelada"]),
    )
    if current_user.rol == "Técnico":
        # Acceso directo a "mis" OT asignadas, no todas las de la empresa.
        ot_query = ot_query.filter(OrdenTrabajo.tecnico_id == current_user.id)
    ot_pendientes = ot_query.count()

    visitas_en_revision = _visitas_visibles().filter(
        Visita.en_revision == True, Visita.cerrada == False  # noqa: E712
    ).count()

    if current_user.rol == "Super Admin":
        repuestos_query = Repuesto.query
    else:
        repuestos_query = Repuesto.query.filter_by(empresa_id=current_user.empresa_id)
    repuestos_criticos = sum(1 for r in repuestos_query.filter_by(activo=True).all() if r.en_nivel_critico)

    # Mensajes donde el usuario logueado participa (como remitente o
    # destinatario) — chat interno acotado entre el staff de la empresa.
    mensajes_abiertos = sorted(
        Mensaje.query.filter(
            (Mensaje.remitente_id == current_user.id) | (Mensaje.destinatario_id == current_user.id),
            Mensaje.resuelto == False,  # noqa: E712
        ).order_by(Mensaje.fecha_carga.desc()).all(),
        key=lambda m: ORDEN_PRIORIDAD.get(m.prioridad, 2),
    )
    destinatarios_mensaje = destinatarios_posibles_mensaje()

    q = request.args.get("q", "").strip()
    resultados_busqueda = []
    if q:
        resultados_busqueda = clientes_visibles().filter(Cliente.nombre.ilike(f"%{q}%")).order_by(Cliente.nombre).all()

    return render_template(
        "dashboard/inicio.html",
        clientes_con_novedad=clientes_con_novedad,
        visitas_vencidas=visitas_vencidas,
        cumplimiento_pct=cumplimiento_pct,
        cumplidos_mes=cumplidos_mes,
        total_mes=total_mes,
        titulo_mes=inicio_mes.strftime("%B %Y"),
        agenda_semana=agenda_semana,
        ot_pendientes=ot_pendientes,
        visitas_en_revision=visitas_en_revision,
        repuestos_criticos=repuestos_criticos,
        mensajes_abiertos=mensajes_abiertos,
        destinatarios_mensaje=destinatarios_mensaje,
        prioridades=PRIORIDADES_OT,
        clientes_para_mensaje=clientes,
        q=q,
        resultados_busqueda=resultados_busqueda,
    )


@dashboard_bp.route("/visitas-vencidas")
@rol_requerido("Administrador", "Jefe", "Técnico")
def visitas_vencidas_lista():
    visitas = _visitas_visibles().filter(Visita.estado == "Vencido").order_by(Visita.fecha).all()
    return render_template("dashboard/visitas_vencidas.html", visitas=visitas)


@dashboard_bp.route("/cumplimiento-mensual")
@rol_requerido("Administrador", "Jefe", "Técnico")
def cumplimiento_mensual():
    """Detalle de la tarjeta de cumplimiento: todos los servicios del mes,
    cumplidos y no (pendientes o cancelados), para ver de un vistazo qué
    clientes tienen algo sin resolver este mes."""
    actualizar_vencimientos()
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)
    fin_mes = inicio_mes + relativedelta(months=1) - timedelta(days=1)

    ids_visitas_visibles = [v.id for v in _visitas_visibles().all()]
    items_mes = (
        ItemVisita.query.join(Visita)
        .filter(Visita.id.in_(ids_visitas_visibles))
        .filter(Visita.fecha >= inicio_mes, Visita.fecha <= fin_mes)
        .order_by(Visita.fecha)
        .all()
    )

    return render_template(
        "dashboard/cumplimiento_mensual.html",
        items=items_mes,
        titulo_mes=inicio_mes.strftime("%B %Y"),
    )


@dashboard_bp.route("/clientes-con-novedad/<clasificacion>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def clientes_con_novedad_lista(clasificacion):
    """Radar general: qué clientes tienen novedades abiertas de esta
    clasificación (crítica, no crítica, desactivación o comentario)."""
    clientes = [
        c for c in clientes_visibles().order_by(Cliente.nombre).all()
        if c.deficiencias_abiertas().get(clasificacion)
    ]
    return render_template(
        "dashboard/clientes_con_novedad.html", clientes=clientes, clasificacion=clasificacion
    )


@dashboard_bp.route("/visitas-en-revision")
@rol_requerido("Administrador", "Jefe", "Técnico")
def visitas_en_revision_lista():
    """Visitas que los técnicos ya mandaron a revisión, esperando que
    Administrador/Jefe las apruebe y cierre."""
    visitas = _visitas_visibles().filter(
        Visita.en_revision == True, Visita.cerrada == False  # noqa: E712
    ).order_by(Visita.fecha_enviada_revision).all()
    return render_template("dashboard/visitas_en_revision.html", visitas=visitas)
