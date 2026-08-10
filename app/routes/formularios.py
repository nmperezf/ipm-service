from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import rol_requerido, verificar_acceso_cliente, verificar_escritura_cliente, verificar_visita_editable
from app.models import Equipo, Formulario, ItemVisita, Observacion, TipoFormulario, categoria_de_tipo_equipo
from app.notificaciones import notificar_gestion
from app.pdf_reporte import generar_pdf_reporte_equipos

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

        if guardados:
            notificar_gestion(
                empresa_id=instalacion.cliente.empresa_id,
                tipo="formulario_cargado",
                titulo=f"Formulario cargado — {tipo.nombre} ({instalacion.nombre})",
                cliente_id=instalacion.cliente_id,
                enlace=url_for("visitas.detalle", visita_id=item.visita_id),
                remitente=current_user,
            )
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
    Administrador/Jefe la apruebe). N/A y Aprobado no generan nada."""
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

    tipos = (
        TipoFormulario.query.filter_by(cliente_id=instalacion.cliente_id, por_equipo=True)
        .order_by(TipoFormulario.orden, TipoFormulario.nombre)
        .all()
    )
    secciones = []
    for tipo in tipos:
        if categoria_de_tipo_equipo(tipo.tipo_equipo_aplicable) != categoria:
            continue
        equipos = [e for e in instalacion.equipos if e.activo and e.tipo == tipo.tipo_equipo_aplicable]
        if not equipos:
            continue
        formularios_por_equipo = {
            f.equipo_id: f
            for f in Formulario.query.filter_by(item_visita_id=item.id, tipo_formulario_id=tipo.id).all()
        }
        secciones.append({"tipo": tipo, "campos": tipo.campos(), "equipos": equipos, "formularios": formularios_por_equipo})

    if not secciones:
        abort(404)

    if request.method == "POST":
        guardados = 0
        for seccion in secciones:
            tipo = seccion["tipo"]
            for equipo in seccion["equipos"]:
                datos = {}
                algun_valor = False
                for campo in seccion["campos"]:
                    nombre_campo = campo["campo"]
                    con_estado = campo["tipo"] == "estado" or campo.get("con_estado")

                    valor_dato = None
                    tiene_valor = False
                    if campo["tipo"] != "estado":
                        prefijo = f"campo__{tipo.id}__{equipo.id}__{nombre_campo}"
                        if campo["tipo"] == "multi_seleccion":
                            valor_dato = request.form.getlist(prefijo)
                        else:
                            valor_dato = request.form.get(prefijo, "")
                        tiene_valor = bool(valor_dato)

                    if con_estado:
                        estado_valor = request.form.get(f"estado__{tipo.id}__{equipo.id}__{nombre_campo}", "")
                        nota = request.form.get(f"nota__{tipo.id}__{equipo.id}__{nombre_campo}", "").strip()
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
                    continue  # equipo sin tocar, no crea un formulario vacío

                formulario = seccion["formularios"].get(equipo.id)
                if not formulario:
                    formulario = Formulario(item_visita_id=item.id, tipo_formulario_id=tipo.id, equipo_id=equipo.id)
                    db.session.add(formulario)
                formulario.set_datos(datos)
                for obs in equipo.deficiencias:
                    if not obs.resuelto:
                        obs.confirmar_vigencia(item.visita_id, current_user.id)
                guardados += 1

        if guardados:
            notificar_gestion(
                empresa_id=instalacion.cliente.empresa_id,
                tipo="formulario_cargado",
                titulo=f"Checklist de {categoria} cargado — {instalacion.nombre}",
                cliente_id=instalacion.cliente_id,
                enlace=url_for("visitas.detalle", visita_id=item.visita_id),
                remitente=current_user,
            )
        db.session.commit()
        flash(f"Checklist de {categoria} guardado ({guardados} equipo(s)).", "success")
        return redirect(url_for("visitas.detalle", visita_id=item.visita_id))

    return render_template(
        "visitas/checklist_categoria_form.html",
        item=item, categoria=categoria, secciones=secciones, instalacion=instalacion,
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
    equipo = Equipo.query.get(equipo_id) if equipo_id else None

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
        if es_nuevo:
            notificar_gestion(
                empresa_id=item.visita.instalacion.cliente.empresa_id,
                tipo="formulario_cargado",
                titulo=f"Formulario cargado — {tipo.nombre} ({item.visita.instalacion.nombre})",
                cliente_id=item.visita.instalacion.cliente_id,
                enlace=url_for("visitas.detalle", visita_id=item.visita_id),
                remitente=current_user,
            )
        db.session.commit()
        destino = f"'{tipo.nombre}'" + (f" para {equipo.nombre}" if equipo else "")
        verbo = "agregado a" if es_nuevo else "actualizado en"
        flash(f"Formulario {destino} {verbo} '{item.nombre_mostrado}'.", "success")
        if tipo.por_equipo:
            return redirect(url_for("formularios.elegir_equipo", item_id=item.id, tipo_formulario_id=tipo.id))
        return redirect(url_for("visitas.detalle", visita_id=item.visita_id))

    return render_template("visitas/formulario_form.html", item=item, tipo=tipo, equipo=equipo, formulario=formulario)


@formularios_bp.route("/<int:formulario_id>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def detalle(formulario_id):
    formulario = Formulario.query.get_or_404(formulario_id)
    verificar_acceso_cliente(formulario.item_visita.visita.instalacion.cliente)
    return render_template("visitas/formulario_detail.html", formulario=formulario)


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
