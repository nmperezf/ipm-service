import json

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.auth_utils import rol_requerido, verificar_acceso_cliente, verificar_escritura_cliente
from app.models import Cliente, Formulario, TipoFormulario, nombres_tipos_equipo
from app.utils import TIPOS_CAMPO, armar_campos_desde_formulario

tipos_formulario_bp = Blueprint("tipos_formulario", __name__, url_prefix="/tipos-formulario")


@tipos_formulario_bp.route("/<int:cliente_id>/nuevo", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def nuevo(cliente_id):
    """Formulario adicional para un cliente, sin pasar por el catálogo
    'Servicios tipo' de la empresa (caso puntual). Se accede desde la
    ficha del contrato del cliente."""
    cliente = Cliente.query.get_or_404(cliente_id)
    verificar_escritura_cliente(cliente)
    volver_a = request.values.get("volver_a") or url_for("clientes.detalle", cliente_id=cliente.id)
    # Al venir de un ítem de visita ligado a un equipo (ver visitas.detalle),
    # se sugiere ese tipo de equipo para no tener que adivinarlo — evita
    # crear un tipo de formulario mal etiquetado (ej. tipo_equipo_aplicable
    # que no corresponde al nombre del formulario).
    tipo_equipo_sugerido = request.values.get("tipo_equipo_aplicable") or None

    if request.method == "POST":
        campos = armar_campos_desde_formulario(request.form)
        if not campos:
            flash("Agregá al menos un campo antes de guardar.", "danger")
            return render_template(
                "tipos_formulario/form.html", tipo=None, cliente=cliente, tipos_equipo=nombres_tipos_equipo(),
                tipos_campo=TIPOS_CAMPO, volver_a=volver_a, tipo_equipo_sugerido=tipo_equipo_sugerido,
            )

        if TipoFormulario.query.filter_by(cliente_id=cliente.id, nombre=request.form["nombre"]).first():
            flash(f"Este cliente ya tiene un tipo de formulario llamado '{request.form['nombre']}'.", "danger")
            return render_template(
                "tipos_formulario/form.html", tipo=None, cliente=cliente, tipos_equipo=nombres_tipos_equipo(),
                tipos_campo=TIPOS_CAMPO, volver_a=volver_a, tipo_equipo_sugerido=tipo_equipo_sugerido,
            )

        tipo_formulario = TipoFormulario(
            cliente_id=cliente.id,
            nombre=request.form["nombre"],
            descripcion=request.form.get("descripcion"),
            por_equipo=bool(request.form.get("por_equipo")),
            tipo_equipo_aplicable=request.form.get("tipo_equipo_aplicable") or None,
            schema_json=json.dumps(campos),
        )
        db.session.add(tipo_formulario)
        db.session.commit()
        flash(f"Tipo de formulario '{tipo_formulario.nombre}' creado con {len(campos)} campo(s).", "success")
        return redirect(request.form.get("volver_a") or volver_a)

    return render_template(
        "tipos_formulario/form.html", tipo=None, cliente=cliente, tipos_equipo=nombres_tipos_equipo(),
        tipos_campo=TIPOS_CAMPO, volver_a=volver_a, tipo_equipo_sugerido=tipo_equipo_sugerido,
    )


@tipos_formulario_bp.route("/tipo/<int:tipo_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def editar(tipo_id):
    tipo_formulario = TipoFormulario.query.get_or_404(tipo_id)
    verificar_escritura_cliente(tipo_formulario.cliente)
    volver_a = request.values.get("volver_a") or url_for("clientes.detalle", cliente_id=tipo_formulario.cliente_id)

    if request.method == "POST":
        campos = armar_campos_desde_formulario(request.form)
        if not campos:
            flash("Agregá al menos un campo antes de guardar.", "danger")
            return redirect(url_for("tipos_formulario.editar", tipo_id=tipo_id, volver_a=volver_a))

        tipo_formulario.nombre = request.form["nombre"]
        tipo_formulario.descripcion = request.form.get("descripcion")
        tipo_formulario.por_equipo = bool(request.form.get("por_equipo"))
        tipo_formulario.tipo_equipo_aplicable = request.form.get("tipo_equipo_aplicable") or None
        tipo_formulario.schema_json = json.dumps(campos)
        db.session.commit()
        flash(f"Tipo de formulario '{tipo_formulario.nombre}' actualizado.", "success")
        return redirect(request.form.get("volver_a") or volver_a)

    return render_template(
        "tipos_formulario/form.html",
        tipo=tipo_formulario,
        cliente=tipo_formulario.cliente,
        tipos_equipo=nombres_tipos_equipo(),
        tipos_campo=TIPOS_CAMPO,
        volver_a=volver_a,
    )


@tipos_formulario_bp.route("/tipo/<int:tipo_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar(tipo_id):
    tipo_formulario = TipoFormulario.query.get_or_404(tipo_id)
    verificar_escritura_cliente(tipo_formulario.cliente)
    cliente_id = tipo_formulario.cliente_id
    volver_a = request.form.get("volver_a") or url_for("clientes.detalle", cliente_id=cliente_id)
    if Formulario.query.filter_by(tipo_formulario_id=tipo_id).first():
        flash(
            f"'{tipo_formulario.nombre}' ya tiene formularios completados con este esquema; no se puede "
            "eliminar sin perder esos datos.",
            "danger",
        )
        return redirect(volver_a)
    db.session.delete(tipo_formulario)
    db.session.commit()
    flash(f"Tipo de formulario '{tipo_formulario.nombre}' eliminado.", "info")
    return redirect(volver_a)
