from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import rol_requerido
from app.models import Mensaje, Notificacion

notificaciones_bp = Blueprint("notificaciones", __name__, url_prefix="/notificaciones")

ORDEN_PRIORIDAD_MENSAJE = {"Urgente": 0, "Alta": 1, "Media": 2, "Baja": 3}


def _mensajes_abiertos():
    """Mensajes internos sin resolver donde el usuario logueado participa
    -- mismo query que arma dashboard.py para su propio widget de
    Mensajes, reutilizado acá para mostrarlos junto a las notificaciones
    en la campanita (ver _resumen_modal.html)."""
    return sorted(
        Mensaje.query.filter(
            (Mensaje.remitente_id == current_user.id) | (Mensaje.destinatario_id == current_user.id),
            Mensaje.resuelto == False,  # noqa: E712
        ).order_by(Mensaje.fecha_carga.desc()).all(),
        key=lambda m: ORDEN_PRIORIDAD_MENSAJE.get(m.prioridad, 2),
    )


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


TOPE_NO_LEIDAS = 150


@notificaciones_bp.route("/")
@rol_requerido("Administrador", "Jefe", "Técnico")
def listar():
    # Tope generoso en vez de paginación real: se agrupan por (tipo,
    # cliente) antes de mostrarse (ver _agrupar), y paginar por fila
    # cortaría un grupo a la mitad entre dos páginas. Un usuario que deja
    # crecer esto más allá del tope tiene "Marcar todas como leídas" a
    # mano — no hace falta más que eso.
    no_leidas_query = (
        Notificacion.query.filter_by(destinatario_id=current_user.id, leido=False)
        .order_by(Notificacion.fecha_carga.desc())
    )
    total_no_leidas = no_leidas_query.count()
    no_leidas = no_leidas_query.limit(TOPE_NO_LEIDAS).all()
    leidas = (
        Notificacion.query.filter_by(destinatario_id=current_user.id, leido=True)
        .order_by(Notificacion.fecha_carga.desc())
        .limit(20)
        .all()
    )
    return render_template(
        "notificaciones/list.html",
        grupos_no_leidas=_agrupar(no_leidas),
        leidas=leidas,
        hay_mas_no_leidas=total_no_leidas > TOPE_NO_LEIDAS,
        total_no_leidas=total_no_leidas,
    )


@notificaciones_bp.route("/resumen")
@rol_requerido("Administrador", "Jefe", "Técnico")
def resumen():
    """Fragmento HTML para la ventana flotante de notificaciones (campanita),
    sin salir de la pantalla actual."""
    no_leidas = (
        Notificacion.query.filter_by(destinatario_id=current_user.id, leido=False)
        .order_by(Notificacion.fecha_carga.desc())
        .limit(20)
        .all()
    )
    return render_template(
        "notificaciones/_resumen_modal.html",
        grupos_no_leidas=_agrupar(no_leidas),
        mensajes_abiertos=_mensajes_abiertos(),
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


@notificaciones_bp.route("/<int:notificacion_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar(notificacion_id):
    n = Notificacion.query.get_or_404(notificacion_id)
    if n.destinatario_id != current_user.id:
        abort(403)
    db.session.delete(n)
    db.session.commit()
    flash("Notificación eliminada.", "info")
    return redirect(url_for("notificaciones.listar"))


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
