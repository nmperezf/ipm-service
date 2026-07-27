from datetime import date, datetime

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.auth_utils import (
    rol_requerido,
    tecnicos_de_la_empresa,
    verificar_acceso_cliente,
    verificar_escritura_cliente,
    verificar_visita_editable,
)
from app import db
from app.models import (
    ESTADOS_VISITA,
    Formulario,
    Instalacion,
    ItemVisita,
    Observacion,
    OrdenTrabajo,
    TipoFormulario,
    Usuario,
    Visita,
    categorias_equipo_agrupadas,
)
from app.pdf_devolucion import generar_pdf_devolucion

visitas_bp = Blueprint("visitas", __name__, url_prefix="/visitas")

# Nota: las pantallas de visita son de trabajo técnico (checklists, edición
# de estado, etc). El portal del rol Cliente (Fase 4, todavía sin construir)
# va a mostrar una vista curada aparte — por ahora estas rutas quedan para
# Administrador y Técnico únicamente.


def _agrupar_tipos_formulario(tipos):
    """Separa los tipos de formulario en las categorías de navegación
    (Sala de bombas / Estaciones de control y alarma / Bocas de incendio /
    Otros equipos) según a qué tipo de equipo aplican, y deja aparte los
    que no son por equipo (checklists generales del servicio)."""
    categorias = categorias_equipo_agrupadas()
    grupos = {nombre: [] for nombre, _ in categorias}
    generales = []
    for tipo in tipos:
        if tipo.por_equipo and tipo.tipo_equipo_aplicable:
            ubicado = False
            for nombre_categoria, tipos_equipo in categorias:
                if tipo.tipo_equipo_aplicable in tipos_equipo:
                    grupos[nombre_categoria].append(tipo)
                    ubicado = True
                    break
            if not ubicado:
                generales.append(tipo)
        else:
            generales.append(tipo)
    return grupos, generales


def _parse_fecha(valor, por_defecto=None):
    if not valor:
        return por_defecto or date.today()
    return datetime.strptime(valor, "%Y-%m-%d").date()


def _resumen_por_categoria(visita):
    """Para el cierre y el PDF de devolución: cuántos equipos se revisaron
    (tienen al menos un formulario cargado en esta visita) por categoría,
    sin repetir el detalle equipo por equipo."""
    ids_items = [it.id for it in visita.items]
    formularios = Formulario.query.filter(Formulario.item_visita_id.in_(ids_items)).all() if ids_items else []

    resumen = []
    for nombre_categoria, tipos_equipo in categorias_equipo_agrupadas():
        equipos_ids = {
            f.equipo_id for f in formularios if f.equipo and f.equipo.tipo in tipos_equipo
        }
        if equipos_ids:
            resumen.append({"categoria": nombre_categoria, "equipos_revisados": len(equipos_ids)})

    # Formularios generales (no ligados a un equipo puntual, ej. checklist mensual)
    generales = [f for f in formularios if not f.equipo_id]
    if generales:
        resumen.append({"categoria": "Otros formularios", "equipos_revisados": len(generales)})

    return resumen


def _antecedentes(visita):
    """Deficiencias abiertas de la misma instalación, de visitas anteriores
    a esta (para que el técnico tenga contexto al cerrar)."""
    ids_items_esta_visita = {it.id for it in visita.items}
    return [
        o
        for o in visita.instalacion.deficiencias
        if not o.resuelto and o.item_visita_id not in ids_items_esta_visita
    ]


@visitas_bp.route("/nueva/<int:instalacion_id>", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def nueva(instalacion_id):
    """Alta manual de una visita suelta (sin contrato asociado), para casos
    puntuales fuera de la planificación automática. Genera su propia OT
    (tipo 'Visita técnica' por defecto) para poder asignarle un técnico,
    igual que las visitas planificadas."""
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_escritura_cliente(instalacion.cliente)
    tecnicos = tecnicos_de_la_empresa(instalacion.cliente.empresa_id)
    if request.method == "POST":
        visita = Visita(
            instalacion_id=instalacion.id,
            fecha=_parse_fecha(request.form.get("fecha")),
            observaciones=request.form.get("observaciones"),
            estado=request.form.get("estado", "Pendiente"),
        )
        db.session.add(visita)
        db.session.flush()

        tecnico_id = request.form.get("tecnico_id")
        ot = OrdenTrabajo(
            instalacion_id=instalacion.id,
            visita_id=visita.id,
            tipo="Visita técnica",
            prioridad="Media",
            estado="Pendiente",
            tecnico_id=int(tecnico_id) if tecnico_id else None,
            descripcion=request.form.get("observaciones"),
            fecha_apertura=visita.fecha,
        )
        db.session.add(ot)
        db.session.flush()
        ot.asignar_numero()

        db.session.commit()
        flash("Visita registrada.", "success")
        return redirect(url_for("visitas.detalle", visita_id=visita.id))

    return render_template(
        "visitas/form.html", instalacion=instalacion, estados=ESTADOS_VISITA, tecnicos=tecnicos
    )


@visitas_bp.route("/<int:visita_id>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def detalle(visita_id):
    visita = Visita.query.get_or_404(visita_id)
    verificar_acceso_cliente(visita.instalacion.cliente)
    tipos = (
        TipoFormulario.query.filter_by(cliente_id=visita.instalacion.cliente_id)
        .order_by(TipoFormulario.nombre)
        .all()
    )
    grupos_formulario, formularios_generales = _agrupar_tipos_formulario(tipos)
    return render_template(
        "visitas/detail.html",
        visita=visita,
        grupos_formulario=grupos_formulario,
        formularios_generales=formularios_generales,
    )


@visitas_bp.route("/<int:visita_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def editar(visita_id):
    """Permite modificar fecha, observaciones y estado de una visita
    programada. El técnico se gestiona desde su OT (un solo lugar)."""
    visita = Visita.query.get_or_404(visita_id)
    verificar_escritura_cliente(visita.instalacion.cliente)
    verificar_visita_editable(visita)
    if request.method == "POST":
        visita.fecha = _parse_fecha(request.form.get("fecha"), visita.fecha)
        visita.observaciones = request.form.get("observaciones")
        visita.estado = request.form.get("estado", visita.estado)
        db.session.commit()
        flash("Visita actualizada.", "success")
        return redirect(url_for("visitas.detalle", visita_id=visita.id))
    return render_template("visitas/editar.html", visita=visita, estados=ESTADOS_VISITA)


@visitas_bp.route("/<int:visita_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar(visita_id):
    visita = Visita.query.get_or_404(visita_id)
    verificar_escritura_cliente(visita.instalacion.cliente)
    verificar_visita_editable(visita)
    instalacion_id = visita.instalacion_id
    db.session.delete(visita)
    db.session.commit()
    flash(f"Visita del {visita.fecha.strftime('%d/%m/%Y')} eliminada.", "info")
    return redirect(url_for("instalaciones.detalle", instalacion_id=instalacion_id))


@visitas_bp.route("/items/<int:item_id>/cumplido", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def marcar_item_cumplido(item_id):
    item = ItemVisita.query.get_or_404(item_id)
    visita = item.visita
    verificar_escritura_cliente(visita.instalacion.cliente)
    verificar_visita_editable(visita)
    visita.marcar_item_cumplido(item_id)
    db.session.commit()
    flash(f"'{item.servicio.nombre}' marcado como cumplido.", "success")
    return redirect(url_for("visitas.detalle", visita_id=visita.id))


@visitas_bp.route("/items/<int:item_id>/pendiente", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def marcar_item_pendiente(item_id):
    item = ItemVisita.query.get_or_404(item_id)
    visita = item.visita
    verificar_escritura_cliente(visita.instalacion.cliente)
    verificar_visita_editable(visita)
    visita.marcar_item_pendiente(item_id)
    db.session.commit()
    flash(f"'{item.servicio.nombre}' marcado como pendiente.", "info")
    return redirect(url_for("visitas.detalle", visita_id=visita.id))


@visitas_bp.route("/<int:visita_id>/enviar-revision", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def enviar_revision(visita_id):
    """El técnico manda la visita al Jefe/Administrador para su revisión.
    A diferencia del cierre, esto SÍ se puede hacer con observaciones sin
    aprobar — es justamente lo que dispara que el Jefe las mire. A partir
    de acá la visita queda congelada para el técnico."""
    visita = Visita.query.get_or_404(visita_id)
    verificar_escritura_cliente(visita.instalacion.cliente)

    if visita.en_revision or visita.cerrada:
        flash("Esta visita ya fue enviada a revisión.", "info")
        return redirect(url_for("visitas.detalle", visita_id=visita.id))

    if request.method == "POST":
        visita.en_revision = True
        visita.fecha_enviada_revision = date.today()
        visita.enviada_por_id = current_user.id
        visita.notas_cierre = request.form.get("notas_cierre")
        firma = request.form.get("firma_cliente")
        if firma:
            visita.firma_cliente = firma
        db.session.commit()
        flash("Visita enviada a revisión.", "success")
        return redirect(url_for("visitas.detalle", visita_id=visita.id))

    items_sin_cumplir = [it for it in visita.items if it.estado != "Cumplido"]

    return render_template(
        "visitas/enviar_revision.html",
        visita=visita,
        antecedentes=_antecedentes(visita),
        resumen=_resumen_por_categoria(visita),
        items_sin_cumplir=items_sin_cumplir,
    )


@visitas_bp.route("/<int:visita_id>/cerrar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def cerrar(visita_id):
    """Solo Administrador/Jefe. Bloqueado mientras la visita tenga
    observaciones sin aprobar. Acá se captura la firma digital del
    cliente, que va al PDF de devolución."""
    visita = Visita.query.get_or_404(visita_id)
    verificar_acceso_cliente(visita.instalacion.cliente)

    if visita.cerrada:
        flash("Esta visita ya está cerrada.", "info")
        return redirect(url_for("visitas.detalle", visita_id=visita.id))

    if not visita.en_revision:
        flash("Esta visita todavía no fue enviada a revisión por el técnico.", "danger")
        return redirect(url_for("visitas.detalle", visita_id=visita.id))

    pendientes = visita.observaciones_pendientes_de_revision

    if request.method == "POST":
        if pendientes:
            flash("No se puede cerrar: todavía hay observaciones sin aprobar.", "danger")
            return redirect(url_for("visitas.cerrar", visita_id=visita.id))
        visita.cerrada = True
        visita.fecha_cierre = date.today()
        visita.notas_cierre = request.form.get("notas_cierre", visita.notas_cierre)
        visita.cerrada_por_id = current_user.id
        firma = request.form.get("firma_cliente")
        if firma:
            visita.firma_cliente = firma
        db.session.commit()
        flash("Visita cerrada. Ya podés descargar el PDF de devolución.", "success")
        return redirect(url_for("visitas.detalle", visita_id=visita.id))

    return render_template(
        "visitas/cerrar.html",
        visita=visita,
        pendientes=pendientes,
        antecedentes=_antecedentes(visita),
        resumen=_resumen_por_categoria(visita),
    )


@visitas_bp.route("/<int:visita_id>/nota-cliente", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def editar_nota_cliente(visita_id):
    """Nota general de la visita, visible en el portal del cliente junto
    a la fecha en que se escribió. La carga solo Administrador/Jefe."""
    visita = Visita.query.get_or_404(visita_id)
    verificar_acceso_cliente(visita.instalacion.cliente)

    if request.method == "POST":
        visita.nota_cliente = request.form.get("nota_cliente")
        visita.nota_cliente_fecha = date.today()
        db.session.commit()
        flash("Nota para el cliente guardada.", "success")
        return redirect(url_for("visitas.detalle", visita_id=visita.id))

    return render_template("visitas/nota_cliente.html", visita=visita)


@visitas_bp.route("/<int:visita_id>/pdf-devolucion")
@rol_requerido("Administrador", "Jefe", "Técnico", "Cliente")
def pdf_devolucion(visita_id):
    visita = Visita.query.get_or_404(visita_id)
    verificar_acceso_cliente(visita.instalacion.cliente)

    if current_user.rol == "Cliente":
        # Mismo doble candado que el resto del portal: cerrada Y con OT
        # finalizada, no alcanza con una sola.
        if not (visita.cerrada and visita.orden_trabajo and visita.orden_trabajo.estado == "Finalizada"):
            abort(404)
    elif not visita.cerrada:
        flash("Esta visita todavía no está cerrada.", "danger")
        return redirect(url_for("visitas.detalle", visita_id=visita.id))

    ids_items = [it.id for it in visita.items]
    deficiencias = (
        Observacion.query.filter(
            Observacion.item_visita_id.in_(ids_items), Observacion.estado_revision == "Aprobada"
        ).all()
        if ids_items
        else []
    )

    pdf_bytes = generar_pdf_devolucion(visita, _resumen_por_categoria(visita), deficiencias)
    nombre_archivo = f"Devolucion_{visita.instalacion.nombre.replace(' ', '_')}_{visita.fecha.isoformat()}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"inline; filename={nombre_archivo}"},
    )
