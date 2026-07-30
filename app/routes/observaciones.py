from datetime import date, datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import (
    rol_requerido,
    verificar_acceso_cliente,
    verificar_escritura_cliente,
    verificar_visita_editable,
)
from app.models import CLASIFICACIONES_OBSERVACION, Equipo, Instalacion, ItemVisita, Observacion
from app.notificaciones import notificar_gestion, notificar_usuario

observaciones_bp = Blueprint("observaciones", __name__, url_prefix="/observaciones")


def _parse_fecha(valor, por_defecto=None):
    if not valor:
        return por_defecto or date.today()
    return datetime.strptime(valor, "%Y-%m-%d").date()


@observaciones_bp.route("/nueva/<int:instalacion_id>", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def nueva(instalacion_id):
    """Carga manual de una observación (deficiencia/desactivación), pensada
    también para migrar el historial que ya tenés de tus clientes actuales.
    Queda en revisión 'Pendiente' hasta que un Administrador la apruebe."""
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_escritura_cliente(instalacion.cliente)
    item_id = request.values.get("item_id", type=int)
    item = ItemVisita.query.get(item_id) if item_id else None
    if item:
        verificar_visita_editable(item.visita)
    equipo_id = request.values.get("equipo_id", type=int)
    equipo = Equipo.query.get(equipo_id) if equipo_id else None

    if request.method == "POST":
        observacion = Observacion(
            instalacion_id=instalacion.id,
            item_visita_id=item.id if item else None,
            equipo_id=equipo.id if equipo else None,
            clasificacion=request.form["clasificacion"],
            descripcion=request.form["descripcion"],
            fecha_carga=_parse_fecha(request.form.get("fecha_carga")),
            estado_revision="Pendiente",
            creado_por_id=current_user.id,
        )
        db.session.add(observacion)
        db.session.flush()
        notificar_gestion(
            empresa_id=instalacion.cliente.empresa_id,
            tipo="observacion_nueva",
            titulo=f"Observación nueva ({observacion.clasificacion}) — {instalacion.nombre}",
            cliente_id=instalacion.cliente_id,
            enlace=url_for("instalaciones.detalle", instalacion_id=instalacion.id),
            remitente=current_user,
        )
        db.session.commit()
        flash("Observación cargada, pendiente de revisión del Administrador.", "success")
        if equipo:
            return redirect(url_for("equipos.detalle", equipo_id=equipo.id))
        if item:
            return redirect(url_for("visitas.detalle", visita_id=item.visita_id))
        return redirect(url_for("instalaciones.detalle", instalacion_id=instalacion.id))

    return render_template(
        "observaciones/form.html",
        instalacion=instalacion,
        item=item,
        equipo=equipo,
        clasificaciones=CLASIFICACIONES_OBSERVACION,
    )


def _verificar_editable(observacion):
    """Una observación Aprobada ya no se puede tocar (ni técnico ni nadie
    salvo borrarla, que es acción del Administrador)."""
    if observacion.estado_revision == "Aprobada":
        abort(403)


@observaciones_bp.route("/<int:observacion_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def editar(observacion_id):
    observacion = Observacion.query.get_or_404(observacion_id)
    verificar_escritura_cliente(observacion.instalacion.cliente)
    _verificar_editable(observacion)
    if observacion.item_visita:
        verificar_visita_editable(observacion.item_visita.visita)

    if request.method == "POST":
        observacion.clasificacion = request.form["clasificacion"]
        observacion.descripcion = request.form["descripcion"]
        observacion.fecha_carga = _parse_fecha(request.form.get("fecha_carga"), observacion.fecha_carga)
        db.session.commit()
        flash("Observación actualizada.", "success")
        return redirect(request.referrer or url_for("instalaciones.detalle", instalacion_id=observacion.instalacion_id))

    return render_template(
        "observaciones/editar.html", observacion=observacion, clasificaciones=CLASIFICACIONES_OBSERVACION
    )


@observaciones_bp.route("/<int:observacion_id>/aprobar", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def aprobar(observacion_id):
    observacion = Observacion.query.get_or_404(observacion_id)
    verificar_acceso_cliente(observacion.instalacion.cliente)
    observacion.aprobar(current_user.id)
    if observacion.creado_por:
        notificar_usuario(
            observacion.creado_por,
            tipo="observacion_aprobada",
            titulo=f"Observación aprobada — {observacion.instalacion.nombre}",
            empresa_id=observacion.instalacion.cliente.empresa_id,
            cliente_id=observacion.instalacion.cliente_id,
            enlace=url_for("instalaciones.detalle", instalacion_id=observacion.instalacion_id),
            remitente=current_user,
        )
    db.session.commit()
    flash("Observación aprobada.", "success")
    return redirect(request.referrer or url_for("dashboard.inicio"))


@observaciones_bp.route("/<int:observacion_id>/resolver", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def resolver(observacion_id):
    observacion = Observacion.query.get_or_404(observacion_id)
    verificar_escritura_cliente(observacion.instalacion.cliente)
    observacion.marcar_resuelta(current_user.id)
    db.session.commit()
    flash("Observación marcada como resuelta.", "success")
    return redirect(request.referrer or url_for("dashboard.inicio"))


@observaciones_bp.route("/<int:observacion_id>/reabrir", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def reabrir(observacion_id):
    observacion = Observacion.query.get_or_404(observacion_id)
    verificar_escritura_cliente(observacion.instalacion.cliente)
    observacion.reabrir(current_user.id)
    db.session.commit()
    flash("Observación reabierta.", "info")
    return redirect(request.referrer or url_for("dashboard.inicio"))


@observaciones_bp.route("/<int:observacion_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar(observacion_id):
    """Borrado real, distinto de 'resolver'. Una vez Aprobada, solo el
    Administrador la puede eliminar (por ejemplo, para corregirla y
    cargarla de nuevo)."""
    observacion = Observacion.query.get_or_404(observacion_id)
    verificar_escritura_cliente(observacion.instalacion.cliente)
    if observacion.estado_revision == "Aprobada" and current_user.rol not in ("Administrador", "Jefe"):
        abort(403)
    instalacion_id = observacion.instalacion_id
    db.session.delete(observacion)
    db.session.commit()
    flash("Observación eliminada.", "info")
    return redirect(url_for("instalaciones.detalle", instalacion_id=instalacion_id))
