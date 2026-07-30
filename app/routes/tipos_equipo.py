from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.auth_utils import rol_requerido
from app.models import CATEGORIAS_EQUIPO_ORDEN, Equipo, ServicioTipo, TipoEquipo, TipoFormulario, categorias_equipo_agrupadas

tipos_equipo_bp = Blueprint("tipos_equipo", __name__, url_prefix="/tipos-equipo")


@tipos_equipo_bp.route("/")
@rol_requerido("Administrador", "Jefe", "Técnico")
def listar():
    tipos_por_nombre = {t.nombre: t for t in TipoEquipo.query.all()}
    grupos = [
        (categoria, [tipos_por_nombre[nombre] for nombre in nombres])
        for categoria, nombres in categorias_equipo_agrupadas()
    ]
    return render_template("tipos_equipo/list.html", grupos=grupos)


@tipos_equipo_bp.route("/nuevo", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def nuevo():
    """Se accede desde la navegación general o, con el link '+ Nuevo tipo'
    del formulario de equipo (se abre en una pestaña aparte), para no
    perder lo que ya se venía completando ahí."""
    categorias_existentes = sorted({t.categoria for t in TipoEquipo.query.all()} | set(CATEGORIAS_EQUIPO_ORDEN))

    if request.method == "POST":
        nombre = request.form["nombre"].strip()
        categoria = request.form.get("categoria", "").strip() or "Otros equipos"

        if TipoEquipo.query.filter_by(nombre=nombre).first():
            flash(f"Ya existe un tipo de equipo llamado '{nombre}'.", "danger")
            return render_template("tipos_equipo/form.html", categorias=categorias_existentes)

        tipo = TipoEquipo(nombre=nombre, categoria=categoria)
        db.session.add(tipo)
        db.session.commit()
        flash(
            f"Tipo de equipo '{tipo.nombre}' creado. Ya lo podés elegir al cargar un equipo o al definir "
            "a qué tipo de equipo aplica un formulario.",
            "success",
        )
        return redirect(url_for("tipos_equipo.listar"))

    return render_template("tipos_equipo/form.html", categorias=categorias_existentes)


@tipos_equipo_bp.route("/<int:tipo_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def editar(tipo_id):
    tipo = TipoEquipo.query.get_or_404(tipo_id)
    categorias_existentes = sorted({t.categoria for t in TipoEquipo.query.all()} | set(CATEGORIAS_EQUIPO_ORDEN))

    if request.method == "POST":
        nombre = request.form["nombre"].strip()
        categoria = request.form.get("categoria", "").strip() or "Otros equipos"

        duplicado = TipoEquipo.query.filter(TipoEquipo.nombre == nombre, TipoEquipo.id != tipo.id).first()
        if duplicado:
            flash(f"Ya existe un tipo de equipo llamado '{nombre}'.", "danger")
            return render_template("tipos_equipo/form.html", tipo=tipo, categorias=categorias_existentes)

        nombre_anterior = tipo.nombre
        if nombre != nombre_anterior:
            # El nombre se guarda como texto en Equipo/TipoFormulario/ServicioTipo
            # (no hay FK), así que renombrar acá tiene que arrastrar esas referencias.
            Equipo.query.filter_by(tipo=nombre_anterior).update({"tipo": nombre})
            TipoFormulario.query.filter_by(tipo_equipo_aplicable=nombre_anterior).update(
                {"tipo_equipo_aplicable": nombre}
            )
            ServicioTipo.query.filter_by(tipo_equipo_aplicable=nombre_anterior).update(
                {"tipo_equipo_aplicable": nombre}
            )

        tipo.nombre = nombre
        tipo.categoria = categoria
        db.session.commit()
        flash(f"Tipo de equipo '{tipo.nombre}' actualizado.", "success")
        return redirect(url_for("tipos_equipo.listar"))

    return render_template("tipos_equipo/form.html", tipo=tipo, categorias=categorias_existentes)


@tipos_equipo_bp.route("/<int:tipo_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def eliminar(tipo_id):
    tipo = TipoEquipo.query.get_or_404(tipo_id)
    en_uso = (
        Equipo.query.filter_by(tipo=tipo.nombre).first()
        or TipoFormulario.query.filter_by(tipo_equipo_aplicable=tipo.nombre).first()
        or ServicioTipo.query.filter_by(tipo_equipo_aplicable=tipo.nombre).first()
    )
    if en_uso:
        flash(
            f"'{tipo.nombre}' está en uso (hay equipos o formularios cargados con este tipo); no se puede eliminar.",
            "danger",
        )
        return redirect(url_for("tipos_equipo.listar"))

    nombre = tipo.nombre
    db.session.delete(tipo)
    db.session.commit()
    flash(f"Tipo de equipo '{nombre}' eliminado.", "info")
    return redirect(url_for("tipos_equipo.listar"))
