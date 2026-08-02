from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import rol_requerido
from app.models import Mensaje, Usuario
from app.notificaciones import notificar_usuario

mensajes_bp = Blueprint("mensajes", __name__, url_prefix="/mensajes")


def _verificar_participante(mensaje):
    """Solo el remitente o el destinatario de un mensaje pueden tocarlo
    (aparte de Super Admin, para soporte)."""
    if current_user.rol == "Super Admin":
        return
    if current_user.id not in (mensaje.remitente_id, mensaje.destinatario_id):
        abort(403)


@mensajes_bp.route("/nuevo", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def nuevo():
    destinatario = Usuario.query.get_or_404(int(request.form["destinatario_id"]))
    if destinatario.empresa_id != current_user.empresa_id:
        abort(403)
    es_para_mi = destinatario.id == current_user.id
    cliente_id = request.form.get("cliente_id") or None
    mensaje = Mensaje(
        empresa_id=current_user.empresa_id,
        remitente_id=current_user.id,
        destinatario_id=destinatario.id,
        titulo=request.form["titulo"],
        cliente_id=int(cliente_id) if cliente_id else None,
        prioridad=request.form.get("prioridad", "Media"),
    )
    db.session.add(mensaje)
    db.session.flush()
    titulo_notif = (
        f"Recordatorio: {mensaje.titulo}"
        if es_para_mi
        else f"Mensaje de {current_user.nombre_completo or current_user.username}: {mensaje.titulo}"
    )
    notificar_usuario(
        destinatario,
        tipo="mensaje_nuevo",
        titulo=titulo_notif,
        empresa_id=current_user.empresa_id,
        cliente_id=mensaje.cliente_id,
        enlace=url_for("dashboard.inicio", _anchor=f"mensaje-{mensaje.id}"),
        # Sin remitente para el recordatorio personal: notificar_usuario no
        # avisa si destinatario == remitente (evita que un evento propio se
        # autonotifique), y acá sí queremos el aviso.
        remitente=None if es_para_mi else current_user,
    )
    db.session.commit()
    flash("Recordatorio guardado." if es_para_mi else "Mensaje enviado.", "success")
    return redirect(url_for("dashboard.inicio"))


@mensajes_bp.route("/<int:mensaje_id>/resolver", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def resolver(mensaje_id):
    mensaje = Mensaje.query.get_or_404(mensaje_id)
    _verificar_participante(mensaje)
    mensaje.resuelto = True
    db.session.commit()
    flash("Mensaje resuelto.", "success")
    return redirect(url_for("dashboard.inicio"))


@mensajes_bp.route("/<int:mensaje_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar(mensaje_id):
    mensaje = Mensaje.query.get_or_404(mensaje_id)
    _verificar_participante(mensaje)
    db.session.delete(mensaje)
    db.session.commit()
    flash("Mensaje eliminado.", "info")
    return redirect(url_for("dashboard.inicio"))


@mensajes_bp.route("/resueltos")
@rol_requerido("Administrador", "Jefe", "Técnico", "Super Admin")
def resueltos():
    if current_user.rol == "Super Admin":
        mq = Mensaje.query
    else:
        mq = Mensaje.query.filter(
            (Mensaje.remitente_id == current_user.id) | (Mensaje.destinatario_id == current_user.id)
        )
    mensajes = mq.filter_by(resuelto=True).order_by(Mensaje.fecha_carga.desc()).all()
    return render_template("mensajes/resueltos.html", mensajes=mensajes)


@mensajes_bp.route("/<int:mensaje_id>/reabrir", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def reabrir(mensaje_id):
    mensaje = Mensaje.query.get_or_404(mensaje_id)
    _verificar_participante(mensaje)
    mensaje.resuelto = False
    db.session.commit()
    flash("Mensaje reabierto.", "info")
    return redirect(url_for("mensajes.resueltos"))
