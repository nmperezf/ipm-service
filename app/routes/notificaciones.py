from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import rol_requerido
from app.models import Notificacion

notificaciones_bp = Blueprint("notificaciones", __name__, url_prefix="/notificaciones")


def _agrupar(notificaciones):
    """Junta las notificaciones por (tipo, cliente) cuando tienen cliente
    asociado (ej. 'Cliente X: 3 observaciones nuevas'); las que no tienen
    cliente (ej. un mensaje puntual) quedan sueltas, una por grupo."""
    grupos = {}
    orden = []
    for n in notificaciones:
        clave = (n.tipo, n.cliente_id) if n.cliente_id else (n.tipo, f"n{n.id}")
        if clave not in grupos:
            grupos[clave] = []
            orden.append(clave)
        grupos[clave].append(n)
    return [grupos[clave] for clave in orden]


@notificaciones_bp.route("/")
@rol_requerido("Administrador", "Jefe", "Técnico")
def listar():
    no_leidas = (
        Notificacion.query.filter_by(destinatario_id=current_user.id, leido=False)
        .order_by(Notificacion.fecha_carga.desc())
        .all()
    )
    leidas = (
        Notificacion.query.filter_by(destinatario_id=current_user.id, leido=True)
        .order_by(Notificacion.fecha_carga.desc())
        .limit(20)
        .all()
    )
    return render_template(
        "notificaciones/list.html", grupos_no_leidas=_agrupar(no_leidas), leidas=leidas
    )


@notificaciones_bp.route("/<int:notificacion_id>/ir")
@rol_requerido("Administrador", "Jefe", "Técnico")
def ir(notificacion_id):
    """Abre el link de la notificación y de paso la marca leída."""
    n = Notificacion.query.get_or_404(notificacion_id)
    if n.destinatario_id != current_user.id:
        abort(403)
    n.leido = True
    db.session.commit()
    return redirect(n.enlace or url_for("notificaciones.listar"))


@notificaciones_bp.route("/marcar-leidas", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def marcar_leidas():
    """Marca leído un grupo entero (todas las de un mismo tipo+cliente) sin
    salir de la pantalla — para cuando ya viste la lista y no hace falta
    abrir cada una."""
    ids = request.form.getlist("id", type=int)
    if ids:
        Notificacion.query.filter(
            Notificacion.id.in_(ids), Notificacion.destinatario_id == current_user.id
        ).update({"leido": True}, synchronize_session=False)
        db.session.commit()
    return redirect(url_for("notificaciones.listar"))


@notificaciones_bp.route("/marcar-todas-leidas", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def marcar_todas_leidas():
    Notificacion.query.filter_by(destinatario_id=current_user.id, leido=False).update(
        {"leido": True}, synchronize_session=False
    )
    db.session.commit()
    return redirect(url_for("notificaciones.listar"))
