from collections import defaultdict

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

from app import db
from app.auth_utils import (
    rol_requerido,
    verificar_acceso_cliente,
    verificar_escritura_cliente,
    verificar_password_confirmacion,
)
from app.models import Cliente, Instalacion
from app.utils import equipos_por_categoria, es_ajax

instalaciones_bp = Blueprint("instalaciones", __name__, url_prefix="/instalaciones")

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


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
        mensaje = f"Instalación '{instalacion.nombre}' creada."
        if es_ajax():
            return jsonify(ok=True, mensaje=mensaje)
        flash(mensaje, "success")
        return redirect(url_for("clientes.detalle", cliente_id=cliente.id))
    template = "instalaciones/_form_fragment.html" if es_ajax() else "instalaciones/form.html"
    return render_template(template, cliente=cliente, instalacion=None)


@instalaciones_bp.route("/<int:instalacion_id>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def detalle(instalacion_id):
    """Ficha de la instalación: equipos agrupados por categoría (antes una
    pantalla aparte, "Información de instalación"), observaciones
    abiertas, contratos y su hoja de ruta (todas las visitas, cumplidas y
    pendientes/futuras, agrupadas por mes — antes solo existía a nivel
    cliente mezclando todas sus instalaciones)."""
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_acceso_cliente(instalacion.cliente)
    contratos = sorted(instalacion.contratos, key=lambda c: c.fecha_inicio, reverse=True)

    agrupado = defaultdict(list)
    for v in instalacion.visitas:
        agrupado[(v.fecha.year, v.fecha.month)].append(v)
    meses_ordenados = sorted(agrupado.keys(), reverse=True)
    bloques_hoja_ruta = [
        {
            "titulo": f"{MESES_ES[mes - 1]} {anio}",
            "visitas": sorted(agrupado[(anio, mes)], key=lambda v: v.fecha, reverse=True),
        }
        for (anio, mes) in meses_ordenados
    ]

    contexto = dict(
        instalacion=instalacion,
        contratos=contratos,
        categorias=equipos_por_categoria(instalacion),
        bloques_hoja_ruta=bloques_hoja_ruta,
    )
    template = "instalaciones/_contenido.html" if es_ajax() else "instalaciones/detail.html"
    return render_template(template, **contexto)


@instalaciones_bp.route("/<int:instalacion_id>/fotos")
@rol_requerido("Administrador", "Jefe", "Técnico")
def fotos(instalacion_id):
    """Banco de fotos de toda la instalación en una sola tabla (buscable y
    ordenable por columna vía tablas.js) — las fichas de cada equipo
    siguen mostrando su propio mini-grid para contexto rápido, esta
    pantalla es para revisar/auditar todo junto."""
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_acceso_cliente(instalacion.cliente)
    fotos_ordenadas = sorted(
        instalacion.fotos, key=lambda f: f.fecha_toma or f.fecha_subida.date(), reverse=True
    )
    return render_template("instalaciones/fotos.html", instalacion=instalacion, fotos=fotos_ordenadas)


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
        mensaje = f"Instalación '{instalacion.nombre}' actualizada."
        if es_ajax():
            return jsonify(ok=True, mensaje=mensaje)
        flash(mensaje, "success")
        return redirect(url_for("instalaciones.detalle", instalacion_id=instalacion.id))
    template = "instalaciones/_form_fragment.html" if es_ajax() else "instalaciones/form.html"
    return render_template(template, cliente=instalacion.cliente, instalacion=instalacion)


@instalaciones_bp.route("/<int:instalacion_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar(instalacion_id):
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_escritura_cliente(instalacion.cliente)
    if not verificar_password_confirmacion():
        return redirect(url_for("instalaciones.detalle", instalacion_id=instalacion.id))
    cliente_id = instalacion.cliente_id
    db.session.delete(instalacion)
    db.session.commit()
    flash(f"Instalación '{instalacion.nombre}' eliminada.", "info")
    return redirect(url_for("clientes.detalle", cliente_id=cliente_id))
