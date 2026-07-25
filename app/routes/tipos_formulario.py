import json
import re
import unicodedata

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.auth_utils import rol_requerido, verificar_acceso_cliente, verificar_escritura_cliente
from app.models import Cliente, Formulario, TipoFormulario, TIPOS_EQUIPO

tipos_formulario_bp = Blueprint("tipos_formulario", __name__, url_prefix="/tipos-formulario")

TIPOS_CAMPO = [
    ("texto", "Texto corto"),
    ("texto_largo", "Texto largo"),
    ("numero", "Número"),
    ("fecha", "Fecha"),
    ("booleano", "Sí / No"),
    ("seleccion", "Selección (una opción)"),
    ("multi_seleccion", "Checklist (varias opciones)"),
]


def _slugify(texto):
    """Convierte una etiqueta libre en una clave interna segura (sin
    acentos, espacios ni mayúsculas) para usar como nombre de campo."""
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    texto = texto.lower().strip()
    texto = re.sub(r"[^a-z0-9]+", "_", texto).strip("_")
    return texto or "campo"


def _armar_campos_desde_formulario(form):
    """Reconstruye la lista de campos (schema_json) a partir de los inputs
    repetidos del constructor dinámico."""
    labels = form.getlist("campo_label")
    tipos = form.getlist("campo_tipo")
    opciones_list = form.getlist("campo_opciones")

    campos = []
    usados = set()
    for label, tipo, opciones_str in zip(labels, tipos, opciones_list):
        label = (label or "").strip()
        if not label:
            continue
        slug_base = _slugify(label)
        slug = slug_base
        n = 1
        while slug in usados:
            n += 1
            slug = f"{slug_base}_{n}"
        usados.add(slug)

        campo = {"campo": slug, "tipo": tipo, "label": label}
        if tipo in ("seleccion", "multi_seleccion") and opciones_str.strip():
            campo["opciones"] = [o.strip() for o in opciones_str.split(",") if o.strip()]
        campos.append(campo)
    return campos


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

    if request.method == "POST":
        campos = _armar_campos_desde_formulario(request.form)
        if not campos:
            flash("Agregá al menos un campo antes de guardar.", "danger")
            return render_template(
                "tipos_formulario/form.html", tipo=None, cliente=cliente, tipos_equipo=TIPOS_EQUIPO, tipos_campo=TIPOS_CAMPO
            )

        if TipoFormulario.query.filter_by(cliente_id=cliente.id, nombre=request.form["nombre"]).first():
            flash(f"Este cliente ya tiene un tipo de formulario llamado '{request.form['nombre']}'.", "danger")
            return render_template(
                "tipos_formulario/form.html", tipo=None, cliente=cliente, tipos_equipo=TIPOS_EQUIPO, tipos_campo=TIPOS_CAMPO
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
        return redirect(url_for("tipos_formulario.listar", cliente_id=cliente.id))

    return render_template(
        "tipos_formulario/form.html", tipo=None, cliente=cliente, tipos_equipo=TIPOS_EQUIPO, tipos_campo=TIPOS_CAMPO
    )


@tipos_formulario_bp.route("/tipo/<int:tipo_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def editar(tipo_id):
    tipo_formulario = TipoFormulario.query.get_or_404(tipo_id)
    verificar_escritura_cliente(tipo_formulario.cliente)

    if request.method == "POST":
        campos = _armar_campos_desde_formulario(request.form)
        if not campos:
            flash("Agregá al menos un campo antes de guardar.", "danger")
            return redirect(url_for("tipos_formulario.editar", tipo_id=tipo_id))

        tipo_formulario.nombre = request.form["nombre"]
        tipo_formulario.descripcion = request.form.get("descripcion")
        tipo_formulario.por_equipo = bool(request.form.get("por_equipo"))
        tipo_formulario.tipo_equipo_aplicable = request.form.get("tipo_equipo_aplicable") or None
        tipo_formulario.schema_json = json.dumps(campos)
        db.session.commit()
        flash(f"Tipo de formulario '{tipo_formulario.nombre}' actualizado.", "success")
        return redirect(url_for("tipos_formulario.listar", cliente_id=tipo_formulario.cliente_id))

    return render_template(
        "tipos_formulario/form.html",
        tipo=tipo_formulario,
        cliente=tipo_formulario.cliente,
        tipos_equipo=TIPOS_EQUIPO,
        tipos_campo=TIPOS_CAMPO,
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
