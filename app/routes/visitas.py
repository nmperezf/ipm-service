from datetime import date, datetime

from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, url_for
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
    TIPOS_BOMBA_PRINCIPAL,
    Equipo,
    Instalacion,
    ItemVisita,
    Observacion,
    OrdenTrabajo,
    TipoFormulario,
    Usuario,
    Visita,
    categoria_de_tipo_equipo,
    categorias_equipo_agrupadas,
)
from app.notificaciones import notificar_gestion, notificar_tecnico_asignado
from app.pdf_checklist_tecnico import generar_pdf_checklist_tecnico
from app.pdf_devolucion import generar_pdf_devolucion
from app.utils import equipos_por_categoria, es_ajax, filas_checklist, resumen_visita_por_categoria

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
        notificar_tecnico_asignado(ot, current_user)

        db.session.commit()
        if es_ajax():
            return jsonify(ok=True, mensaje="Visita registrada.")
        flash("Visita registrada.", "success")
        return redirect(url_for("visitas.detalle", visita_id=visita.id))

    template = "visitas/_form_fragment.html" if es_ajax() else "visitas/form.html"
    return render_template(
        template, instalacion=instalacion, estados=ESTADOS_VISITA, tecnicos=tecnicos
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
    # Cada servicio de la visita ofrece solo los tipos de formulario que
    # aplican a él (ver TipoFormulario.aplica_a_servicio) — uno sin
    # servicios configurados aparece para todos, sin romper lo de siempre.
    # Un ítem suelto ligado a un equipo (ver visitas.agregar_item) filtra
    # igual, pero por el tipo de ESE equipo en vez del servicio; uno sin
    # equipo ni servicio no tiene de dónde filtrar, así que ofrece todos.
    # Un ítem de curva de caudal no usa el selector de formularios — ofrece
    # directamente las bombas de la instalación (filtradas por
    # tipo_equipo_aplicable si el servicio lo definió) para cargar el
    # ensayo de cada una (ver curvas.ensayo_nuevo).
    formularios_por_item = {}
    equipos_bomba_por_item = {}
    for item in visita.items:
        if item.servicio and item.servicio.es_curva_caudal:
            tipo_filtro = item.servicio.tipo_equipo_aplicable
            tipos_bomba = (tipo_filtro,) if tipo_filtro else TIPOS_BOMBA_PRINCIPAL
            equipos_bomba_por_item[item.id] = [
                e for e in visita.instalacion.equipos if e.activo and e.tipo in tipos_bomba
            ]
            continue
        if item.servicio and item.servicio.categoria:
            # Servicio "paquete" (ej. "Inspecciones y pruebas en sala de
            # bombas"): un solo ítem para toda la categoría, no un tipo de
            # equipo puntual -- se ofrecen todos los tipos de esa categoría
            # juntos (ver formularios.checklist_categoria), no filtrados
            # por aplica_a_tipo_equipo (que compara un único tipo).
            tipos_item = [t for t in tipos if categoria_de_tipo_equipo(t.tipo_equipo_aplicable) == item.servicio.categoria]
        else:
            tipo_equipo_ref = item.servicio.tipo_equipo_aplicable if item.servicio else (item.equipo.tipo if item.equipo else None)
            tipos_item = [t for t in tipos if t.aplica_a_tipo_equipo(tipo_equipo_ref)]
        grupos, generales = _agrupar_tipos_formulario(tipos_item)
        formularios_por_item[item.id] = {"grupos": grupos, "generales": generales}

    # Para que el técnico vea de entrada qué deficiencias ya estaban
    # cargadas en esta instalación, sin tener que ir a buscarlas a la
    # ficha de la instalación. Críticas primero, después por antigüedad.
    deficiencias_abiertas = sorted(
        (o for o in visita.instalacion.deficiencias if not o.resuelto),
        key=lambda o: (o.clasificacion != "Deficiencia crítica", o.fecha_carga),
    )

    formularios_visita = sorted(
        (f for item in visita.items for f in item.formularios), key=lambda f: f.fecha_creacion
    )
    grupos_checklist = filas_checklist(formularios_visita, incluir_equipo=True)

    return render_template(
        "visitas/detail.html",
        visita=visita,
        formularios_por_item=formularios_por_item,
        equipos_bomba_por_item=equipos_bomba_por_item,
        equipos_agrupados=equipos_por_categoria(visita.instalacion),
        deficiencias_abiertas=deficiencias_abiertas,
        grupos_checklist=grupos_checklist,
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
    flash(f"'{item.nombre_mostrado}' marcado como cumplido.", "success")
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
    flash(f"'{item.nombre_mostrado}' marcado como pendiente.", "info")
    return redirect(url_for("visitas.detalle", visita_id=visita.id))


@visitas_bp.route("/<int:visita_id>/items/agregar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def agregar_item(visita_id):
    """Agrega un ítem suelto (sin servicio de contrato) a la visita, para
    cargar algo puntual: una revisión no contemplada en el contrato, o
    directamente el único ítem de una visita de cliente esporádico sin
    contrato armado (ver visitas.nueva). Elegir un equipo de la propia
    instalación (en vez de texto libre) es lo que después deja ofrecer
    el formulario correcto ya filtrado y listo para cargar, sin pasar
    por el paso de "elegir equipo" — ver visitas.detalle."""
    visita = Visita.query.get_or_404(visita_id)
    verificar_escritura_cliente(visita.instalacion.cliente)
    verificar_visita_editable(visita)

    equipo_id = request.form.get("equipo_id", type=int)
    equipo = None
    if equipo_id:
        equipo = Equipo.query.get_or_404(equipo_id)
        if equipo.instalacion_id != visita.instalacion_id:
            abort(400)

    nombre = (request.form.get("nombre_libre") or "").strip()
    if not equipo and not nombre:
        flash("Elegí un equipo o escribí una descripción antes de agregarlo.", "danger")
        return redirect(url_for("visitas.detalle", visita_id=visita.id))

    item = ItemVisita(
        visita_id=visita.id, equipo_id=equipo.id if equipo else None,
        nombre_libre=nombre or None, estado="Pendiente",
    )
    db.session.add(item)
    db.session.commit()
    flash(f"'{item.nombre_mostrado}' agregado a la visita.", "success")
    return redirect(url_for("visitas.detalle", visita_id=visita.id))


@visitas_bp.route("/items/<int:item_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar_item(item_id):
    """Solo para ítems sueltos que todavía no tienen nada cargado — evita
    perder formularios o fotos ya subidos por error de un click."""
    item = ItemVisita.query.get_or_404(item_id)
    visita = item.visita
    verificar_escritura_cliente(visita.instalacion.cliente)
    verificar_visita_editable(visita)
    if item.servicio_contrato_id or item.formularios or item.fotos or item.ensayos_caudal:
        flash("Ese ítem ya tiene datos cargados o viene del contrato — no se puede eliminar.", "danger")
        return redirect(url_for("visitas.detalle", visita_id=visita.id))
    nombre = item.nombre_mostrado
    db.session.delete(item)
    db.session.commit()
    flash(f"'{nombre}' eliminado de la visita.", "info")
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
        firma_tecnico = request.form.get("firma_tecnico")
        if firma_tecnico:
            visita.firma_tecnico = firma_tecnico
        # La OT no tiene un estado propio editable mientras esté ligada a
        # una visita (ver ordenes.actualizar_campo) -- se sincroniza sola
        # con la fase de la visita, para no terminar con dos estados
        # desincronizados.
        if visita.orden_trabajo and visita.orden_trabajo.estado not in ("Finalizada", "Cancelada"):
            visita.orden_trabajo.estado = "En proceso"
        notificar_gestion(
            empresa_id=current_user.empresa_id,
            tipo="visita_revision",
            titulo=f"Visita a revisión — {visita.instalacion.nombre} ({visita.fecha.strftime('%d/%m/%Y')})",
            cliente_id=visita.instalacion.cliente_id,
            enlace=url_for("visitas.detalle", visita_id=visita.id),
            remitente=current_user,
        )
        db.session.commit()
        flash("Visita enviada a revisión.", "success")
        return redirect(url_for("visitas.detalle", visita_id=visita.id))

    items_sin_cumplir = [it for it in visita.items if it.estado != "Cumplido"]

    return render_template(
        "visitas/enviar_revision.html",
        visita=visita,
        antecedentes=_antecedentes(visita),
        resumen=resumen_visita_por_categoria(visita),
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
        # La OT preventiva que generó esta visita se cierra junto con ella
        # (ver ordenes_trabajo.py: ya bloqueaba finalizar a mano si había
        # observaciones sin aprobar, así que para cuando se llega hasta acá
        # siempre está en condiciones de finalizarse). Si alguien ya la
        # había cancelado a mano, se respeta esa cancelación.
        if visita.orden_trabajo and visita.orden_trabajo.estado != "Cancelada":
            visita.orden_trabajo.estado = "Finalizada"
            visita.orden_trabajo.fecha_cierre = visita.fecha_cierre
            # Si la OT viene de un presupuesto aprobado, cerrarla acá
            # también cierra el presupuesto y resuelve la deficiencia que
            # lo originó (mismo efecto que finalizar una OT correctiva a
            # mano desde ordenes.actualizar_campo).
            presupuesto = visita.orden_trabajo.presupuesto_origen
            if presupuesto and presupuesto.estado != "Cerrado":
                presupuesto.cambiar_estado("Cerrado", current_user.id, "Cerrado automáticamente al cerrar la visita.")
                presupuesto.observacion.marcar_resuelta(current_user.id)
        db.session.commit()
        flash("Visita cerrada. Ya podés descargar el PDF de devolución.", "success")
        return redirect(url_for("visitas.detalle", visita_id=visita.id))

    return render_template(
        "visitas/cerrar.html",
        visita=visita,
        pendientes=pendientes,
        antecedentes=_antecedentes(visita),
        resumen=resumen_visita_por_categoria(visita),
    )


@visitas_bp.route("/<int:visita_id>/reabrir", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def reabrir(visita_id):
    """Una visita cerrada queda bloqueada para todos (ver
    verificar_visita_editable). Si hace falta corregir algo después de
    cerrarla, primero hay que reabrirla acá explícitamente: es una acción
    deliberada y visible, no una edición silenciosa sobre un PDF que ya se
    le pudo haber entregado al cliente."""
    visita = Visita.query.get_or_404(visita_id)
    verificar_acceso_cliente(visita.instalacion.cliente)

    if not visita.cerrada:
        flash("Esta visita no está cerrada.", "info")
        return redirect(url_for("visitas.detalle", visita_id=visita.id))

    visita.cerrada = False
    visita.fecha_cierre = None
    visita.cerrada_por_id = None
    if visita.orden_trabajo and visita.orden_trabajo.estado == "Finalizada":
        visita.orden_trabajo.estado = "En proceso"
        visita.orden_trabajo.fecha_cierre = None
    db.session.commit()
    flash(
        "Visita reabierta. Recordá que el PDF de devolución ya entregado no va a reflejar los cambios hasta volver a cerrarla.",
        "warning",
    )
    return redirect(url_for("visitas.detalle", visita_id=visita.id))


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

    ids_deficiencias_visita = {d.id for d in deficiencias}
    observaciones_vigentes = sorted(
        (
            o
            for o in visita.instalacion.deficiencias
            if not o.resuelto and o.id not in ids_deficiencias_visita
        ),
        key=lambda o: (o.clasificacion != "Deficiencia crítica", o.fecha_carga),
    )

    pdf_bytes = generar_pdf_devolucion(
        visita, resumen_visita_por_categoria(visita), deficiencias, observaciones_vigentes
    )
    nombre_archivo = f"Devolucion_{visita.instalacion.nombre.replace(' ', '_')}_{visita.fecha.isoformat()}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"inline; filename={nombre_archivo}"},
    )


@visitas_bp.route("/<int:visita_id>/checklist-tecnico-pdf")
@rol_requerido("Administrador", "Jefe", "Técnico", "Cliente")
def checklist_tecnico_pdf(visita_id):
    """Documento técnico con cada punto cargado (valor, estado, nota) --
    a diferencia del PDF de devolución, que es el resumen ejecutivo. Mismo
    candado de acceso que ese: para el Cliente, solo si la visita está
    Cerrada y su OT Finalizada."""
    visita = Visita.query.get_or_404(visita_id)
    verificar_acceso_cliente(visita.instalacion.cliente)

    if current_user.rol == "Cliente":
        if not (visita.cerrada and visita.orden_trabajo and visita.orden_trabajo.estado == "Finalizada"):
            abort(404)
    elif not visita.cerrada:
        flash("Esta visita todavía no está cerrada.", "danger")
        return redirect(url_for("visitas.detalle", visita_id=visita.id))

    pdf_bytes = generar_pdf_checklist_tecnico(visita)
    nombre_archivo = f"Checklist_{visita.instalacion.nombre.replace(' ', '_')}_{visita.fecha.isoformat()}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"inline; filename={nombre_archivo}"},
    )
