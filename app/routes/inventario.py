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
@rol_requerido("Administrador", "Jefe", "Técnico")
def dashboard():
    repuestos = _repuestos_empresa().filter_by(activo=True).order_by(Repuesto.nombre).all()
    criticos = [r for r in repuestos if r.en_nivel_critico]
    return render_template("inventario/dashboard.html", repuestos=repuestos, criticos=criticos)


@inventario_bp.route("/criticos")
@rol_requerido("Administrador", "Jefe", "Técnico")
def criticos_lista():
    repuestos = _repuestos_empresa().filter_by(activo=True).order_by(Repuesto.nombre).all()
    criticos = [r for r in repuestos if r.en_nivel_critico]
    return render_template("inventario/criticos.html", criticos=criticos)


@inventario_bp.route("/nuevo", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def nuevo():
    if request.method == "POST":
        stock_actual = request.form.get("stock_actual", type=int)
        stock_minimo = request.form.get("stock_minimo", type=int)
        if stock_actual is None or stock_minimo is None or stock_actual < 0 or stock_minimo < 0:
            flash("El stock no puede ser negativo.", "danger")
            return redirect(url_for("inventario.nuevo"))
        repuesto = Repuesto(
            empresa_id=current_user.empresa_id,
            nombre=request.form["nombre"],
            codigo=request.form.get("codigo"),
            unidad=request.form.get("unidad") or "unidad",
            stock_actual=stock_actual,
            stock_minimo=stock_minimo,
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
        stock_minimo = request.form.get("stock_minimo", type=int)
        if stock_minimo is None or stock_minimo < 0:
            flash("El stock mínimo no puede ser negativo.", "danger")
            return redirect(url_for("inventario.editar", repuesto_id=repuesto.id))
        repuesto.nombre = request.form["nombre"]
        repuesto.codigo = request.form.get("codigo")
        repuesto.unidad = request.form.get("unidad") or "unidad"
        repuesto.stock_minimo = stock_minimo
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
    cantidad = request.form.get("cantidad", type=int)
    if cantidad is None or cantidad <= 0:
        flash("La cantidad tiene que ser mayor a 0.", "danger")
        return redirect(url_for("inventario.dashboard"))
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
