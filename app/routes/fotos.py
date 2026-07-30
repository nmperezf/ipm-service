import os
import uuid
from datetime import date, datetime

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user
from werkzeug.utils import secure_filename

from app import db
from app.auth_utils import rol_requerido, verificar_escritura_cliente, verificar_visita_editable
from app.models import Equipo, Foto, Instalacion, ItemVisita, ORIGENES_FOTO

fotos_bp = Blueprint("fotos", __name__, url_prefix="/fotos")


def _extension_permitida(nombre_archivo):
    return (
        "." in nombre_archivo
        and nombre_archivo.rsplit(".", 1)[1].lower() in current_app.config["EXTENSIONES_PERMITIDAS"]
    )


def _parse_fecha(valor, por_defecto=None):
    if not valor:
        return por_defecto
    return datetime.strptime(valor, "%Y-%m-%d").date()


def _guardar_archivo(archivo, empresa_id, cliente_id, instalacion_id, equipo_id=None):
    """Guarda el archivo bajo UPLOAD_FOLDER organizado por
    empresa/cliente/instalación/equipo (o 'general' si no es de un equipo
    puntual), y devuelve la ruta relativa a guardar en Foto.nombre_archivo
    — la ruta 'ver' ya sirve subcarpetas vía <path:nombre_archivo>."""
    carpeta_relativa = os.path.join(
        str(empresa_id), str(cliente_id), str(instalacion_id), str(equipo_id) if equipo_id else "general"
    )
    carpeta_absoluta = os.path.join(current_app.config["UPLOAD_FOLDER"], carpeta_relativa)
    os.makedirs(carpeta_absoluta, exist_ok=True)
    nombre_seguro = secure_filename(archivo.filename)
    nombre_unico = f"{uuid.uuid4().hex}_{nombre_seguro}"
    archivo.save(os.path.join(carpeta_absoluta, nombre_unico))
    return os.path.join(carpeta_relativa, nombre_unico)


@fotos_bp.route("/subir/<int:item_id>", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def subir(item_id):
    """Foto sacada durante un servicio puntual de una visita (flujo de
    siempre). Opcionalmente se le puede indicar a qué equipo corresponde
    (ej. cuál de los 5 ECA que se revisaron en la visita)."""
    item = ItemVisita.query.get_or_404(item_id)
    instalacion = item.visita.instalacion
    cliente = instalacion.cliente
    verificar_escritura_cliente(cliente)
    verificar_visita_editable(item.visita)
    archivo = request.files.get("foto")

    if not archivo or archivo.filename == "":
        flash("No se seleccionó ninguna foto.", "danger")
        return redirect(url_for("visitas.detalle", visita_id=item.visita_id))

    if not _extension_permitida(archivo.filename):
        flash("Formato no permitido. Usá JPG, PNG, GIF o WEBP.", "danger")
        return redirect(url_for("visitas.detalle", visita_id=item.visita_id))

    equipo_id = request.form.get("equipo_id", type=int)
    equipo = Equipo.query.get(equipo_id) if equipo_id else None
    if equipo and equipo.instalacion_id != instalacion.id:
        abort(400)

    ruta_relativa = _guardar_archivo(archivo, cliente.empresa_id, cliente.id, instalacion.id, equipo.id if equipo else None)

    foto = Foto(
        item_visita_id=item.id,
        instalacion_id=instalacion.id,
        equipo_id=equipo.id if equipo else None,
        nombre_archivo=ruta_relativa,
        descripcion=request.form.get("descripcion"),
        origen="Visita",
        fecha_toma=date.today(),
        subido_por_id=current_user.id,
    )
    db.session.add(foto)
    db.session.commit()
    flash("Foto subida correctamente.", "success")
    return redirect(url_for("visitas.detalle", visita_id=item.visita_id))


@fotos_bp.route("/subir-manual/<int:instalacion_id>", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def subir_manual(instalacion_id):
    """Carga una foto suelta, sin pasar por una visita: para una foto que
    se saca fuera de un servicio programado, o para migrar fotos de un
    sistema anterior (con su fecha de toma real, no la de hoy). Se liga a
    la instalación y, opcionalmente, a un equipo puntual."""
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    cliente = instalacion.cliente
    verificar_escritura_cliente(cliente)
    equipo_preseleccionado = request.args.get("equipo_id", type=int)
    origenes_permitidos = [o for o in ORIGENES_FOTO if o != "Visita"]

    if request.method == "POST":
        archivo = request.files.get("foto")
        if not archivo or archivo.filename == "":
            flash("No se seleccionó ninguna foto.", "danger")
            return redirect(url_for("fotos.subir_manual", instalacion_id=instalacion.id))

        if not _extension_permitida(archivo.filename):
            flash("Formato no permitido. Usá JPG, PNG, GIF o WEBP.", "danger")
            return redirect(url_for("fotos.subir_manual", instalacion_id=instalacion.id))

        equipo_id = request.form.get("equipo_id", type=int)
        equipo = Equipo.query.get(equipo_id) if equipo_id else None
        if equipo and equipo.instalacion_id != instalacion.id:
            abort(400)

        origen_elegido = request.form.get("origen")
        origen = origen_elegido if origen_elegido in origenes_permitidos else "Carga manual"

        ruta_relativa = _guardar_archivo(
            archivo, cliente.empresa_id, cliente.id, instalacion.id, equipo.id if equipo else None
        )

        foto = Foto(
            instalacion_id=instalacion.id,
            equipo_id=equipo.id if equipo else None,
            nombre_archivo=ruta_relativa,
            descripcion=request.form.get("descripcion"),
            origen=origen,
            fecha_toma=_parse_fecha(request.form.get("fecha_toma"), date.today()),
            subido_por_id=current_user.id,
        )
        db.session.add(foto)
        db.session.commit()
        flash("Foto cargada correctamente.", "success")
        if foto.equipo_id:
            return redirect(url_for("equipos.detalle", equipo_id=foto.equipo_id))
        return redirect(url_for("instalaciones.detalle", instalacion_id=instalacion.id))

    return render_template(
        "fotos/subir_manual.html",
        instalacion=instalacion,
        equipos=instalacion.equipos,
        equipo_preseleccionado=equipo_preseleccionado,
        origenes=origenes_permitidos,
        hoy=date.today().isoformat(),
    )


@fotos_bp.route("/<int:foto_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar(foto_id):
    foto = Foto.query.get_or_404(foto_id)
    verificar_escritura_cliente(foto.instalacion.cliente)
    if foto.item_visita:
        verificar_visita_editable(foto.item_visita.visita)
    ruta = os.path.join(current_app.config["UPLOAD_FOLDER"], foto.nombre_archivo)
    if os.path.exists(ruta):
        os.remove(ruta)

    destino_visita_id = foto.item_visita.visita_id if foto.item_visita else None
    destino_equipo_id = foto.equipo_id
    destino_instalacion_id = foto.instalacion_id

    db.session.delete(foto)
    db.session.commit()
    flash("Foto eliminada.", "info")

    if destino_visita_id:
        return redirect(url_for("visitas.detalle", visita_id=destino_visita_id))
    if destino_equipo_id:
        return redirect(url_for("equipos.detalle", equipo_id=destino_equipo_id))
    return redirect(url_for("instalaciones.detalle", instalacion_id=destino_instalacion_id))


@fotos_bp.route("/ver/<path:nombre_archivo>")
def ver(nombre_archivo):
    # El login global ya exige sesión iniciada; el nombre de archivo lleva
    # un prefijo aleatorio (uuid4) no adivinable, así que no se agrega acá
    # una verificación de pertenencia adicional por ahora.
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], nombre_archivo)
