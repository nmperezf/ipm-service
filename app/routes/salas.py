from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.auth_utils import rol_requerido, verificar_acceso_cliente, verificar_escritura_cliente
from app.models import Instalacion, SalaBombas
from app.utils import (
    obtener_acciones_recomendadas,
    obtener_datos_grafico_evolucion,
    obtener_resumen_sala,
    obtener_ultimos_ensayos_por_bomba,
)

salas_bp = Blueprint("salas", __name__, url_prefix="/salas")


@salas_bp.route("/instalacion/<int:instalacion_id>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def listar(instalacion_id):
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_acceso_cliente(instalacion.cliente)
    salas = SalaBombas.query.filter_by(instalacion_id=instalacion.id).order_by(SalaBombas.nombre).all()
    return render_template("salas/lista_salas.html", instalacion=instalacion, salas=salas)


@salas_bp.route("/nueva/<int:instalacion_id>", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def nueva(instalacion_id):
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_escritura_cliente(instalacion.cliente)

    if request.method == "POST":
        sala = SalaBombas(
            instalacion_id=instalacion.id,
            nombre=request.form["nombre"],
            descripcion=request.form.get("descripcion"),
            ubicacion=request.form.get("ubicacion"),
        )
        db.session.add(sala)
        db.session.commit()
        flash(f"Sala de bombas '{sala.nombre}' creada.", "success")
        return redirect(url_for("salas.detalle", sala_id=sala.id))

    return render_template("salas/formulario_sala.html", instalacion=instalacion, sala=None)


@salas_bp.route("/<int:sala_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def editar(sala_id):
    sala = SalaBombas.query.get_or_404(sala_id)
    verificar_escritura_cliente(sala.instalacion.cliente)

    if request.method == "POST":
        sala.nombre = request.form["nombre"]
        sala.descripcion = request.form.get("descripcion")
        sala.ubicacion = request.form.get("ubicacion")
        db.session.commit()
        flash(f"Sala de bombas '{sala.nombre}' actualizada.", "success")
        return redirect(url_for("salas.detalle", sala_id=sala.id))

    return render_template("salas/formulario_sala.html", instalacion=sala.instalacion, sala=sala)


@salas_bp.route("/<int:sala_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def eliminar(sala_id):
    sala = SalaBombas.query.get_or_404(sala_id)
    verificar_escritura_cliente(sala.instalacion.cliente)
    instalacion_id = sala.instalacion_id
    nombre = sala.nombre
    for bomba in list(sala.bombas):
        bomba.sala_id = None
    db.session.delete(sala)
    db.session.commit()
    flash(f"Sala de bombas '{nombre}' eliminada. Las bombas que tenía asignadas no se borraron.", "info")
    return redirect(url_for("salas.listar", instalacion_id=instalacion_id))


@salas_bp.route("/<int:sala_id>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def detalle(sala_id):
    sala = SalaBombas.query.get_or_404(sala_id)
    verificar_acceso_cliente(sala.instalacion.cliente)

    resumen = obtener_resumen_sala(sala.id)
    ensayos_por_bomba = {item["bomba_id"]: item["ensayos"] for item in obtener_ultimos_ensayos_por_bomba(sala.id)}
    grafico = obtener_datos_grafico_evolucion(sala.id)

    deficiencias_abiertas = [
        obs for bomba in sala.bombas for obs in bomba.deficiencias if not obs.resuelto
    ]
    criticas = [o for o in deficiencias_abiertas if o.clasificacion == "Deficiencia crítica"]
    no_criticas = [o for o in deficiencias_abiertas if o.clasificacion == "Deficiencia no crítica"]

    return render_template(
        "salas/ficha_sala.html",
        sala=sala,
        resumen=resumen,
        ensayos_por_bomba=ensayos_por_bomba,
        grafico=grafico,
        criticas=criticas,
        no_criticas=no_criticas,
        acciones=obtener_acciones_recomendadas(sala.id),
    )
