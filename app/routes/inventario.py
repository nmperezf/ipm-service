from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import rol_requerido
from app.models import Repuesto

inventario_bp = Blueprint("inventario", __name__, url_prefix="/inventario")


def _repuestos_empresa():
    if current_user.rol == "Super Admin":
        return Repuesto.query
    return Repuesto.query.filter_by(empresa_id=current_user.empresa_id)


@inventario_bp.route("/")
def dashboard():
    repuestos = _repuestos_empresa().filter_by(activo=True).order_by(Repuesto.nombre).all()
    criticos = [r for r in repuestos if r.en_nivel_critico]
    return render_template("inventario/dashboard.html", repuestos=repuestos, criticos=criticos)


@inventario_bp.route("/criticos")
def criticos_lista():
    repuestos = _repuestos_empresa().filter_by(activo=True).order_by(Repuesto.nombre).all()
    criticos = [r for r in repuestos if r.en_nivel_critico]
    return render_template("inventario/criticos.html", criticos=criticos)


@inventario_bp.route("/nuevo", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def nuevo():
    if request.method == "POST":
        repuesto = Repuesto(
            empresa_id=current_user.empresa_id,
            nombre=request.form["nombre"],
            codigo=request.form.get("codigo"),
            unidad=request.form.get("unidad") or "unidad",
            stock_actual=int(request.form.get("stock_actual") or 0),
            stock_minimo=int(request.form.get("stock_minimo") or 0),
        )
        db.session.add(repuesto)
        db.session.commit()
        flash(f"Repuesto '{repuesto.nombre}' cargado.", "success")
        return redirect(url_for("inventario.dashboard"))
    return render_template("inventario/form.html", repuesto=None)


def _verificar_repuesto(repuesto):
    if current_user.rol != "Super Admin" and repuesto.empresa_id != current_user.empresa_id:
        abort(403)


@inventario_bp.route("/<int:repuesto_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def editar(repuesto_id):
    repuesto = Repuesto.query.get_or_404(repuesto_id)
    _verificar_repuesto(repuesto)
    if request.method == "POST":
        repuesto.nombre = request.form["nombre"]
        repuesto.codigo = request.form.get("codigo")
        repuesto.unidad = request.form.get("unidad") or "unidad"
        repuesto.stock_minimo = int(request.form.get("stock_minimo") or 0)
        repuesto.activo = bool(request.form.get("activo"))
        db.session.commit()
        flash(f"Repuesto '{repuesto.nombre}' actualizado.", "success")
        return redirect(url_for("inventario.dashboard"))
    return render_template("inventario/form.html", repuesto=repuesto)


@inventario_bp.route("/<int:repuesto_id>/reponer", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def reponer(repuesto_id):
    """Carga manual de stock (compra/reposición) — la única vía para
    aumentar stock; el consumo se descuenta desde una orden de trabajo."""
    repuesto = Repuesto.query.get_or_404(repuesto_id)
    _verificar_repuesto(repuesto)
    cantidad = int(request.form["cantidad"])
    repuesto.stock_actual += cantidad
    db.session.commit()
    flash(f"Se repusieron {cantidad} {repuesto.unidad}(s) de '{repuesto.nombre}'.", "success")
    return redirect(url_for("inventario.dashboard"))


@inventario_bp.route("/<int:repuesto_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def eliminar(repuesto_id):
    repuesto = Repuesto.query.get_or_404(repuesto_id)
    _verificar_repuesto(repuesto)
    if repuesto.usos:
        flash(
            f"'{repuesto.nombre}' ya tiene consumos registrados en órdenes de trabajo, no se puede "
            "eliminar sin perder ese historial. Desmarcá 'Activo' para ocultarlo en vez de borrarlo.",
            "danger",
        )
        return redirect(url_for("inventario.editar", repuesto_id=repuesto.id))
    db.session.delete(repuesto)
    db.session.commit()
    flash(f"Repuesto '{repuesto.nombre}' eliminado.", "info")
    return redirect(url_for("inventario.dashboard"))
