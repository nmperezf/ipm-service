import os
import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

from app import db
from app.auth_utils import rol_requerido, verificar_acceso_cliente, verificar_escritura_cliente, verificar_visita_editable
from app.models import Foto, ItemVisita

fotos_bp = Blueprint("fotos", __name__, url_prefix="/fotos")


def _extension_permitida(nombre_archivo):
    return (
        "." in nombre_archivo
        and nombre_archivo.rsplit(".", 1)[1].lower() in current_app.config["EXTENSIONES_PERMITIDAS"]
    )


@fotos_bp.route("/subir/<int:item_id>", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def subir(item_id):
    item = ItemVisita.query.get_or_404(item_id)
    verificar_escritura_cliente(item.visita.instalacion.cliente)
    verificar_visita_editable(item.visita)
    archivo = request.files.get("foto")

    if not archivo or archivo.filename == "":
        flash("No se seleccionó ninguna foto.", "danger")
        return redirect(url_for("visitas.detalle", visita_id=item.visita_id))

    if not _extension_permitida(archivo.filename):
        flash("Formato no permitido. Usá JPG, PNG, GIF o WEBP.", "danger")
        return redirect(url_for("visitas.detalle", visita_id=item.visita_id))

    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    nombre_seguro = secure_filename(archivo.filename)
    nombre_unico = f"{uuid.uuid4().hex}_{nombre_seguro}"
    archivo.save(os.path.join(current_app.config["UPLOAD_FOLDER"], nombre_unico))

    foto = Foto(
        item_visita_id=item.id,
        nombre_archivo=nombre_unico,
        descripcion=request.form.get("descripcion"),
    )
    db.session.add(foto)
    db.session.commit()
    flash("Foto subida correctamente.", "success")
    return redirect(url_for("visitas.detalle", visita_id=item.visita_id))


@fotos_bp.route("/<int:foto_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar(foto_id):
    foto = Foto.query.get_or_404(foto_id)
    verificar_escritura_cliente(foto.item_visita.visita.instalacion.cliente)
    verificar_visita_editable(foto.item_visita.visita)
    visita_id = foto.item_visita.visita_id
    ruta = os.path.join(current_app.config["UPLOAD_FOLDER"], foto.nombre_archivo)
    if os.path.exists(ruta):
        os.remove(ruta)
    db.session.delete(foto)
    db.session.commit()
    flash("Foto eliminada.", "info")
    return redirect(url_for("visitas.detalle", visita_id=visita_id))


@fotos_bp.route("/ver/<path:nombre_archivo>")
def ver(nombre_archivo):
    # El login global ya exige sesión iniciada; el nombre de archivo lleva
    # un prefijo aleatorio (uuid4) no adivinable, así que no se agrega acá
    # una verificación de pertenencia adicional por ahora.
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], nombre_archivo)
