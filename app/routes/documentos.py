import os
import uuid
from datetime import date

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template, request, send_from_directory, url_for,
)
from flask_login import current_user
from werkzeug.utils import secure_filename

from app import db
from app.auth_utils import rol_requerido, verificar_acceso_cliente, verificar_escritura_cliente
from app.models import Documento, Equipo, Instalacion
from app.utils import parse_fecha

documentos_bp = Blueprint("documentos", __name__, url_prefix="/documentos")


def _extension_permitida(nombre_archivo):
    return (
        "." in nombre_archivo
        and nombre_archivo.rsplit(".", 1)[1].lower() in current_app.config["EXTENSIONES_DOCUMENTOS"]
    )


def _guardar_archivo(archivo, empresa_id, cliente_id, instalacion_id):
    carpeta_relativa = os.path.join(str(empresa_id), str(cliente_id), str(instalacion_id), "documentos")
    carpeta_absoluta = os.path.join(current_app.config["UPLOAD_FOLDER"], carpeta_relativa)
    os.makedirs(carpeta_absoluta, exist_ok=True)
    nombre_seguro = secure_filename(archivo.filename)
    nombre_unico = f"{uuid.uuid4().hex}_{nombre_seguro}"
    archivo.save(os.path.join(carpeta_absoluta, nombre_unico))
    return os.path.join(carpeta_relativa, nombre_unico)


@documentos_bp.route("/subir/<int:instalacion_id>", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def subir(instalacion_id):
    """Carga un documento suelto (informe de alineación, trabajo especial,
    u otro archivo puntual) ligado a la instalación y, opcionalmente, a un
    equipo puntual — aparece en el histórico técnico como una fila más."""
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    cliente = instalacion.cliente
    verificar_escritura_cliente(cliente)
    equipo_preseleccionado = request.args.get("equipo_id", type=int)

    if request.method == "POST":
        archivo = request.files.get("archivo")
        if not archivo or archivo.filename == "":
            flash("No se seleccionó ningún archivo.", "danger")
            return redirect(url_for("documentos.subir", instalacion_id=instalacion.id))

        if not _extension_permitida(archivo.filename):
            flash("Formato no permitido. Usá PDF, Word, Excel o imagen.", "danger")
            return redirect(url_for("documentos.subir", instalacion_id=instalacion.id))

        titulo = (request.form.get("titulo") or "").strip()
        if not titulo:
            flash("El título es obligatorio.", "danger")
            return redirect(url_for("documentos.subir", instalacion_id=instalacion.id))

        equipo_id = request.form.get("equipo_id", type=int)
        equipo = db.session.get(Equipo, equipo_id) if equipo_id else None
        if equipo and equipo.instalacion_id != instalacion.id:
            abort(400)

        ruta_relativa = _guardar_archivo(archivo, cliente.empresa_id, cliente.id, instalacion.id)

        documento = Documento(
            instalacion_id=instalacion.id,
            equipo_id=equipo.id if equipo else None,
            titulo=titulo,
            descripcion=request.form.get("descripcion"),
            fecha_documento=parse_fecha(request.form.get("fecha_documento"), date.today()),
            nombre_archivo=ruta_relativa,
            subido_por_id=current_user.id,
        )
        db.session.add(documento)
        db.session.commit()
        flash("Documento cargado correctamente.", "success")
        return redirect(url_for("historial.ver", instalacion_id=instalacion.id))

    return render_template(
        "documentos/subir.html",
        instalacion=instalacion,
        equipos=instalacion.equipos,
        equipo_preseleccionado=equipo_preseleccionado,
        hoy=date.today().isoformat(),
    )


@documentos_bp.route("/<int:documento_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar(documento_id):
    documento = Documento.query.get_or_404(documento_id)
    verificar_escritura_cliente(documento.instalacion.cliente)
    ruta = os.path.join(current_app.config["UPLOAD_FOLDER"], documento.nombre_archivo)
    if os.path.exists(ruta):
        os.remove(ruta)
    instalacion_id = documento.instalacion_id
    db.session.delete(documento)
    db.session.commit()
    flash("Documento eliminado.", "info")
    return redirect(url_for("historial.ver", instalacion_id=instalacion_id))


@documentos_bp.route("/ver/<path:nombre_archivo>")
def ver(nombre_archivo):
    documento = Documento.query.filter_by(nombre_archivo=nombre_archivo).first_or_404()
    verificar_acceso_cliente(documento.instalacion.cliente)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], nombre_archivo)
