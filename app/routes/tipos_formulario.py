import json

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.auth_utils import rol_requerido, verificar_acceso_cliente, verificar_escritura_cliente
from app.models import Cliente, Formulario, ServicioTipo, TipoFormulario, nombres_tipos_equipo
from app.utils import TIPOS_CAMPO, armar_campos_desde_formulario

tipos_formulario_bp = Blueprint("tipos_formulario", __name__, url_prefix="/tipos-formulario")


def _servicios_tipo_disponibles(empresa_id):
    return ServicioTipo.query.filter_by(empresa_id=empresa_id).order_by(ServicioTipo.nombre).all()


def _aplicar_servicios_tipo(tipo_formulario, form, empresa_id):
    ids = [int(i) for i in form.getlist("servicios_tipo_ids")]
    if ids:
        tipo_formulario.servicios_tipo = ServicioTipo.query.filter(
            ServicioTipo.id.in_(ids), ServicioTipo.empresa_id == empresa_id
        ).all()
    else:
        tipo_formulario.servicios_tipo = []


@tipos_formulario_bp.route("/<int:cliente_id>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def listar(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    verificar_acceso_cliente(cliente)
    tipos = TipoFormulario.query.filter_by(cliente_id=cliente.id).order_by(TipoFormulario.nombre).all()
    return render_template("tipos_formulario/list.html", tipos=tipos, cliente=cliente)


@tipos_formulario_bp.route("/<int:cliente_id>/nuevo", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def nuevo(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    verificar_escritura_cliente(cliente)

    servicios_tipo_disponibles = _servicios_tipo_disponibles(cliente.empresa_id)

    if request.method == "POST":
        campos = armar_campos_desde_formulario(request.form)
        if not campos:
            flash("Agregá al menos un campo antes de guardar.", "danger")
            return render_template(
                "tipos_formulario/form.html", tipo=None, cliente=cliente, tipos_equipo=nombres_tipos_equipo(),
                tipos_campo=TIPOS_CAMPO, servicios_tipo_disponibles=servicios_tipo_disponibles,
            )

        if TipoFormulario.query.filter_by(cliente_id=cliente.id, nombre=request.form["nombre"]).first():
            flash(f"Este cliente ya tiene un tipo de formulario llamado '{request.form['nombre']}'.", "danger")
            return render_template(
                "tipos_formulario/form.html", tipo=None, cliente=cliente, tipos_equipo=nombres_tipos_equipo(),
                tipos_campo=TIPOS_CAMPO, servicios_tipo_disponibles=servicios_tipo_disponibles,
            )

        tipo_formulario = TipoFormulario(
            cliente_id=cliente.id,
            nombre=request.form["nombre"],
            descripcion=request.form.get("descripcion"),
            por_equipo=bool(request.form.get("por_equipo")),
            tipo_equipo_aplicable=request.form.get("tipo_equipo_aplicable") or None,
            schema_json=json.dumps(campos),
        )
        _aplicar_servicios_tipo(tipo_formulario, request.form, cliente.empresa_id)
        db.session.add(tipo_formulario)
        db.session.commit()
        flash(f"Tipo de formulario '{tipo_formulario.nombre}' creado con {len(campos)} campo(s).", "success")
        return redirect(url_for("tipos_formulario.listar", cliente_id=cliente.id))

    return render_template(
        "tipos_formulario/form.html", tipo=None, cliente=cliente, tipos_equipo=nombres_tipos_equipo(),
        tipos_campo=TIPOS_CAMPO, servicios_tipo_disponibles=servicios_tipo_disponibles,
    )


@tipos_formulario_bp.route("/tipo/<int:tipo_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def editar(tipo_id):
    tipo_formulario = TipoFormulario.query.get_or_404(tipo_id)
    verificar_escritura_cliente(tipo_formulario.cliente)

    if request.method == "POST":
        campos = armar_campos_desde_formulario(request.form)
        if not campos:
            flash("Agregá al menos un campo antes de guardar.", "danger")
            return redirect(url_for("tipos_formulario.editar", tipo_id=tipo_id))

        tipo_formulario.nombre = request.form["nombre"]
        tipo_formulario.descripcion = request.form.get("descripcion")
        tipo_formulario.por_equipo = bool(request.form.get("por_equipo"))
        tipo_formulario.tipo_equipo_aplicable = request.form.get("tipo_equipo_aplicable") or None
        tipo_formulario.schema_json = json.dumps(campos)
        _aplicar_servicios_tipo(tipo_formulario, request.form, tipo_formulario.cliente.empresa_id)
        db.session.commit()
        flash(f"Tipo de formulario '{tipo_formulario.nombre}' actualizado.", "success")
        return redirect(url_for("tipos_formulario.listar", cliente_id=tipo_formulario.cliente_id))

    return render_template(
        "tipos_formulario/form.html",
        tipo=tipo_formulario,
        cliente=tipo_formulario.cliente,
        tipos_equipo=nombres_tipos_equipo(),
        tipos_campo=TIPOS_CAMPO,
        servicios_tipo_disponibles=_servicios_tipo_disponibles(tipo_formulario.cliente.empresa_id),
    )


@tipos_formulario_bp.route("/tipo/<int:tipo_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar(tipo_id):
    tipo_formulario = TipoFormulario.query.get_or_404(tipo_id)
    verificar_escritura_cliente(tipo_formulario.cliente)
    cliente_id = tipo_formulario.cliente_id
    if Formulario.query.filter_by(tipo_formulario_id=tipo_id).first():
        flash(
            f"'{tipo_formulario.nombre}' ya tiene formularios completados con este esquema; no se puede "
            "eliminar sin perder esos datos.",
            "danger",
        )
        return redirect(url_for("tipos_formulario.listar", cliente_id=cliente_id))
    db.session.delete(tipo_formulario)
    db.session.commit()
    flash(f"Tipo de formulario '{tipo_formulario.nombre}' eliminado.", "info")
    return redirect(url_for("tipos_formulario.listar", cliente_id=cliente_id))
