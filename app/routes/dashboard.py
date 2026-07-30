from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user

from app.auth_utils import clientes_visibles, destinatarios_posibles_mensaje, rol_requerido
from app.models import (
    CLASIFICACIONES_OBSERVACION,
    Cliente,
    Equipo,
    EnsayoCaudal,
    Instalacion,
    ItemVisita,
    Mensaje,
    Observacion,
    OrdenTrabajo,
    PRIORIDADES_OT,
    Presupuesto,
    ROLES_GESTION,
    Repuesto,
    Usuario,
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
    es_gestion = current_user.rol in ROLES_GESTION

    clientes = clientes_visibles().all()
    ids_clientes = [c.id for c in clientes]

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

    cumplimiento_tendencia = None
    if es_gestion:
        fin_mes_anterior = inicio_mes - timedelta(days=1)
        inicio_mes_anterior = fin_mes_anterior.replace(day=1)
        items_mes_anterior = (
            ItemVisita.query.join(Visita)
            .filter(Visita.id.in_(ids_visitas_visibles))
            .filter(Visita.fecha >= inicio_mes_anterior, Visita.fecha <= fin_mes_anterior)
            .all()
        )
        if items_mes_anterior:
            cumplidos_mes_anterior = sum(1 for it in items_mes_anterior if it.estado == "Cumplido")
            pct_anterior = round((cumplidos_mes_anterior / len(items_mes_anterior)) * 100, 1)
            cumplimiento_tendencia = round(cumplimiento_pct - pct_anterior, 1)

    agenda_semana = (
        _visitas_visibles()
        .filter(Visita.fecha >= hoy, Visita.fecha <= hoy + timedelta(days=7))
        .order_by(Visita.fecha)
        .all()
    )

    ot_query = OrdenTrabajo.query.join(Instalacion).filter(
        Instalacion.cliente_id.in_(ids_clientes),
        OrdenTrabajo.estado.notin_(["Finalizada", "Cancelada"]),
    )
    mis_ot = None
    if current_user.rol == "Técnico":
        # Acceso directo a "mis" OT asignadas, no todas las de la empresa.
        ot_query = ot_query.filter(OrdenTrabajo.tecnico_id == current_user.id)
        mis_ot = sorted(
            ot_query.all(), key=lambda o: (ORDEN_PRIORIDAD.get(o.prioridad, 2), o.fecha_apertura)
        )[:8]
    ot_pendientes = ot_query.count()

    visitas_en_revision = _visitas_visibles().filter(
        Visita.en_revision == True, Visita.cerrada == False  # noqa: E712
    ).count()

    repuestos_criticos = 0
    deficiencias_abiertas = []
    deficiencias_total = 0
    deficiencias_por_clasif = {}
    ensayos_pendientes = []
    ensayos_pendientes_total = 0
    carga_tecnicos = []
    presupuestos_activos = 0
    if es_gestion:
        repuestos_query = Repuesto.query.filter_by(empresa_id=current_user.empresa_id, activo=True)
        repuestos_criticos = sum(1 for r in repuestos_query.all() if r.en_nivel_critico)

        presupuestos_activos = Presupuesto.query.filter(
            Presupuesto.empresa_id == current_user.empresa_id,
            Presupuesto.estado.in_(["Pendiente", "Cotizado", "Aprobado"]),
        ).count()

        deficiencias_query = (
            Observacion.query.join(Instalacion, Observacion.instalacion_id == Instalacion.id)
            .filter(Instalacion.cliente_id.in_(ids_clientes), Observacion.resuelto == False)  # noqa: E712
            .order_by(Observacion.fecha_carga.desc())
        )
        deficiencias_todas = deficiencias_query.all()
        deficiencias_total = len(deficiencias_todas)
        deficiencias_por_clasif = {
            clasif: sum(1 for o in deficiencias_todas if o.clasificacion == clasif)
            for clasif in CLASIFICACIONES_OBSERVACION
        }
        deficiencias_abiertas = deficiencias_todas[:6]

        ensayos_query = (
            EnsayoCaudal.query.join(Equipo, EnsayoCaudal.equipo_id == Equipo.id)
            .join(Instalacion, Equipo.instalacion_id == Instalacion.id)
            .filter(Instalacion.cliente_id.in_(ids_clientes), EnsayoCaudal.estado_revision == "Pendiente")
            .order_by(EnsayoCaudal.fecha_creacion.desc())
        )
        ensayos_todos = ensayos_query.all()
        ensayos_pendientes_total = len(ensayos_todos)
        ensayos_pendientes = ensayos_todos[:6]

        tecnicos = Usuario.query.filter_by(
            empresa_id=current_user.empresa_id, rol="Técnico", activo=True
        ).order_by(Usuario.nombre_completo).all()
        for t in tecnicos:
            ot_tecnico = OrdenTrabajo.query.join(Instalacion).filter(
                Instalacion.cliente_id.in_(ids_clientes),
                OrdenTrabajo.tecnico_id == t.id,
                OrdenTrabajo.estado.notin_(["Finalizada", "Cancelada"]),
            ).all()
            carga_tecnicos.append({
                "usuario": t,
                "abiertas": len(ot_tecnico),
                "urgentes": sum(1 for o in ot_tecnico if o.prioridad == "Urgente"),
            })
        max_carga_tecnico = max((c["abiertas"] for c in carga_tecnicos), default=0)
    else:
        max_carga_tecnico = 0

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
        hoy=hoy,
        es_gestion=es_gestion,
        cumplimiento_pct=cumplimiento_pct,
        cumplimiento_tendencia=cumplimiento_tendencia,
        cumplidos_mes=cumplidos_mes,
        total_mes=total_mes,
        titulo_mes=inicio_mes.strftime("%B %Y"),
        agenda_semana=agenda_semana,
        mis_ot=mis_ot,
        ot_pendientes=ot_pendientes,
        visitas_en_revision=visitas_en_revision,
        repuestos_criticos=repuestos_criticos,
        presupuestos_activos=presupuestos_activos,
        deficiencias_abiertas=deficiencias_abiertas,
        deficiencias_total=deficiencias_total,
        deficiencias_por_clasif=deficiencias_por_clasif,
        ensayos_pendientes=ensayos_pendientes,
        ensayos_pendientes_total=ensayos_pendientes_total,
        carga_tecnicos=carga_tecnicos,
        max_carga_tecnico=max_carga_tecnico,
        mensajes_abiertos=mensajes_abiertos,
        destinatarios_mensaje=destinatarios_mensaje,
        prioridades=PRIORIDADES_OT,
        clientes_para_mensaje=clientes,
        q=q,
        resultados_busqueda=resultados_busqueda,
    )


@dashboard_bp.route("/deficiencias-abiertas")
@rol_requerido("Administrador", "Jefe")
def deficiencias_abiertas_lista():
    """Todas las observaciones sin resolver de los clientes visibles —
    versión completa de la tarjeta expandible del Inicio."""
    ids_clientes = [c.id for c in clientes_visibles().all()]
    deficiencias = (
        Observacion.query.join(Instalacion, Observacion.instalacion_id == Instalacion.id)
        .filter(Instalacion.cliente_id.in_(ids_clientes), Observacion.resuelto == False)  # noqa: E712
        .order_by(Observacion.fecha_carga.desc())
        .all()
    )
    return render_template("dashboard/deficiencias_abiertas.html", deficiencias=deficiencias)


@dashboard_bp.route("/ensayos-pendientes")
@rol_requerido("Administrador", "Jefe")
def ensayos_pendientes_lista():
    """Todos los ensayos (hoy: curva de caudal) pendientes de validación de
    los clientes visibles — versión completa de la tarjeta expandible."""
    ids_clientes = [c.id for c in clientes_visibles().all()]
    ensayos = (
        EnsayoCaudal.query.join(Equipo, EnsayoCaudal.equipo_id == Equipo.id)
        .join(Instalacion, Equipo.instalacion_id == Instalacion.id)
        .filter(Instalacion.cliente_id.in_(ids_clientes), EnsayoCaudal.estado_revision == "Pendiente")
        .order_by(EnsayoCaudal.fecha_creacion.desc())
        .all()
    )
    return render_template("dashboard/ensayos_pendientes.html", ensayos=ensayos)


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


@dashboard_bp.route("/visitas-en-revision")
@rol_requerido("Administrador", "Jefe", "Técnico")
def visitas_en_revision_lista():
    """Visitas que los técnicos ya mandaron a revisión, esperando que
    Administrador/Jefe las apruebe y cierre."""
    visitas = _visitas_visibles().filter(
        Visita.en_revision == True, Visita.cerrada == False  # noqa: E712
    ).order_by(Visita.fecha_enviada_revision).all()
    return render_template("dashboard/visitas_en_revision.html", visitas=visitas)
