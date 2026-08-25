from datetime import date

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import (
    rol_requerido,
    verificar_acceso_cliente,
    verificar_escritura_cliente,
    verificar_visita_editable,
)
from app.models import (
    CLASIFICACIONES_OBSERVACION,
    VISIBILIDADES_OBSERVACION,
    Equipo,
    Foto,
    Instalacion,
    ItemVisita,
    Observacion,
)
from app.notificaciones import notificar_gestion, notificar_usuario
from app.routes.fotos import _extension_permitida, _guardar_archivo
from app.utils import crear_presupuesto, es_ajax, parse_fecha

observaciones_bp = Blueprint("observaciones", __name__, url_prefix="/observaciones")

CLASIFICACIONES_CON_PRESUPUESTO = ("Deficiencia crítica", "Deficiencia no crítica")


@observaciones_bp.route("/nueva/<int:instalacion_id>", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def nueva(instalacion_id):
    """Carga manual de una observación (deficiencia/desactivación), pensada
    también para migrar el historial que ya tenés de tus clientes actuales.
    Queda en revisión 'Pendiente' hasta que un Administrador la apruebe."""
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_escritura_cliente(instalacion.cliente)
    item_id = request.values.get("item_id", type=int)
    item = db.session.get(ItemVisita, item_id) if item_id else None
    if item:
        verificar_visita_editable(item.visita)
    equipo_id = request.values.get("equipo_id", type=int)
    equipo = db.session.get(Equipo, equipo_id) if equipo_id else None
    if item and item.visita.instalacion_id != instalacion.id:
        abort(400)
    if equipo and equipo.instalacion_id != instalacion.id:
        abort(400)

    if request.method == "POST":
        clasificacion = request.form["clasificacion"]
        requiere_presupuesto = bool(request.form.get("requiere_presupuesto")) and clasificacion in CLASIFICACIONES_CON_PRESUPUESTO
        visibilidad = request.form.get("visibilidad")
        if visibilidad not in VISIBILIDADES_OBSERVACION:
            visibilidad = "Cliente"

        observacion = Observacion(
            instalacion_id=instalacion.id,
            item_visita_id=item.id if item else None,
            equipo_id=equipo.id if equipo else None,
            clasificacion=clasificacion,
            descripcion=request.form["descripcion"],
            fecha_carga=parse_fecha(request.form.get("fecha_carga"), date.today()),
            estado_revision="Pendiente",
            visibilidad=visibilidad,
            creado_por_id=current_user.id,
            requiere_presupuesto=requiere_presupuesto,
        )
        db.session.add(observacion)
        db.session.flush()

        for archivo in request.files.getlist("fotos"):
            if not archivo or archivo.filename == "" or not _extension_permitida(archivo.filename):
                continue
            ruta_relativa = _guardar_archivo(
                archivo, instalacion.cliente.empresa_id, instalacion.cliente_id, instalacion.id,
                equipo.id if equipo else None,
            )
            db.session.add(
                Foto(
                    instalacion_id=instalacion.id,
                    equipo_id=equipo.id if equipo else None,
                    observacion_id=observacion.id,
                    nombre_archivo=ruta_relativa,
                    origen="Visita" if item else "Carga manual",
                    fecha_toma=date.today(),
                    subido_por_id=current_user.id,
                )
            )

        presupuesto = None
        if requiere_presupuesto:
            presupuesto = crear_presupuesto(observacion, current_user.id)

        notificar_gestion(
            empresa_id=instalacion.cliente.empresa_id,
            tipo="observacion_nueva",
            titulo=f"Observación nueva ({observacion.clasificacion}) — {instalacion.nombre}",
            cliente_id=instalacion.cliente_id,
            enlace=url_for("instalaciones.detalle", instalacion_id=instalacion.id),
            remitente=current_user,
        )
        db.session.commit()
        if presupuesto:
            mensaje = f"Observación cargada. Se generó el presupuesto {presupuesto.codigo}."
        else:
            mensaje = "Observación cargada, pendiente de revisión del Administrador."
        if es_ajax():
            return jsonify(ok=True, mensaje=mensaje)
        flash(mensaje, "success")
        if equipo:
            return redirect(url_for("equipos.detalle", equipo_id=equipo.id))
        if item:
            return redirect(url_for("visitas.detalle", visita_id=item.visita_id))
        return redirect(url_for("instalaciones.detalle", instalacion_id=instalacion.id))

    template = "observaciones/_form_fragment.html" if es_ajax() else "observaciones/form.html"
    return render_template(
        template,
        instalacion=instalacion,
        item=item,
        equipo=equipo,
        equipos=[e for e in instalacion.equipos if e.activo],
        equipo_preseleccionado=equipo.id if equipo else None,
        clasificaciones=CLASIFICACIONES_OBSERVACION,
        clasificaciones_con_presupuesto=CLASIFICACIONES_CON_PRESUPUESTO,
        visibilidades=VISIBILIDADES_OBSERVACION,
    )


def _verificar_editable(observacion):
    """Una observación Aprobada ya no se puede tocar (ni técnico ni nadie
    salvo borrarla, que es acción del Administrador). Tampoco si ya se
    presupuestó y el presupuesto avanzó de Pendiente — cambiar la
    descripción ahí desincronizaría lo que el cliente ya cotizó."""
    if observacion.estado_revision == "Aprobada":
        abort(403)
    if observacion.presupuesto and observacion.presupuesto.estado != "Pendiente":
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
        observacion.fecha_carga = parse_fecha(request.form.get("fecha_carga"), observacion.fecha_carga)
        visibilidad = request.form.get("visibilidad")
        if visibilidad in VISIBILIDADES_OBSERVACION:
            observacion.visibilidad = visibilidad
        db.session.commit()
        flash("Observación actualizada.", "success")
        return redirect(request.referrer or url_for("instalaciones.detalle", instalacion_id=observacion.instalacion_id))

    return render_template(
        "observaciones/editar.html",
        observacion=observacion,
        clasificaciones=CLASIFICACIONES_OBSERVACION,
        visibilidades=VISIBILIDADES_OBSERVACION,
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
