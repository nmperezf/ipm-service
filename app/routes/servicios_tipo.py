import json

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import rol_requerido
from app.models import ServicioTipo, nombres_tipos_equipo
from app.utils import TIPOS_CAMPO, armar_campos_desde_formulario

servicios_tipo_bp = Blueprint("servicios_tipo", __name__, url_prefix="/servicios-tipo")


def _verificar_pertenencia(servicio_tipo):
    if current_user.rol != "Super Admin" and servicio_tipo.empresa_id != current_user.empresa_id:
        abort(403)


@servicios_tipo_bp.route("/")
@rol_requerido("Administrador", "Jefe")
def listar():
    servicios = (
        ServicioTipo.query.filter_by(empresa_id=current_user.empresa_id).order_by(ServicioTipo.nombre).all()
    )
    return render_template("servicios_tipo/list.html", servicios=servicios)


@servicios_tipo_bp.route("/nuevo", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def nuevo():
    if request.method == "POST":
        campos = armar_campos_desde_formulario(request.form)
        if not campos:
            flash("Agregá al menos un campo antes de guardar.", "danger")
            return render_template("servicios_tipo/form.html", servicio=None, tipos_equipo=nombres_tipos_equipo(), tipos_campo=TIPOS_CAMPO)

        if ServicioTipo.query.filter_by(empresa_id=current_user.empresa_id, nombre=request.form["nombre"]).first():
            flash(f"Ya existe un servicio tipo llamado '{request.form['nombre']}' en tu empresa.", "danger")
            return render_template("servicios_tipo/form.html", servicio=None, tipos_equipo=nombres_tipos_equipo(), tipos_campo=TIPOS_CAMPO)

        servicio = ServicioTipo(
            empresa_id=current_user.empresa_id,
            nombre=request.form["nombre"],
            descripcion=request.form.get("descripcion"),
            por_equipo=bool(request.form.get("por_equipo")),
            tipo_equipo_aplicable=request.form.get("tipo_equipo_aplicable") or None,
            schema_json=json.dumps(campos),
        )
        db.session.add(servicio)
        db.session.commit()
        flash(f"Servicio tipo '{servicio.nombre}' creado con {len(campos)} campo(s).", "success")
        return redirect(url_for("servicios_tipo.listar"))

    return render_template("servicios_tipo/form.html", servicio=None, tipos_equipo=nombres_tipos_equipo(), tipos_campo=TIPOS_CAMPO)


@servicios_tipo_bp.route("/<int:servicio_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def editar(servicio_id):
    servicio = ServicioTipo.query.get_or_404(servicio_id)
    _verificar_pertenencia(servicio)

    if request.method == "POST":
        campos = armar_campos_desde_formulario(request.form)
        if not campos:
            flash("Agregá al menos un campo antes de guardar.", "danger")
            return redirect(url_for("servicios_tipo.editar", servicio_id=servicio_id))

        servicio.nombre = request.form["nombre"]
        servicio.descripcion = request.form.get("descripcion")
        servicio.por_equipo = bool(request.form.get("por_equipo"))
        servicio.tipo_equipo_aplicable = request.form.get("tipo_equipo_aplicable") or None
        servicio.schema_json = json.dumps(campos)
        db.session.commit()
        flash(
            f"Servicio tipo '{servicio.nombre}' actualizado. Los clientes que ya lo habían importado "
            "conservan su propia copia — este cambio no los afecta.",
            "success",
        )
        return redirect(url_for("servicios_tipo.listar"))

    return render_template("servicios_tipo/form.html", servicio=servicio, tipos_equipo=nombres_tipos_equipo(), tipos_campo=TIPOS_CAMPO)


@servicios_tipo_bp.route("/<int:servicio_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def eliminar(servicio_id):
    servicio = ServicioTipo.query.get_or_404(servicio_id)
    _verificar_pertenencia(servicio)
    nombre = servicio.nombre
    db.session.delete(servicio)
    db.session.commit()
    flash(
        f"Servicio tipo '{nombre}' eliminado del catálogo. Las copias que ya importaron algunos "
        "clientes no se ven afectadas.",
        "info",
    )
    return redirect(url_for("servicios_tipo.listar"))
