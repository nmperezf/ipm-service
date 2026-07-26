from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.auth_utils import rol_requerido
from app.models import Empresa, Usuario

empresas_bp = Blueprint("empresas", __name__, url_prefix="/empresas")


@empresas_bp.route("/")
@rol_requerido("Super Admin")
def listar():
    empresas = Empresa.query.order_by(Empresa.nombre).all()
    return render_template("empresas/list.html", empresas=empresas)


@empresas_bp.route("/nueva", methods=["GET", "POST"])
@rol_requerido("Super Admin")
def nueva():
    """Crea la empresa y su primer usuario Administrador de una vez —
    de ahí en más, ese Administrador gestiona el resto de sus usuarios."""
    if request.method == "POST":
        nombre_usuario = request.form["admin_username"].strip()
        if Usuario.query.filter_by(username=nombre_usuario).first():
            flash(f"Ya existe un usuario con el nombre '{nombre_usuario}'.", "danger")
            return render_template("empresas/form.html")

        empresa = Empresa(nombre=request.form["nombre"])
        db.session.add(empresa)
        db.session.flush()

        admin = Usuario(
            username=nombre_usuario,
            nombre_completo=request.form.get("admin_nombre"),
            rol="Administrador",
            empresa_id=empresa.id,
        )
        admin.set_password(request.form["admin_password"])
        db.session.add(admin)
        db.session.commit()
        flash(f"Empresa '{empresa.nombre}' creada, con '{admin.username}' como administrador.", "success")
        return redirect(url_for("empresas.listar"))

    return render_template("empresas/form.html")


@empresas_bp.route("/<int:empresa_id>/editar", methods=["GET", "POST"])
@rol_requerido("Super Admin")
def editar(empresa_id):
    empresa = Empresa.query.get_or_404(empresa_id)
    if request.method == "POST":
        empresa.nombre = request.form["nombre"]
        empresa.activo = bool(request.form.get("activo"))
        db.session.commit()
        flash(f"Empresa '{empresa.nombre}' actualizada.", "success")
        return redirect(url_for("empresas.listar"))
    return render_template("empresas/editar.html", empresa=empresa)
