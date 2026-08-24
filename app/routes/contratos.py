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
    categoria_de_tipo_equipo,
)
from app.utils import TIPOS_CAMPO

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
            f"Servicio contratado '{contrato.nombre}' creado (vigente hasta {contrato.fecha_fin.strftime('%m/%Y')}). "
            "Ahora agregá los servicios contratados. Cada mes vas a poder coordinar con el cliente "
            "la fecha real de la visita desde la pantalla de Coordinación.",
            "success",
        )
        return redirect(url_for("contratos.detalle", contrato_id=contrato.id))
    return render_template("contratos/form.html", instalacion=instalacion, contrato=None)


@contratos_bp.route("/instalacion/<int:instalacion_id>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def listar_por_instalacion(instalacion_id):
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_acceso_cliente(instalacion.cliente)
    contratos = sorted(instalacion.contratos, key=lambda c: c.fecha_inicio, reverse=True)
    return render_template("contratos/listar.html", instalacion=instalacion, contratos=contratos)


@contratos_bp.route("/<int:contrato_id>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def detalle(contrato_id):
    contrato = Contrato.query.get_or_404(contrato_id)
    verificar_acceso_cliente(contrato.instalacion.cliente)
    visitas = sorted(contrato.visitas, key=lambda v: v.fecha, reverse=True)
    cliente = contrato.instalacion.cliente
    # oculto=True son servicios "miembro" de un paquete (ej. Bomba jockey,
    # parte de "Inspecciones y pruebas en sala de bombas") -- no se ofrecen
    # sueltos acá, solo a través del paquete (ver nuevo_servicio).
    servicios_tipo = (
        ServicioTipo.query.filter_by(empresa_id=cliente.empresa_id, oculto=False)
        .order_by(ServicioTipo.nombre).all()
    )
    # El formulario de cada servicio contratado es la copia que se importó
    # al cliente al agregarlo (ver nuevo_servicio) — se busca por nombre
    # porque ServicioContrato no tiene FK directa a ella. Un servicio
    # "paquete" (categoria seteada) no tiene un único formulario propio --
    # importó uno por cada tipo de equipo que agrupa (ver miembros_por_servicio).
    formularios_por_servicio = {
        s.id: TipoFormulario.query.filter_by(cliente_id=cliente.id, nombre=s.nombre).first()
        for s in contrato.servicios if not s.categoria
    }
    miembros_por_servicio = {
        s.id: [
            t for t in TipoFormulario.query.filter_by(cliente_id=cliente.id, por_equipo=True).all()
            if categoria_de_tipo_equipo(t.tipo_equipo_aplicable) == s.categoria
        ]
        for s in contrato.servicios if s.categoria
    }
    hoy = date.today()
    proxima_visita = min(
        (v for v in visitas if v.fecha >= hoy and v.estado != "Cancelado"),
        key=lambda v: v.fecha,
        default=None,
    )
    return render_template(
        "contratos/detail.html", contrato=contrato, visitas=visitas, frecuencias=FRECUENCIAS_DISPONIBLES,
        servicios_tipo=servicios_tipo, formularios_por_servicio=formularios_por_servicio,
        miembros_por_servicio=miembros_por_servicio, etiquetas_tipo_campo=dict(TIPOS_CAMPO),
        proxima_visita=proxima_visita,
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
        flash(f"Servicio contratado '{contrato.nombre}' actualizado.", "success")
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
    flash(f"Servicio contratado '{contrato.nombre}' eliminado.", "info")
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

    if servicio_tipo.categoria:
        # Paquete (ej. "Inspecciones y pruebas en sala de bombas"): no
        # tiene campos propios, así que no hay nada suyo para importar --
        # en cambio, importa el checklist de cada tipo de equipo que
        # agrupa, para que la pantalla combinada de la visita
        # (formularios.checklist_categoria) tenga con qué armarse.
        miembros = [
            st for st in ServicioTipo.query.filter_by(empresa_id=servicio_tipo.empresa_id, por_equipo=True).all()
            if categoria_de_tipo_equipo(st.tipo_equipo_aplicable) == servicio_tipo.categoria
            and st.incluir_en_carga_combinada
        ]
        for miembro in miembros:
            TipoFormulario.desde_catalogo(miembro, cliente.id)
    elif not servicio_tipo.es_curva_caudal:
        # La curva de caudal no usa el sistema de formularios genérico — el
        # ítem de la visita ofrece directamente la pantalla de ensayo de la
        # bomba (ver visitas.detalle), así que no hace falta importar un
        # TipoFormulario para esto.
        TipoFormulario.desde_catalogo(servicio_tipo, cliente.id)

    fecha_inicio_servicio = _parse_mes(request.form.get("mes_inicio"))  # None = usa el del contrato
    servicio = ServicioContrato(
        contrato_id=contrato.id,
        nombre=servicio_tipo.nombre,
        frecuencia=request.form["frecuencia"],
        fecha_inicio=fecha_inicio_servicio,
        activo=True,
        tipo_equipo_aplicable=servicio_tipo.tipo_equipo_aplicable,
        categoria=servicio_tipo.categoria,
        es_curva_caudal=servicio_tipo.es_curva_caudal,
    )
    db.session.add(servicio)
    db.session.commit()
    if servicio.fechas_ocurrencia():
        flash(
            f"Servicio '{servicio.nombre}' agregado. Se va a incluir la próxima vez que se generen las "
            "solicitudes de coordinación del mes que le toque.",
            "success",
        )
    else:
        flash(
            f"Servicio '{servicio.nombre}' agregado, pero no cae ningún mes dentro de lo que queda del año "
            "del servicio contratado (el mes de inicio elegido + la frecuencia excede su fecha de fin).",
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
    flash(f"Servicio '{servicio.nombre}' eliminado.", "info")
    return redirect(url_for("contratos.detalle", contrato_id=contrato.id))
