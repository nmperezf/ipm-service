from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.auth_utils import rol_requerido, verificar_acceso_cliente, verificar_escritura_cliente
from app.models import Cliente, Instalacion

instalaciones_bp = Blueprint("instalaciones", __name__, url_prefix="/instalaciones")


@instalaciones_bp.route("/nueva/<int:cliente_id>", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def nueva(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    verificar_escritura_cliente(cliente)
    if request.method == "POST":
        instalacion = Instalacion(
            cliente_id=cliente.id,
            nombre=request.form["nombre"],
            direccion=request.form.get("direccion"),
            observaciones=request.form.get("observaciones"),
        )
        db.session.add(instalacion)
        db.session.commit()
        flash(f"Instalación '{instalacion.nombre}' creada.", "success")
        return redirect(url_for("clientes.detalle", cliente_id=cliente.id))
    return render_template("instalaciones/form.html", cliente=cliente, instalacion=None)


@instalaciones_bp.route("/<int:instalacion_id>")
def detalle(instalacion_id):
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_acceso_cliente(instalacion.cliente)
    contratos = sorted(instalacion.contratos, key=lambda c: c.fecha_inicio, reverse=True)
    visitas = sorted(instalacion.visitas, key=lambda v: v.fecha, reverse=True)
    return render_template(
        "instalaciones/detail.html", instalacion=instalacion, contratos=contratos, visitas=visitas
    )


@instalaciones_bp.route("/<int:instalacion_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def editar(instalacion_id):
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_escritura_cliente(instalacion.cliente)
    if request.method == "POST":
        instalacion.nombre = request.form["nombre"]
        instalacion.direccion = request.form.get("direccion")
        instalacion.observaciones = request.form.get("observaciones")
        db.session.commit()
        flash(f"Instalación '{instalacion.nombre}' actualizada.", "success")
        return redirect(url_for("instalaciones.detalle", instalacion_id=instalacion.id))
    return render_template(
        "instalaciones/form.html", cliente=instalacion.cliente, instalacion=instalacion
    )


@instalaciones_bp.route("/<int:instalacion_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar(instalacion_id):
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_escritura_cliente(instalacion.cliente)
    cliente_id = instalacion.cliente_id
    db.session.delete(instalacion)
    db.session.commit()
    flash(f"Instalación '{instalacion.nombre}' eliminada.", "info")
    return redirect(url_for("clientes.detalle", cliente_id=cliente_id))
