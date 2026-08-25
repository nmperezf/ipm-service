from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import rol_requerido, verificar_acceso_cliente, verificar_escritura_cliente, verificar_visita_editable
from app.models import (
    TIPOS_BOMBA_PRINCIPAL,
    Equipo,
    Formulario,
    Foto,
    ItemVisita,
    Observacion,
    TipoFormulario,
    categoria_de_tipo_equipo,
)
from app.pdf_informe_sala_bombas import generar_pdf_informe_categoria
from app.pdf_reporte import generar_pdf_reporte_equipos
from app.utils import es_ajax, obtener_o_crear_informe

formularios_bp = Blueprint("formularios", __name__, url_prefix="/formularios")


@formularios_bp.route("/")
@rol_requerido("Administrador", "Jefe", "Técnico")
def hub():
    """Landing del menú 'Formularios': los dos catálogos de la empresa
    (Servicios tipo, Tipos de equipo). Los formularios propios de cada
    cliente no aparecen acá — esos se ven y editan desde el contrato de
    cada cliente."""
    return render_template("formularios/hub.html")


def _verificar_tipo_del_cliente(item, tipo):
    """El tipo de formulario tiene que pertenecer al mismo cliente que la
    visita — evita mezclar un checklist de otro cliente por id."""
    if tipo.cliente_id != item.visita.instalacion.cliente_id:
        abort(403)


@formularios_bp.route("/elegir-equipo/<int:item_id>/<int:tipo_formulario_id>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def elegir_equipo(item_id, tipo_formulario_id):
    """Para formularios 'por equipo' (ej. checklist de ECA): antes
    de completar el formulario, elegís a cuál equipo corresponde. Podés
    cargar uno por cada equipo aplicable de la instalación."""
    item = ItemVisita.query.get_or_404(item_id)
    verificar_escritura_cliente(item.visita.instalacion.cliente)
    verificar_visita_editable(item.visita)
    tipo = TipoFormulario.query.get_or_404(tipo_formulario_id)
    _verificar_tipo_del_cliente(item, tipo)
    instalacion = item.visita.instalacion

    equipos = [
        e for e in instalacion.equipos
        if e.activo and (not tipo.tipo_equipo_aplicable or e.tipo == tipo.tipo_equipo_aplicable)
    ]

    return render_template(
        "visitas/elegir_equipo.html", item=item, tipo=tipo, equipos=equipos, instalacion=instalacion
    )


@formularios_bp.route("/carga-masiva/<int:item_id>/<int:tipo_formulario_id>", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def carga_masiva(item_id, tipo_formulario_id):
    """Grilla para cargar el mismo checklist en muchos equipos de una vez
    (pensada para instalaciones con decenas o cientos de BIE/ECA): una fila
    por equipo, todas las columnas del formulario editables ahí mismo, un
    solo guardado. Si el equipo ya tenía datos cargados para esta visita,
    los actualiza en vez de duplicar."""
    item = ItemVisita.query.get_or_404(item_id)
    verificar_escritura_cliente(item.visita.instalacion.cliente)
    verificar_visita_editable(item.visita)
    tipo = TipoFormulario.query.get_or_404(tipo_formulario_id)
    _verificar_tipo_del_cliente(item, tipo)
    instalacion = item.visita.instalacion

    equipos = [
        e for e in instalacion.equipos
        if e.activo and (not tipo.tipo_equipo_aplicable or e.tipo == tipo.tipo_equipo_aplicable)
    ]

    if request.method == "POST":
        campos = tipo.campos()
        guardados = 0
        for equipo in equipos:
            datos = {}
            algun_valor = False
            for campo in campos:
                nombre_input = f"campo__{equipo.id}__{campo['campo']}"
                if campo["tipo"] == "multi_seleccion":
                    valor = request.form.getlist(nombre_input)
                else:
                    valor = request.form.get(nombre_input, "")
                if valor:
                    algun_valor = True
                datos[campo["campo"]] = valor

            if not algun_valor:
                continue  # fila sin tocar, no crea un formulario vacío

            formulario = Formulario.query.filter_by(
                item_visita_id=item.id, tipo_formulario_id=tipo.id, equipo_id=equipo.id
            ).first()
            if not formulario:
                formulario = Formulario(item_visita_id=item.id, tipo_formulario_id=tipo.id, equipo_id=equipo.id)
                db.session.add(formulario)
            formulario.set_datos(datos)
            for obs in equipo.deficiencias:
                if not obs.resuelto:
                    obs.confirmar_vigencia(item.visita_id, current_user.id)
            guardados += 1

        db.session.commit()
        flash(f"Se guardaron {guardados} checklist(s) de '{tipo.nombre}'.", "success")
        return redirect(url_for("visitas.detalle", visita_id=item.visita_id))

    # Precarga los valores ya guardados, si los había
    formularios_por_equipo = {
        f.equipo_id: f
        for f in Formulario.query.filter_by(item_visita_id=item.id, tipo_formulario_id=tipo.id).all()
    }

    return render_template(
        "visitas/carga_masiva.html",
        item=item,
        tipo=tipo,
        equipos=equipos,
        formularios_por_equipo=formularios_por_equipo,
    )


def _crear_observacion_de_punto(item, equipo, campo_label, estado, nota):
    """Un punto de checklist marcado Observado o Deficiencia con una nota
    genera una Observación automáticamente, ligada a ese equipo puntual --
    mismo circuito de revisión que una carga manual (Pendiente hasta que
    Administrador/Jefe la apruebe). N/A y Conforme no generan nada."""
    if not nota or estado not in ("observado", "deficiencia"):
        return
    clasificacion = "Deficiencia no crítica" if estado == "deficiencia" else "Comentario"
    observacion = Observacion(
        instalacion_id=item.visita.instalacion_id,
        item_visita_id=item.id,
        equipo_id=equipo.id if equipo else None,
        clasificacion=clasificacion,
        descripcion=f"{campo_label}: {nota}",
        estado_revision="Pendiente",
        creado_por_id=current_user.id,
    )
    db.session.add(observacion)


def _secciones_categoria(item, categoria):
    """Arma la lista de secciones de una categoría entera (ej. Sala de
    bombas) para un ítem de visita: junta los TipoFormulario de esa
    categoría (por equipo o de sala completa) con lo ya cargado. Compartida
    entre la pantalla de carga combinada (checklist_categoria) y el informe
    oficial (formularios.informe_categoria_pdf) para que las dos lean
    exactamente los mismos datos por el mismo camino."""
    instalacion = item.visita.instalacion
    tipos = (
        TipoFormulario.query.filter_by(cliente_id=instalacion.cliente_id)
        .order_by(TipoFormulario.orden, TipoFormulario.nombre)
        .all()
    )
    # Un servicio "paquete" (categoria seteada) sigue mostrando todos los
    # tipos de esa categoría física, como siempre. Un servicio puntual (sin
    # categoria) muestra solo el tipo que se importó con su mismo nombre --
    # no el resto de checklists que compartan tipo de equipo (ver el mismo
    # criterio en visitas.detalle).
    es_paquete = not (item.servicio and not item.servicio.categoria)
    if not es_paquete:
        tipos = [t for t in tipos if t.nombre == item.servicio.nombre]

    secciones = []
    for tipo in tipos:
        if categoria_de_tipo_equipo(tipo.tipo_equipo_aplicable) != categoria:
            continue
        # incluir_en_carga_combinada solo aplica cuando de verdad se está
        # armando la pantalla combinada de varios tipos (paquete) -- un
        # servicio puntual (ej. un mantenimiento anual contratado por su
        # cuenta, no como parte de "Inspecciones y pruebas") ya viene
        # acotado a un solo tipo arriba y tiene que poder cargarse igual,
        # aunque ese mismo tipo esté marcado para no entrar a un paquete.
        if es_paquete and not tipo.incluir_en_carga_combinada:
            continue
        if tipo.por_equipo:
            equipos = [e for e in instalacion.equipos if e.activo and e.tipo == tipo.tipo_equipo_aplicable]
            if not equipos:
                continue
            formularios_por_equipo = {
                f.equipo_id: f
                for f in Formulario.query.filter_by(item_visita_id=item.id, tipo_formulario_id=tipo.id).all()
            }
            secciones.append({"tipo": tipo, "campos": tipo.campos(), "equipos": equipos, "formularios": formularios_por_equipo})
        else:
            # Checklist de sala completa (ej. protocolo de retiro): no se
            # liga a un equipo puntual, un solo Formulario por visita
            # (equipo_id=None) -- el sentinel "0" en el nombre del campo
            # del form (ver POST más abajo) deja reusar el mismo parseo
            # que el resto de las secciones sin inventar otro esquema.
            formulario_general = Formulario.query.filter_by(
                item_visita_id=item.id, tipo_formulario_id=tipo.id, equipo_id=None
            ).first()
            secciones.append({"tipo": tipo, "campos": tipo.campos(), "equipos": [], "formularios": {}, "formulario_general": formulario_general})
    return secciones


@formularios_bp.route("/checklist-categoria/<int:item_id>/<categoria>", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def checklist_categoria(item_id, categoria):
    """Pantalla combinada para una categoría entera (ej. Sala de bombas):
    junta los tipos de formulario 'por equipo' de esa categoría con los
    equipos reales de la instalación que les corresponden, para
    completarlos de una sola carga -- pero cada equipo se guarda como su
    propio Formulario, igual que si se hubiera cargado por separado, así
    que su ficha individual, el histórico por categoría y el gráfico de
    valores numéricos no cambian en nada."""
    item = ItemVisita.query.get_or_404(item_id)
    verificar_escritura_cliente(item.visita.instalacion.cliente)
    verificar_visita_editable(item.visita)
    instalacion = item.visita.instalacion

    secciones = _secciones_categoria(item, categoria)
    if not secciones:
        abort(404)

    # Fotos ya subidas ligadas a un punto puntual (campo_formulario) de
    # esta visita, agrupadas por (equipo, campo) para mostrarlas de
    # entrada al redibujar la pantalla (ver foto-campo.js).
    fotos_por_campo = {}
    for foto in Foto.query.filter(
        Foto.item_visita_id == item.id, Foto.campo_formulario.isnot(None)
    ).all():
        fotos_por_campo.setdefault((foto.equipo_id, foto.campo_formulario), []).append(foto)

    if request.method == "POST":
        guardados = 0
        for seccion in secciones:
            tipo = seccion["tipo"]
            # Sección de sala completa: un solo pase con equipo=None (0 es
            # el sentinel usado en el nombre del campo, ver template) en
            # vez de loopear equipos reales.
            equipos_a_guardar = seccion["equipos"] if tipo.por_equipo else [None]
            for equipo in equipos_a_guardar:
                equipo_id_campo = equipo.id if equipo else 0
                datos = {}
                algun_valor = False
                for campo in seccion["campos"]:
                    nombre_campo = campo["campo"]
                    con_estado = campo["tipo"] == "estado" or campo.get("con_estado")

                    valor_dato = None
                    tiene_valor = False
                    if campo["tipo"] != "estado":
                        prefijo = f"campo__{tipo.id}__{equipo_id_campo}__{nombre_campo}"
                        if campo["tipo"] == "multi_seleccion":
                            valor_dato = request.form.getlist(prefijo)
                        else:
                            valor_dato = request.form.get(prefijo, "")
                        tiene_valor = bool(valor_dato)

                    if con_estado:
                        estado_valor = request.form.get(f"estado__{tipo.id}__{equipo_id_campo}__{nombre_campo}", "")
                        nota = request.form.get(f"nota__{tipo.id}__{equipo_id_campo}__{nombre_campo}", "").strip()
                        if estado_valor or tiene_valor:
                            algun_valor = True
                            datos[nombre_campo] = {"valor": valor_dato or None, "estado": estado_valor, "nota": nota}
                            _crear_observacion_de_punto(item, equipo, campo["label"], estado_valor, nota)
                        else:
                            datos[nombre_campo] = None
                    else:
                        if tiene_valor:
                            algun_valor = True
                        datos[nombre_campo] = valor_dato

                if not algun_valor:
                    continue  # sin tocar, no crea un formulario vacío

                if equipo:
                    formulario = seccion["formularios"].get(equipo.id)
                else:
                    formulario = seccion.get("formulario_general")
                if not formulario:
                    formulario = Formulario(item_visita_id=item.id, tipo_formulario_id=tipo.id, equipo_id=equipo.id if equipo else None)
                    db.session.add(formulario)
                formulario.set_datos(datos)
                if equipo:
                    for obs in equipo.deficiencias:
                        if not obs.resuelto:
                            obs.confirmar_vigencia(item.visita_id, current_user.id)
                guardados += 1

        db.session.commit()
        flash(f"Checklist de {categoria} guardado ({guardados} equipo(s)).", "success")
        return redirect(url_for("visitas.detalle", visita_id=item.visita_id))

    return render_template(
        "visitas/checklist_categoria_form.html",
        item=item, categoria=categoria, secciones=secciones, instalacion=instalacion,
        fotos_por_campo=fotos_por_campo,
    )


@formularios_bp.route("/informe-categoria/<int:item_id>/<categoria>/dictamen", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def informe_dictamen(item_id, categoria):
    """El veredicto final del informe lo redacta a mano Administrador/Jefe
    -- mismo criterio que EnsayoCaudal.resultado_manual: la app nunca
    calcula un 'aprobado/no aprobado' automático para un documento
    oficial, solo muestra el estado de cada punto."""
    item = ItemVisita.query.get_or_404(item_id)
    verificar_escritura_cliente(item.visita.instalacion.cliente)
    if not item.visita.cerrada:
        flash("El dictamen se redacta una vez que la visita está cerrada.", "danger")
        return redirect(url_for("visitas.detalle", visita_id=item.visita_id))

    informe = obtener_o_crear_informe(item, categoria, current_user.id)
    db.session.commit()

    if request.method == "POST":
        informe.dictamen = request.form.get("dictamen", "").strip() or None
        db.session.commit()
        flash("Dictamen guardado.", "success")
        return redirect(url_for("formularios.informe_categoria_pdf", item_id=item.id, categoria=categoria))

    return render_template("visitas/informe_dictamen_form.html", item=item, categoria=categoria, informe=informe)


@formularios_bp.route("/informe-categoria/<int:item_id>/<categoria>/pdf")
@rol_requerido("Administrador", "Jefe", "Técnico", "Cliente")
def informe_categoria_pdf(item_id, categoria):
    """Informe oficial combinado de una categoría (ej. Sala de bombas):
    junta los checklists ya cargados (ver _secciones_categoria), el
    ensayo de curva de caudal más reciente de cada bomba principal/
    respaldo y las observaciones, en un solo PDF con número de documento
    y dictamen. No es una carga nueva -- se arma a partir de lo que ya
    está guardado."""
    item = ItemVisita.query.get_or_404(item_id)
    verificar_acceso_cliente(item.visita.instalacion.cliente)
    if not item.visita.cerrada:
        if current_user.rol == "Cliente":
            abort(404)
        flash("Este informe se genera una vez que la visita está cerrada.", "danger")
        return redirect(url_for("visitas.detalle", visita_id=item.visita_id))

    secciones = _secciones_categoria(item, categoria)
    if not secciones:
        abort(404)

    instalacion = item.visita.instalacion
    equipos_categoria = {e for seccion in secciones for e in seccion["equipos"]}
    equipos_categoria_ids = {e.id for e in equipos_categoria}

    ensayos = {}
    for equipo in equipos_categoria:
        if equipo.tipo not in TIPOS_BOMBA_PRINCIPAL:
            continue
        mas_reciente = sorted(equipo.ensayos_caudal, key=lambda e: e.fecha_ensayo, reverse=True)
        if mas_reciente:
            ensayos[equipo] = mas_reciente[0]

    ids_items = [it.id for it in item.visita.items]
    # Incluye equipo_id IS NULL para no perder las deficiencias que salen
    # de un checklist de sala completa (ej. protocolo de retiro), que no
    # se ligan a un equipo puntual -- ver _secciones_categoria.
    observaciones = (
        Observacion.query.filter(
            Observacion.item_visita_id.in_(ids_items),
            db.or_(Observacion.equipo_id.in_(equipos_categoria_ids), Observacion.equipo_id.is_(None)),
            Observacion.estado_revision == "Aprobada",
            Observacion.visibilidad != "Interna",
        ).all()
        if ids_items else []
    )
    ids_obs_visita = {o.id for o in observaciones}
    observaciones_vigentes = [
        o for o in instalacion.deficiencias
        if not o.resuelto and o.id not in ids_obs_visita
        and o.equipo_id in equipos_categoria_ids and o.visibilidad != "Interna"
    ]
    observaciones_todas = sorted(
        observaciones + observaciones_vigentes,
        key=lambda o: (o.clasificacion != "Deficiencia crítica", o.fecha_carga),
    )

    informe = obtener_o_crear_informe(item, categoria, current_user.id)
    db.session.commit()

    pdf_bytes = generar_pdf_informe_categoria(item, categoria, secciones, ensayos, observaciones_todas, informe)
    nombre_archivo = f"Informe_{categoria.replace(' ', '_')}_{instalacion.nombre.replace(' ', '_')}_{item.visita.fecha.isoformat()}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"inline; filename={nombre_archivo}", "Cache-Control": "no-store"},
    )


@formularios_bp.route("/reporte/<int:item_id>/<int:tipo_formulario_id>/pdf")
@rol_requerido("Administrador", "Jefe", "Técnico")
def reporte_pdf(item_id, tipo_formulario_id):
    """Un solo documento con el detalle de cada equipo, para mandarle al
    cliente el resultado de esta ronda de inspección (ej. todas las BIE)."""
    item = ItemVisita.query.get_or_404(item_id)
    verificar_acceso_cliente(item.visita.instalacion.cliente)
    tipo = TipoFormulario.query.get_or_404(tipo_formulario_id)
    _verificar_tipo_del_cliente(item, tipo)

    formularios = (
        Formulario.query.filter_by(item_visita_id=item.id, tipo_formulario_id=tipo.id)
        .join(Equipo)
        .order_by(Equipo.nombre)
        .all()
    )

    pdf_bytes = generar_pdf_reporte_equipos(item, tipo, formularios)
    nombre_archivo = f"Reporte_{tipo.nombre.replace(' ', '_')}_{item.visita.instalacion.nombre.replace(' ', '_')}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"inline; filename={nombre_archivo}"},
    )


@formularios_bp.route("/nuevo/<int:item_id>/<int:tipo_formulario_id>", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def nuevo(item_id, tipo_formulario_id):
    item = ItemVisita.query.get_or_404(item_id)
    verificar_escritura_cliente(item.visita.instalacion.cliente)
    verificar_visita_editable(item.visita)
    tipo = TipoFormulario.query.get_or_404(tipo_formulario_id)
    _verificar_tipo_del_cliente(item, tipo)

    equipo_id = request.values.get("equipo_id", type=int)
    equipo = db.session.get(Equipo, equipo_id) if equipo_id else None

    if tipo.por_equipo and not equipo:
        return redirect(url_for("formularios.elegir_equipo", item_id=item.id, tipo_formulario_id=tipo.id))

    # Si ya había un formulario cargado para este item/tipo/equipo, lo
    # actualiza en vez de duplicarlo (antes creaba uno nuevo cada vez que
    # se volvía a guardar el mismo checklist).
    formulario = Formulario.query.filter_by(
        item_visita_id=item.id, tipo_formulario_id=tipo.id, equipo_id=equipo.id if equipo else None
    ).first()

    if request.method == "POST":
        datos = {}
        for campo in tipo.campos():
            nombre_campo = campo["campo"]
            con_estado = campo["tipo"] == "estado" or campo.get("con_estado")

            valor_dato = None
            if campo["tipo"] == "multi_seleccion":
                valor_dato = request.form.getlist(nombre_campo)
            elif campo["tipo"] != "estado":
                valor_dato = request.form.get(nombre_campo)

            if con_estado:
                estado_valor = request.form.get(f"estado__{nombre_campo}", "")
                nota = request.form.get(f"nota__{nombre_campo}", "").strip()
                datos[nombre_campo] = {"valor": valor_dato or None, "estado": estado_valor, "nota": nota}
                _crear_observacion_de_punto(item, equipo, campo["label"], estado_valor, nota)
            else:
                datos[nombre_campo] = valor_dato
        es_nuevo = formulario is None
        if es_nuevo:
            formulario = Formulario(
                item_visita_id=item.id,
                tipo_formulario_id=tipo.id,
                equipo_id=equipo.id if equipo else None,
            )
            db.session.add(formulario)
        formulario.set_datos(datos)
        if equipo:
            for obs in equipo.deficiencias:
                if not obs.resuelto:
                    obs.confirmar_vigencia(item.visita_id, current_user.id)
        db.session.commit()
        destino = f"'{tipo.nombre}'" + (f" para {equipo.nombre}" if equipo else "")
        verbo = "agregado a" if es_nuevo else "actualizado en"
        flash(f"Formulario {destino} {verbo} '{item.nombre_mostrado}'.", "success")
        if tipo.por_equipo:
            return redirect(url_for("formularios.elegir_equipo", item_id=item.id, tipo_formulario_id=tipo.id))
        return redirect(url_for("visitas.detalle", visita_id=item.visita_id))

    fotos_por_campo = {}
    for foto in Foto.query.filter(
        Foto.item_visita_id == item.id,
        Foto.equipo_id == (equipo.id if equipo else None),
        Foto.campo_formulario.isnot(None),
    ).all():
        fotos_por_campo.setdefault(foto.campo_formulario, []).append(foto)

    return render_template(
        "visitas/formulario_form.html", item=item, tipo=tipo, equipo=equipo, formulario=formulario,
        fotos_por_campo=fotos_por_campo,
    )


@formularios_bp.route("/<int:formulario_id>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def detalle(formulario_id):
    formulario = Formulario.query.get_or_404(formulario_id)
    visita = formulario.item_visita.visita
    verificar_acceso_cliente(visita.instalacion.cliente)
    # Mismo criterio que visitas/detail.html: una vez que la visita salió de
    # la fase "Abierta" (enviada a revisión), un Técnico ya no puede tocar
    # sus formularios -- ocultar el botón evita el 403 confuso de intentar
    # editar/eliminar algo que el backend (verificar_visita_editable) igual
    # va a rechazar.
    puede_editar = not visita.cerrada and not (current_user.rol == "Técnico" and visita.fase != "Abierta")

    if es_ajax():
        fotos_por_campo = {}
        for foto in Foto.query.filter(
            Foto.item_visita_id == formulario.item_visita_id,
            Foto.equipo_id == formulario.equipo_id,
            Foto.campo_formulario.isnot(None),
        ).all():
            fotos_por_campo.setdefault(foto.campo_formulario, []).append(foto)
        return render_template(
            "visitas/_formulario_modal.html", formulario=formulario, fotos_por_campo=fotos_por_campo, puede_editar=puede_editar
        )

    # Página completa: se ven todos los formularios de este mismo ítem uno
    # detrás de otro (el mismo listado que aparece como botones en
    # visitas/detail.html), no solo el que se clickeó -- si no, esta página
    # no agregaba nada sobre el modal.
    formularios_item = sorted(formulario.item_visita.formularios, key=lambda f: f.fecha_creacion)
    fotos_todas = Foto.query.filter(
        Foto.item_visita_id == formulario.item_visita_id,
        Foto.campo_formulario.isnot(None),
    ).all()
    fotos_por_formulario = {}
    for f in formularios_item:
        fotos_campo = {}
        for foto in fotos_todas:
            if foto.equipo_id == f.equipo_id:
                fotos_campo.setdefault(foto.campo_formulario, []).append(foto)
        fotos_por_formulario[f.id] = fotos_campo

    return render_template(
        "visitas/formulario_detail.html",
        formulario=formulario, formularios=formularios_item,
        fotos_por_formulario=fotos_por_formulario, puede_editar=puede_editar,
    )


@formularios_bp.route("/<int:formulario_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar(formulario_id):
    formulario = Formulario.query.get_or_404(formulario_id)
    verificar_escritura_cliente(formulario.item_visita.visita.instalacion.cliente)
    verificar_visita_editable(formulario.item_visita.visita)
    visita_id = formulario.item_visita.visita_id
    tipo_nombre = formulario.tipo_formulario.nombre
    db.session.delete(formulario)
    db.session.commit()
    flash(f"Formulario '{tipo_nombre}' eliminado.", "info")
    return redirect(url_for("visitas.detalle", visita_id=visita_id))
