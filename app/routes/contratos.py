from datetime import date, datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import (
    rol_requerido,
    verificar_acceso_cliente,
    verificar_escritura_cliente,
    verificar_password_confirmacion,
)
from app.models import (
    Contrato,
    ESTADOS_CONTRATO,
    FRECUENCIAS_DISPONIBLES,
    Instalacion,
    ServicioContrato,
    ServicioTipo,
    TipoFormulario,
)

contratos_bp = Blueprint("contratos", __name__, url_prefix="/contratos")


def _parse_mes(valor, por_defecto=None):
    """Parsea un <input type="month"> ('YYYY-MM') a una fecha con día 1.
    El día real de cada visita se define más adelante, editando la visita
    puntual una vez que el cliente confirma la fecha."""
    if not valor:
        return por_defecto
    anio, mes = valor.split("-")
    return date(int(anio), int(mes), 1)


@contratos_bp.route("/nuevo/<int:instalacion_id>", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def nuevo(instalacion_id):
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_escritura_cliente(instalacion.cliente)
    if request.method == "POST":
        fecha_inicio = _parse_mes(request.form.get("mes_inicio"), date.today().replace(day=1))
        contrato = Contrato(
            instalacion_id=instalacion.id,
            nombre=request.form["nombre"],
            fecha_inicio=fecha_inicio,
            fecha_fin=Contrato.calcular_fecha_fin(fecha_inicio),
            estado="Activo",
            activo=True,
        )
        db.session.add(contrato)
        db.session.commit()
        flash(
            f"Contrato '{contrato.nombre}' creado (vigente hasta {contrato.fecha_fin.strftime('%m/%Y')}). "
            "Ahora agregá los servicios contratados para generar las visitas automáticamente. "
            "El día exacto de cada visita se termina de definir más adelante, cuando el cliente lo confirme.",
            "success",
        )
        return redirect(url_for("contratos.detalle", contrato_id=contrato.id))
    return render_template("contratos/form.html", instalacion=instalacion, contrato=None)


@contratos_bp.route("/<int:contrato_id>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def detalle(contrato_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    verificar_acceso_cliente(contrato.instalacion.cliente)
    visitas = sorted(contrato.visitas, key=lambda v: v.fecha)
    empresa_id = contrato.instalacion.cliente.empresa_id
    servicios_tipo = ServicioTipo.query.filter_by(empresa_id=empresa_id).order_by(ServicioTipo.nombre).all()
    return render_template(
        "contratos/detail.html", contrato=contrato, visitas=visitas, frecuencias=FRECUENCIAS_DISPONIBLES,
        servicios_tipo=servicios_tipo,
    )


@contratos_bp.route("/<int:contrato_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def editar(contrato_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    verificar_escritura_cliente(contrato.instalacion.cliente)
    if request.method == "POST":
        contrato.nombre = request.form["nombre"]
        contrato.estado = request.form.get("estado", contrato.estado)
        contrato.activo = bool(request.form.get("activo"))
        db.session.commit()
        flash(f"Contrato '{contrato.nombre}' actualizado.", "success")
        return redirect(url_for("contratos.detalle", contrato_id=contrato.id))
    return render_template(
        "contratos/editar.html", contrato=contrato, estados=ESTADOS_CONTRATO
    )


@contratos_bp.route("/<int:contrato_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar(contrato_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    verificar_escritura_cliente(contrato.instalacion.cliente)
    if not verificar_password_confirmacion():
        return redirect(url_for("contratos.detalle", contrato_id=contrato.id))
    instalacion_id = contrato.instalacion_id
    db.session.delete(contrato)
    db.session.commit()
    flash(f"Contrato '{contrato.nombre}' eliminado.", "info")
    return redirect(url_for("instalaciones.detalle", instalacion_id=instalacion_id))


@contratos_bp.route("/<int:contrato_id>/servicios/nuevo", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def nuevo_servicio(contrato_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    verificar_escritura_cliente(contrato.instalacion.cliente)

    servicio_tipo_id = request.form.get("servicio_tipo_id", type=int)
    servicio_tipo = ServicioTipo.query.get_or_404(servicio_tipo_id)
    if current_user.rol != "Super Admin" and servicio_tipo.empresa_id != current_user.empresa_id:
        abort(403)

    cliente = contrato.instalacion.cliente

    # Importa el formulario base al cliente — si ya tenía uno con ese
    # nombre (lo importó antes, o lo cargó a mano), se reutiliza tal cual
    # en vez de duplicar; de ahí en más queda como una copia independiente.
    tipo_formulario = TipoFormulario.query.filter_by(cliente_id=cliente.id, nombre=servicio_tipo.nombre).first()
    if not tipo_formulario:
        tipo_formulario = TipoFormulario(
            cliente_id=cliente.id,
            nombre=servicio_tipo.nombre,
            descripcion=servicio_tipo.descripcion,
            por_equipo=servicio_tipo.por_equipo,
            tipo_equipo_aplicable=servicio_tipo.tipo_equipo_aplicable,
            schema_json=servicio_tipo.schema_json,
        )
        db.session.add(tipo_formulario)

    fecha_inicio_servicio = _parse_mes(request.form.get("mes_inicio"))  # None = usa el del contrato
    servicio = ServicioContrato(
        contrato_id=contrato.id,
        nombre=servicio_tipo.nombre,
        frecuencia=request.form["frecuencia"],
        fecha_inicio=fecha_inicio_servicio,
        activo=True,
    )
    db.session.add(servicio)
    db.session.commit()
    # Regenera automáticamente todas las visitas del contrato agrupando por fecha
    contrato.generar_visitas()
    if servicio.fechas_ocurrencia():
        flash(
            f"Servicio '{servicio.nombre}' agregado. Visitas del contrato regeneradas y agrupadas por fecha.",
            "success",
        )
    else:
        flash(
            f"Servicio '{servicio.nombre}' agregado, pero no generó ninguna visita dentro de lo que queda "
            "del año de contrato (el mes de inicio elegido + la frecuencia excede la fecha de fin del contrato).",
            "warning",
        )
    return redirect(url_for("contratos.detalle", contrato_id=contrato.id))


@contratos_bp.route("/servicios/<int:servicio_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar_servicio(servicio_id):
    servicio = ServicioContrato.query.get_or_404(servicio_id)
    contrato = servicio.contrato
    verificar_escritura_cliente(contrato.instalacion.cliente)
    db.session.delete(servicio)
    db.session.commit()
    contrato.generar_visitas()
    flash(f"Servicio '{servicio.nombre}' eliminado y visitas regeneradas.", "info")
    return redirect(url_for("contratos.detalle", contrato_id=contrato.id))
