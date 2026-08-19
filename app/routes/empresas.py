import os
import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app import db
from app.auth_utils import rol_requerido
from app.models import Empresa, Usuario
from app.routes.fotos import _extension_permitida

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


def _guardar_logo(archivo, empresa_id):
    """Guarda el logo bajo UPLOAD_FOLDER/<empresa_id>/logo/, mismo patrón
    de nombre único (uuid4 + secure_filename) que _guardar_archivo en
    fotos.py -- devuelve la ruta relativa a guardar en Empresa.logo."""
    carpeta_relativa = os.path.join(str(empresa_id), "logo")
    carpeta_absoluta = os.path.join(current_app.config["UPLOAD_FOLDER"], carpeta_relativa)
    os.makedirs(carpeta_absoluta, exist_ok=True)
    nombre_seguro = secure_filename(archivo.filename)
    nombre_unico = f"{uuid.uuid4().hex}_{nombre_seguro}"
    archivo.save(os.path.join(carpeta_absoluta, nombre_unico))
    return os.path.join(carpeta_relativa, nombre_unico)


@empresas_bp.route("/mi-empresa", methods=["GET", "POST"])
@login_required
@rol_requerido("Administrador", "Jefe")
def mi_empresa():
    """Autogestión de los datos de la propia empresa (nombre + logo) --
    a diferencia de empresas.editar (Super Admin, cualquier empresa), acá
    siempre opera sobre current_user.empresa. El logo subido acá reemplaza
    el genérico de IPM Manager en el encabezado de los PDF que genera esta
    empresa (ver app/pdf_base.py)."""
    empresa = current_user.empresa
    if request.method == "POST":
        empresa.nombre = request.form["nombre"]
        archivo = request.files.get("logo")
        if archivo and archivo.filename:
            if not _extension_permitida(archivo.filename):
                flash("Formato de logo no permitido. Usá PNG, JPG, GIF o WEBP.", "danger")
                return redirect(url_for("empresas.mi_empresa"))
            empresa.logo = _guardar_logo(archivo, empresa.id)
        db.session.commit()
        flash("Datos de la empresa actualizados.", "success")
        return redirect(url_for("empresas.mi_empresa"))
    return render_template("empresas/mi_empresa.html", empresa=empresa)


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
