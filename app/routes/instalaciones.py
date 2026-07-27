from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app import db
from app.auth_utils import rol_requerido, verificar_acceso_cliente, verificar_escritura_cliente
from app.models import Cliente, Instalacion
from app.utils import equipos_por_categoria

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
@rol_requerido("Administrador", "Jefe", "Técnico")
def detalle(instalacion_id):
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_acceso_cliente(instalacion.cliente)
    contratos = sorted(instalacion.contratos, key=lambda c: c.fecha_inicio, reverse=True)
    visitas = sorted(instalacion.visitas, key=lambda v: v.fecha, reverse=True)
    return render_template(
        "instalaciones/detail.html", instalacion=instalacion, contratos=contratos, visitas=visitas
    )


@instalaciones_bp.route("/<int:instalacion_id>/informacion")
@rol_requerido("Administrador", "Jefe", "Técnico")
def informacion(instalacion_id):
    """Información de Instalación: tarjetas por categoría de equipo
    (Bombas, ECA/Manifold, BIE, Otros — cada una solo un título, sin
    detalle) y las acciones recomendadas (Observaciones) de la
    instalación. El detalle de cada equipo vive en su propia ficha."""
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_acceso_cliente(instalacion.cliente)

    acciones_recomendadas = sorted(
        (o for o in instalacion.deficiencias if not o.resuelto),
        key=lambda o: o.fecha_carga,
        reverse=True,
    )

    return render_template(
        "instalaciones/informacion.html",
        instalacion=instalacion,
        categorias=equipos_por_categoria(instalacion),
        acciones_recomendadas=acciones_recomendadas,
    )


@instalaciones_bp.route("/<int:instalacion_id>/informacion/<categoria>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def equipos_categoria(instalacion_id, categoria):
    """Listado liviano de los equipos de una categoría (nombre, ubicación
    y, para bombas, el estado NFPA 25 de su último ensayo) — el detalle
    completo de cada equipo vive en su propia ficha (equipos.detalle)."""
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_acceso_cliente(instalacion.cliente)

    grupos = dict(equipos_por_categoria(instalacion))
    if categoria not in grupos:
        abort(404)

    return render_template(
        "instalaciones/equipos_categoria.html",
        instalacion=instalacion,
        categoria=categoria,
        equipos=grupos[categoria],
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
