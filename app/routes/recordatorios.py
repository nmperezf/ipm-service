from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import rol_requerido
from app.models import Recordatorio

recordatorios_bp = Blueprint("recordatorios", __name__, url_prefix="/recordatorios")


@recordatorios_bp.route("/nuevo", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def nuevo():
    cliente_id = request.form.get("cliente_id") or None
    recordatorio = Recordatorio(
        empresa_id=current_user.empresa_id,
        titulo=request.form["titulo"],
        cliente_id=int(cliente_id) if cliente_id else None,
        prioridad=request.form.get("prioridad", "Media"),
    )
    db.session.add(recordatorio)
    db.session.commit()
    flash("Recordatorio cargado.", "success")
    return redirect(url_for("dashboard.inicio"))


def _verificar_recordatorio(recordatorio):
    if current_user.rol != "Super Admin" and recordatorio.empresa_id != current_user.empresa_id:
        abort(403)


@recordatorios_bp.route("/<int:recordatorio_id>/resolver", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def resolver(recordatorio_id):
    recordatorio = Recordatorio.query.get_or_404(recordatorio_id)
    _verificar_recordatorio(recordatorio)
    recordatorio.resuelto = True
    db.session.commit()
    flash("Recordatorio resuelto.", "success")
    return redirect(url_for("dashboard.inicio"))


@recordatorios_bp.route("/<int:recordatorio_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def eliminar(recordatorio_id):
    recordatorio = Recordatorio.query.get_or_404(recordatorio_id)
    _verificar_recordatorio(recordatorio)
    db.session.delete(recordatorio)
    db.session.commit()
    flash("Recordatorio eliminado.", "info")
    return redirect(url_for("dashboard.inicio"))


@recordatorios_bp.route("/resueltos")
@rol_requerido("Administrador", "Jefe", "Super Admin")
def resueltos():
    rq = Recordatorio.query if current_user.rol == "Super Admin" else Recordatorio.query.filter_by(
        empresa_id=current_user.empresa_id
    )
    recordatorios = rq.filter_by(resuelto=True).order_by(Recordatorio.fecha_carga.desc()).all()
    return render_template("recordatorios/resueltos.html", recordatorios=recordatorios)


@recordatorios_bp.route("/<int:recordatorio_id>/reabrir", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def reabrir(recordatorio_id):
    recordatorio = Recordatorio.query.get_or_404(recordatorio_id)
    _verificar_recordatorio(recordatorio)
    recordatorio.resuelto = False
    db.session.commit()
    flash("Recordatorio reabierto.", "info")
    return redirect(url_for("recordatorios.resueltos"))
