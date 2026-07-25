from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for

from app import db
from app.auth_utils import rol_requerido, verificar_acceso_cliente, verificar_escritura_cliente, verificar_visita_editable
from app.models import Equipo, Formulario, ItemVisita, TipoFormulario
from app.pdf_reporte import generar_pdf_reporte_equipos

formularios_bp = Blueprint("formularios", __name__, url_prefix="/formularios")


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

    if request.method == "POST":
        datos = {}
        for campo in tipo.campos():
            if campo["tipo"] == "multi_seleccion":
                datos[campo["campo"]] = request.form.getlist(campo["campo"])
            else:
                datos[campo["campo"]] = request.form.get(campo["campo"])
        formulario = Formulario(
            item_visita_id=item.id,
            tipo_formulario_id=tipo.id,
            equipo_id=equipo.id if equipo else None,
        )
        formulario.set_datos(datos)
        db.session.add(formulario)
        db.session.commit()
        destino = f"'{tipo.nombre}'" + (f" para {equipo.nombre}" if equipo else "")
        flash(f"Formulario {destino} agregado a '{item.servicio.nombre}'.", "success")
        if tipo.por_equipo:
            return redirect(url_for("formularios.elegir_equipo", item_id=item.id, tipo_formulario_id=tipo.id))
        return redirect(url_for("visitas.detalle", visita_id=item.visita_id))

    return render_template("visitas/formulario_form.html", item=item, tipo=tipo, equipo=equipo)


@formularios_bp.route("/<int:formulario_id>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def detalle(formulario_id):
    formulario = Formulario.query.get_or_404(formulario_id)
    verificar_acceso_cliente(formulario.item_visita.visita.instalacion.cliente)
    return render_template("visitas/formulario_detail.html", formulario=formulario)
