from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import rol_requerido, verificar_acceso_cliente, verificar_escritura_cliente
from app.models import DatosEquipoBase, Equipo, TipoFormulario

datos_motor_bp = Blueprint("datos_motor", __name__, url_prefix="/equipos")


def _plantillas_disponibles(equipo):
    """Tipos de formulario 'dato de base' aplicables a este equipo: los que
    no tienen tipo_equipo_aplicable (sirven para cualquier tipo) más los
    que aplican puntualmente al tipo de este equipo."""
    return (
        TipoFormulario.query.filter_by(cliente_id=equipo.instalacion.cliente_id, es_dato_base=True)
        .filter((TipoFormulario.tipo_equipo_aplicable == equipo.tipo) | (TipoFormulario.tipo_equipo_aplicable.is_(None)))
        .order_by(TipoFormulario.nombre)
        .all()
    )


@datos_motor_bp.route("/<int:equipo_id>/datos-base")
@rol_requerido("Administrador", "Jefe", "Técnico")
def listar(equipo_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    verificar_acceso_cliente(equipo.instalacion.cliente)
    return render_template(
        "equipos/datos_base_lista.html",
        equipo=equipo,
        datos=equipo.datos_base,
        plantillas_disponibles=_plantillas_disponibles(equipo),
    )


@datos_motor_bp.route("/<int:equipo_id>/datos-base/elegir")
@rol_requerido("Administrador", "Jefe", "Técnico")
def elegir(equipo_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    verificar_escritura_cliente(equipo.instalacion.cliente)
    plantillas = _plantillas_disponibles(equipo)
    if not plantillas:
        flash(
            f"Todavía no hay ninguna plantilla de dato de base aplicable a equipos tipo '{equipo.tipo}'. "
            "Un Administrador puede crear una desde Formularios del cliente.",
            "warning",
        )
        return redirect(url_for("datos_motor.listar", equipo_id=equipo.id))
    return render_template("equipos/datos_base_elegir.html", equipo=equipo, plantillas=plantillas)


@datos_motor_bp.route("/<int:equipo_id>/datos-base/<int:tipo_formulario_id>", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def cargar(equipo_id, tipo_formulario_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    verificar_escritura_cliente(equipo.instalacion.cliente)
    tipo = TipoFormulario.query.get_or_404(tipo_formulario_id)
    if not tipo.es_dato_base or tipo.cliente_id != equipo.instalacion.cliente_id:
        abort(403)

    registro = DatosEquipoBase.query.filter_by(equipo_id=equipo.id, tipo_formulario_id=tipo.id).first()

    if request.method == "POST":
        datos = {}
        for campo in tipo.campos():
            if campo["tipo"] == "multi_seleccion":
                datos[campo["campo"]] = request.form.getlist(campo["campo"])
            else:
                datos[campo["campo"]] = request.form.get(campo["campo"])
        es_nuevo = registro is None
        if es_nuevo:
            registro = DatosEquipoBase(equipo_id=equipo.id, tipo_formulario_id=tipo.id)
            db.session.add(registro)
        registro.set_datos(datos)
        registro.cargado_por_id = current_user.id
        db.session.commit()
        verbo = "cargado" if es_nuevo else "actualizado"
        flash(f"'{tipo.nombre}' {verbo} para '{equipo.nombre}'.", "success")
        return redirect(url_for("datos_motor.listar", equipo_id=equipo.id))

    return render_template("equipos/datos_base_form.html", equipo=equipo, tipo=tipo, registro=registro)


@datos_motor_bp.route("/<int:equipo_id>/datos-base/<int:datos_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def eliminar(equipo_id, datos_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    verificar_escritura_cliente(equipo.instalacion.cliente)
    registro = DatosEquipoBase.query.get_or_404(datos_id)
    if registro.equipo_id != equipo.id:
        abort(404)

    nombre = registro.tipo_formulario.nombre
    db.session.delete(registro)
    db.session.commit()
    flash(f"'{nombre}' eliminado de '{equipo.nombre}'.", "info")
    return redirect(url_for("datos_motor.listar", equipo_id=equipo.id))
