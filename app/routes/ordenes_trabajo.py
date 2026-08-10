from datetime import date, datetime

from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, url_for
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
from app.notificaciones import notificar_usuario
from app.pdf_ot import generar_pdf_ot
from app.utils import es_ajax

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


def _datos_lista():
    """Cola de trabajo + resumen, compartido por listar() y detalle() — las
    dos rutas renderizan el mismo template de lista+detalle lado a lado, así
    que las dos necesitan la lista completa (ver ordenes_trabajo/list.html).
    El Administrador/Jefe ve todas las OT de su empresa. El Técnico ve solo
    las que tiene asignadas, y solo lo que le queda por hacer (sin
    Finalizada ni Cancelada — va directo a lo suyo)."""
    ids_clientes = [c.id for c in clientes_visibles().all()]
    query = OrdenTrabajo.query.join(Instalacion).filter(Instalacion.cliente_id.in_(ids_clientes))

    if current_user.rol == "Técnico":
        query = query.filter(OrdenTrabajo.tecnico_id == current_user.id)
        query = query.filter(OrdenTrabajo.estado.notin_(["Finalizada", "Cancelada"]))

    ordenes = query.order_by(OrdenTrabajo.fecha_apertura.desc()).all()

    hoy = date.today()
    abiertas = [o for o in ordenes if o.estado not in ("Finalizada", "Cancelada")]
    urgentes = [o for o in abiertas if o.prioridad in ("Urgente", "Alta")]
    sin_asignar = [o for o in abiertas if not o.tecnico_id]
    finalizadas_mes = [
        o
        for o in ordenes
        if o.estado == "Finalizada" and o.fecha_cierre and o.fecha_cierre.year == hoy.year and o.fecha_cierre.month == hoy.month
    ]

    return dict(
        ordenes=ordenes,
        estados=ESTADOS_OT,
        hoy=hoy,
        abiertas=abiertas,
        urgentes=urgentes,
        sin_asignar=sin_asignar,
        finalizadas_mes=finalizadas_mes,
    )


@ordenes_bp.route("/")
@rol_requerido("Administrador", "Jefe", "Técnico")
def listar():
    """Sin una OT puntual en la URL, se abre con la primera de la lista
    seleccionada (la más reciente) — así la pantalla nunca arranca con el
    panel de detalle vacío si hay algo para mostrar."""
    datos = _datos_lista()
    ot_actual = datos["ordenes"][0] if datos["ordenes"] else None
    repuestos_disponibles = _repuestos_disponibles() if ot_actual else []
    return render_template(
        "ordenes_trabajo/list.html", ot_actual=ot_actual, repuestos_disponibles=repuestos_disponibles, **datos
    )


def _repuestos_disponibles():
    return Repuesto.query.filter_by(activo=True, empresa_id=current_user.empresa_id).order_by(Repuesto.nombre).all()


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
        if ot.tecnico_id:
            notificar_usuario(
                ot.tecnico_usuario,
                tipo="ot_asignada",
                titulo=f"OT {ot.numero} asignada — {instalacion.nombre}",
                empresa_id=current_user.empresa_id,
                cliente_id=instalacion.cliente_id,
                enlace=url_for("ordenes.detalle", ot_id=ot.id),
                remitente=current_user,
            )
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
    repuestos_disponibles = _repuestos_disponibles()
    if es_ajax():
        # Refresco parcial del panel de detalle (ver #contenido-refrescable
        # en list.html) -- lo usa el modal de "cambiar técnico" para
        # actualizar el nombre sin recargar toda la lista de OT.
        return render_template(
            "ordenes_trabajo/_detalle_fragment.html", ot_actual=ot, repuestos_disponibles=repuestos_disponibles
        )
    datos = _datos_lista()
    return render_template(
        "ordenes_trabajo/list.html", ot_actual=ot, repuestos_disponibles=repuestos_disponibles, **datos
    )


@ordenes_bp.route("/<int:ot_id>/asignar-tecnico", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def asignar_tecnico(ot_id):
    """Cambiar el técnico de una OT ya existente sin pasar por 'Editar OT'
    completo -- se abre como modal desde el detalle (ver data-modal-form
    en _detalle_fragment.html)."""
    ot = OrdenTrabajo.query.get_or_404(ot_id)
    verificar_acceso_cliente(ot.instalacion.cliente)
    tecnicos = tecnicos_de_la_empresa()

    if request.method == "POST":
        tecnico_id_anterior = ot.tecnico_id
        tecnico_id = request.form.get("tecnico_id")
        ot.tecnico_id = int(tecnico_id) if tecnico_id else None
        if ot.tecnico_id and ot.estado == "Pendiente":
            ot.estado = "Asignada"
        db.session.commit()
        if ot.tecnico_id and ot.tecnico_id != tecnico_id_anterior:
            notificar_usuario(
                ot.tecnico_usuario,
                tipo="ot_asignada",
                titulo=f"OT {ot.numero} asignada — {ot.instalacion.nombre}",
                empresa_id=current_user.empresa_id,
                cliente_id=ot.instalacion.cliente_id,
                enlace=url_for("ordenes.detalle", ot_id=ot.id),
                remitente=current_user,
            )
        mensaje = f"Técnico asignado: {ot.nombre_tecnico}." if ot.tecnico_id else "OT sin técnico asignado."
        if es_ajax():
            return jsonify(ok=True, mensaje=mensaje)
        flash(mensaje, "success")
        return redirect(url_for("ordenes.detalle", ot_id=ot.id))

    template = "ordenes_trabajo/_asignar_tecnico_fragment.html" if es_ajax() else "ordenes_trabajo/asignar_tecnico.html"
    return render_template(template, ot=ot, tecnicos=tecnicos)


@ordenes_bp.route("/<int:ot_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def editar(ot_id):
    """Tipo, prioridad, descripción y observaciones -- el técnico se
    asigna aparte (ver ordenes.asignar_tecnico) y, si la OT tiene una
    visita ligada, el estado también se maneja aparte (lo define la fase
    de la visita: Abierta/En revisión/Cerrada -- ver visitas.enviar_revision
    / visitas.cerrar) en vez de un campo editable acá, para no tener dos
    estados de la misma OT desincronizados entre sí."""
    ot = OrdenTrabajo.query.get_or_404(ot_id)
    verificar_acceso_cliente(ot.instalacion.cliente)
    if request.method == "POST":
        nuevo_estado = request.form.get("estado", ot.estado) if not ot.visita_id else ot.estado
        if nuevo_estado == "Finalizada" and ot.visita and ot.visita.observaciones_pendientes_de_revision:
            mensaje = (
                "No se puede finalizar: la visita asociada tiene observaciones sin aprobar. "
                "Aprobalas primero (podés hacerlo desde 'Cerrar visita')."
            )
            if es_ajax():
                return jsonify(ok=False, mensaje=mensaje), 400
            flash(mensaje, "danger")
            return redirect(url_for("ordenes.editar", ot_id=ot.id))
        ot.tipo = request.form.get("tipo", ot.tipo)
        ot.prioridad = request.form.get("prioridad", ot.prioridad)
        ot.estado = nuevo_estado
        ot.descripcion = request.form.get("descripcion")
        ot.observaciones = request.form.get("observaciones")
        if ot.estado == "Finalizada" and not ot.fecha_cierre:
            ot.fecha_cierre = date.today()
        # Si esta OT viene de un presupuesto aprobado, terminarla cierra
        # también el presupuesto (el trabajo ya se ejecutó) y resuelve la
        # deficiencia que lo originó — sin depender de que alguien se
        # acuerde de tocar esas dos pantallas por separado.
        if ot.estado == "Finalizada" and ot.presupuesto_origen and ot.presupuesto_origen.estado != "Cerrado":
            presupuesto = ot.presupuesto_origen
            presupuesto.cambiar_estado("Cerrado", current_user.id, "Cerrado automáticamente al finalizar la OT.")
            presupuesto.observacion.marcar_resuelta(current_user.id)
        db.session.commit()
        mensaje = f"Orden {ot.numero} actualizada."
        if es_ajax():
            return jsonify(ok=True, mensaje=mensaje)
        flash(mensaje, "success")
        return redirect(url_for("ordenes.detalle", ot_id=ot.id))

    template = "ordenes_trabajo/_editar_fragment.html" if es_ajax() else "ordenes_trabajo/editar.html"
    return render_template(template, ot=ot, estados=ESTADOS_OT, prioridades=PRIORIDADES_OT, tipos=TIPOS_OT)


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

    if cantidad <= 0:
        flash("La cantidad tiene que ser mayor a 0.", "danger")
        return redirect(url_for("ordenes.detalle", ot_id=ot.id))
    if cantidad > repuesto.stock_actual:
        flash(
            f"No hay suficiente stock de '{repuesto.nombre}': quedan {repuesto.stock_actual} {repuesto.unidad}(s).",
            "danger",
        )
        return redirect(url_for("ordenes.detalle", ot_id=ot.id))

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
