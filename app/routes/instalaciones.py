from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.auth_utils import rol_requerido, verificar_acceso_cliente, verificar_escritura_cliente
from app.models import Cliente, Instalacion
from app.utils import (
    obtener_acciones_recomendadas,
    obtener_curvas_superpuestas_equipo,
    obtener_resumen_bombas,
    obtener_resumen_checklists_instalacion,
    obtener_ultimos_ensayos_por_bomba,
)

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


@instalaciones_bp.route("/<int:instalacion_id>/informacion")
@rol_requerido("Administrador", "Jefe", "Técnico")
def informacion(instalacion_id):
    """Información de Instalación: resumen de bombas (curva de caudal,
    datos de motor) y un vistazo al histórico de checklist de todos los
    equipos (ECA, BIE, Bomba, etc), no solo bombas."""
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_acceso_cliente(instalacion.cliente)

    bombas = [e for e in instalacion.equipos if e.tipo == "Bomba"]
    ensayos_por_bomba = {item["bomba_id"]: item["ensayos"] for item in obtener_ultimos_ensayos_por_bomba(instalacion)}
    curvas_por_bomba = {equipo.id: obtener_curvas_superpuestas_equipo(equipo) for equipo in bombas}

    return render_template(
        "instalaciones/informacion.html",
        instalacion=instalacion,
        bombas=bombas,
        resumen=obtener_resumen_bombas(instalacion),
        ensayos_por_bomba=ensayos_por_bomba,
        curvas_por_bomba=curvas_por_bomba,
        acciones=obtener_acciones_recomendadas(instalacion),
        checklists_por_tipo=obtener_resumen_checklists_instalacion(instalacion),
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
