from datetime import date, datetime

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import clientes_visibles, rol_requerido, tecnicos_de_la_empresa, verificar_acceso_cliente
from app.models import (
    ESTADOS_OT,
    Instalacion,
    OrdenTrabajo,
    PRIORIDADES_OT,
    Repuesto,
    RepuestoUsado,
    TIPOS_OT,
    TIPOS_OT_MANUAL,
    Usuario,
)
from app.pdf_ot import generar_pdf_ot

ordenes_bp = Blueprint("ordenes", __name__, url_prefix="/ordenes-trabajo")

# División de tareas acordada: el Administrador asigna técnico y repuestos,
# y cambia el estado/cierra la OT. El Técnico ve solo las OT que tiene
# asignadas, y puede cargar ahí los repuestos que usó (se descuentan del
# stock en el momento).


def _parse_fecha(valor, por_defecto=None):
    if not valor:
        return por_defecto
    return datetime.strptime(valor, "%Y-%m-%d").date()


def _verificar_acceso_ot(ot):
    """Además de pertenecer a un cliente visible, un Técnico solo puede
    tocar las OT que tiene asignadas a él."""
    verificar_acceso_cliente(ot.instalacion.cliente)
    if current_user.rol == "Técnico" and ot.tecnico_id != current_user.id:
        abort(403)


@ordenes_bp.route("/")
@rol_requerido("Administrador", "Jefe", "Técnico")
def listar():
    """Cola de trabajo. El Administrador/Jefe ve todas las OT de su
    empresa, con filtro por estado disponible. El Técnico ve solo las que
    tiene asignadas, y solo lo que le queda por hacer (sin Finalizada ni
    Cancelada, sin filtro de estado — va directo a lo suyo)."""
    ids_clientes = [c.id for c in clientes_visibles().all()]
    query = OrdenTrabajo.query.join(Instalacion).filter(Instalacion.cliente_id.in_(ids_clientes))

    if current_user.rol == "Técnico":
        query = query.filter(OrdenTrabajo.tecnico_id == current_user.id)
        query = query.filter(OrdenTrabajo.estado.notin_(["Finalizada", "Cancelada"]))
        estado_filtro = ""
    else:
        estado_filtro = request.args.get("estado", "")
        if estado_filtro:
            query = query.filter(OrdenTrabajo.estado == estado_filtro)

    ordenes = query.order_by(OrdenTrabajo.fecha_apertura.desc()).all()
    return render_template(
        "ordenes_trabajo/list.html", ordenes=ordenes, estados=ESTADOS_OT, estado_filtro=estado_filtro
    )


@ordenes_bp.route("/nueva", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def nueva():
    """Alta de una OT correctiva (trabajo suelto, sin contrato de por medio)."""
    ids_clientes = [c.id for c in clientes_visibles().all()]
    instalaciones = (
        Instalacion.query.join(Instalacion.cliente)
        .filter(Instalacion.cliente_id.in_(ids_clientes))
        .order_by(Instalacion.nombre)
        .all()
    )
    tecnicos = tecnicos_de_la_empresa()

    if request.method == "POST":
        instalacion = Instalacion.query.get_or_404(int(request.form["instalacion_id"]))
        verificar_acceso_cliente(instalacion.cliente)
        tecnico_id = request.form.get("tecnico_id")
        ot = OrdenTrabajo(
            instalacion_id=instalacion.id,
            tipo=request.form.get("tipo", "Correctivo"),
            prioridad=request.form.get("prioridad", "Media"),
            estado="Pendiente",
            tecnico_id=int(tecnico_id) if tecnico_id else None,
            descripcion=request.form.get("descripcion"),
            fecha_apertura=_parse_fecha(request.form.get("fecha_apertura"), date.today()),
        )
        db.session.add(ot)
        db.session.flush()
        ot.asignar_numero()
        db.session.commit()
        flash(f"Orden de trabajo {ot.numero} creada.", "success")
        return redirect(url_for("ordenes.detalle", ot_id=ot.id))

    return render_template(
        "ordenes_trabajo/form.html",
        instalaciones=instalaciones,
        prioridades=PRIORIDADES_OT,
        tipos=TIPOS_OT_MANUAL,
        tecnicos=tecnicos,
    )


@ordenes_bp.route("/<int:ot_id>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def detalle(ot_id):
    ot = OrdenTrabajo.query.get_or_404(ot_id)
    _verificar_acceso_ot(ot)
    repuestos_disponibles = Repuesto.query.filter_by(
        activo=True, empresa_id=current_user.empresa_id
    ).order_by(Repuesto.nombre).all()
    return render_template("ordenes_trabajo/detail.html", ot=ot, repuestos_disponibles=repuestos_disponibles)


@ordenes_bp.route("/<int:ot_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def editar(ot_id):
    ot = OrdenTrabajo.query.get_or_404(ot_id)
    verificar_acceso_cliente(ot.instalacion.cliente)
    tecnicos = tecnicos_de_la_empresa()
    if request.method == "POST":
        nuevo_estado = request.form.get("estado", ot.estado)
        if nuevo_estado == "Finalizada" and ot.visita and ot.visita.observaciones_pendientes_de_revision:
            flash(
                "No se puede finalizar: la visita asociada tiene observaciones sin aprobar. "
                "Aprobalas primero (podés hacerlo desde 'Cerrar visita').",
                "danger",
            )
            return redirect(url_for("ordenes.editar", ot_id=ot.id))
        ot.tipo = request.form.get("tipo", ot.tipo)
        ot.prioridad = request.form.get("prioridad", ot.prioridad)
        ot.estado = nuevo_estado
        tecnico_id = request.form.get("tecnico_id")
        ot.tecnico_id = int(tecnico_id) if tecnico_id else None
        ot.descripcion = request.form.get("descripcion")
        ot.observaciones = request.form.get("observaciones")
        if ot.estado == "Finalizada" and not ot.fecha_cierre:
            ot.fecha_cierre = date.today()
        db.session.commit()
        flash(f"Orden {ot.numero} actualizada.", "success")
        return redirect(url_for("ordenes.detalle", ot_id=ot.id))
    return render_template(
        "ordenes_trabajo/editar.html", ot=ot, estados=ESTADOS_OT, prioridades=PRIORIDADES_OT, tipos=TIPOS_OT, tecnicos=tecnicos
    )


@ordenes_bp.route("/<int:ot_id>/pdf")
@rol_requerido("Administrador", "Jefe", "Técnico")
def pdf(ot_id):
    ot = OrdenTrabajo.query.get_or_404(ot_id)
    _verificar_acceso_ot(ot)
    pdf_bytes = generar_pdf_ot(ot)
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"inline; filename={ot.numero}.pdf"},
    )


@ordenes_bp.route("/<int:ot_id>/repuestos/agregar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def agregar_repuesto(ot_id):
    """El técnico carga acá directamente lo que usó — se descuenta del
    stock en el momento (sin paso previo de 'asignación')."""
    ot = OrdenTrabajo.query.get_or_404(ot_id)
    _verificar_acceso_ot(ot)
    repuesto = Repuesto.query.get_or_404(int(request.form["repuesto_id"]))
    if repuesto.empresa_id != current_user.empresa_id:
        abort(403)
    cantidad = int(request.form["cantidad"])

    uso = RepuestoUsado(orden_trabajo_id=ot.id, repuesto_id=repuesto.id, cantidad=cantidad)
    repuesto.stock_actual -= cantidad
    db.session.add(uso)
    db.session.commit()
    flash(f"Se descontaron {cantidad} {repuesto.unidad}(s) de '{repuesto.nombre}' del stock.", "success")
    return redirect(url_for("ordenes.detalle", ot_id=ot.id))


@ordenes_bp.route("/<int:ot_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def eliminar(ot_id):
    """Solo se pueden eliminar OT sueltas (correctivas, sin visita
    planificada detrás) — las que vienen de una visita se borran borrando
    la visita (o el contrato), así todo ese árbol queda consistente."""
    ot = OrdenTrabajo.query.get_or_404(ot_id)
    verificar_acceso_cliente(ot.instalacion.cliente)
    if ot.visita_id:
        flash(
            f"La OT {ot.numero} está ligada a una visita planificada; para eliminarla, eliminá la visita "
            "(o el contrato) en vez de la OT directamente.",
            "danger",
        )
        return redirect(url_for("ordenes.detalle", ot_id=ot.id))

    for uso in list(ot.repuestos_usados):
        uso.repuesto.stock_actual += uso.cantidad  # repone el stock consumido antes de borrar

    numero = ot.numero
    db.session.delete(ot)
    db.session.commit()
    flash(f"Orden de trabajo {numero} eliminada. Stock de repuestos usados restituido.", "info")
    return redirect(url_for("ordenes.listar"))


@ordenes_bp.route("/repuestos-usados/<int:uso_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar_repuesto_usado(uso_id):
    uso = RepuestoUsado.query.get_or_404(uso_id)
    _verificar_acceso_ot(uso.orden_trabajo)
    ot_id = uso.orden_trabajo_id
    uso.repuesto.stock_actual += uso.cantidad  # repone el stock al deshacer el uso
    db.session.delete(uso)
    db.session.commit()
    flash("Uso de repuesto eliminado; stock repuesto.", "info")
    return redirect(url_for("ordenes.detalle", ot_id=ot_id))
