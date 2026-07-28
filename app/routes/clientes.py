from collections import defaultdict

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import clientes_visibles, rol_requerido, verificar_acceso_cliente, verificar_password_confirmacion
from app.models import Cliente, Visita
from app.utils import actualizar_vencimientos

clientes_bp = Blueprint("clientes", __name__, url_prefix="/clientes")

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


@clientes_bp.route("/")
@rol_requerido("Administrador", "Jefe", "Técnico")
def listar():
    q = request.args.get("q", "").strip()
    query = clientes_visibles()
    if q:
        query = query.filter(Cliente.nombre.ilike(f"%{q}%"))
    clientes = query.order_by(Cliente.nombre).all()
    return render_template("clientes/list.html", clientes=clientes, q=q)


@clientes_bp.route("/nuevo", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def nuevo():
    if request.method == "POST":
        cliente = Cliente(
            empresa_id=current_user.empresa_id,
            nombre=request.form["nombre"],
            direccion=request.form.get("direccion"),
            contacto=request.form.get("contacto"),
            telefono=request.form.get("telefono"),
            email=request.form.get("email"),
            observaciones=request.form.get("observaciones"),
            activo=bool(request.form.get("activo")),
        )
        db.session.add(cliente)
        db.session.commit()
        flash(f"Cliente '{cliente.nombre}' creado correctamente.", "success")
        return redirect(url_for("clientes.listar"))
    return render_template("clientes/form.html", cliente=None)


@clientes_bp.route("/<int:cliente_id>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def detalle(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    verificar_acceso_cliente(cliente)
    return render_template(
        "clientes/detail.html",
        cliente=cliente,
        indicadores=cliente.indicadores(),
        deficiencias=cliente.deficiencias_abiertas(),
        cumplido_anual_pct=cliente.cumplido_anual_pct(),
    )


@clientes_bp.route("/<int:cliente_id>/hoja-ruta")
@rol_requerido("Administrador", "Jefe", "Técnico")
def hoja_ruta(cliente_id):
    """Hoja de ruta del cliente: todas las visitas (cumplidas y pendientes/
    futuras) de todas sus instalaciones, agrupadas por mes."""
    cliente = Cliente.query.get_or_404(cliente_id)
    verificar_acceso_cliente(cliente)
    actualizar_vencimientos()

    visitas = (
        Visita.query.join(Visita.instalacion)
        .filter_by(cliente_id=cliente.id)
        .order_by(Visita.fecha)
        .all()
    )

    agrupado = defaultdict(list)
    for v in visitas:
        agrupado[(v.fecha.year, v.fecha.month)].append(v)

    meses_ordenados = sorted(agrupado.keys())
    bloques = [
        {"titulo": f"{MESES_ES[mes - 1]} {anio}", "visitas": agrupado[(anio, mes)]}
        for (anio, mes) in meses_ordenados
    ]

    return render_template("clientes/hoja_ruta.html", cliente=cliente, bloques=bloques)


@clientes_bp.route("/<int:cliente_id>/deficiencias/<clasificacion>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def deficiencias(cliente_id, clasificacion):
    cliente = Cliente.query.get_or_404(cliente_id)
    verificar_acceso_cliente(cliente)
    observaciones = sorted(
        (
            o
            for inst in cliente.instalaciones
            for o in inst.deficiencias
            if not o.resuelto and o.clasificacion == clasificacion
        ),
        key=lambda o: o.fecha_carga,
        reverse=True,
    )
    return render_template(
        "clientes/deficiencias.html", cliente=cliente, observaciones=observaciones, clasificacion=clasificacion
    )


@clientes_bp.route("/<int:cliente_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def editar(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    verificar_acceso_cliente(cliente)
    if request.method == "POST":
        cliente.nombre = request.form["nombre"]
        cliente.direccion = request.form.get("direccion")
        cliente.contacto = request.form.get("contacto")
        cliente.telefono = request.form.get("telefono")
        cliente.email = request.form.get("email")
        cliente.observaciones = request.form.get("observaciones")
        cliente.activo = bool(request.form.get("activo"))
        db.session.commit()
        flash(f"Cliente '{cliente.nombre}' actualizado.", "success")
        return redirect(url_for("clientes.detalle", cliente_id=cliente.id))
    return render_template("clientes/form.html", cliente=cliente)


@clientes_bp.route("/<int:cliente_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def eliminar(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    verificar_acceso_cliente(cliente)
    if not verificar_password_confirmacion():
        return redirect(url_for("clientes.detalle", cliente_id=cliente.id))
    db.session.delete(cliente)
    db.session.commit()
    flash(f"Cliente '{cliente.nombre}' eliminado.", "info")
    return redirect(url_for("clientes.listar"))
