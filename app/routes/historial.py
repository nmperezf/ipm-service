import csv
import io

from flask import Blueprint, Response, render_template
from flask import request

from app.auth_utils import rol_requerido, verificar_acceso_cliente
from app.models import Documento, Instalacion, Observacion

historial_bp = Blueprint("historial", __name__, url_prefix="/historial")


def _filas_historial(instalacion):
    """Aplana todo el historial técnico de una instalación: cada fila es
    un servicio dentro de una visita, con su formulario y fotos si tiene."""
    filas = []
    for contrato in instalacion.contratos:
        for visita in sorted(contrato.visitas, key=lambda v: v.fecha):
            if not visita.items:
                filas.append(
                    {
                        "fecha": visita.fecha,
                        "contrato": contrato.nombre,
                        "servicio": "-",
                        "estado_item": "-",
                        "estado_visita": visita.estado,
                        "tecnico": visita.nombre_tecnico,
                        "observaciones": visita.observaciones or "",
                        "formularios": 0,
                        "fotos": 0,
                        "visita_id": visita.id,
                    }
                )
            for item in visita.items:
                filas.append(
                    {
                        "fecha": visita.fecha,
                        "contrato": contrato.nombre,
                        "servicio": item.servicio.nombre if item.servicio else "-",
                        "estado_item": item.estado,
                        "estado_visita": visita.estado,
                        "tecnico": visita.nombre_tecnico,
                        "observaciones": (item.observaciones or visita.observaciones or ""),
                        "formularios": len(item.formularios),
                        "fotos": len(item.fotos),
                        "visita_id": visita.id,
                    }
                )
    # Visitas sueltas sin contrato (alta manual)
    for visita in getattr(instalacion, "visitas", []):
        if visita.contrato_id is None:
            filas.append(
                {
                    "fecha": visita.fecha,
                    "contrato": "-",
                    "servicio": "Visita manual",
                    "estado_item": "-",
                    "estado_visita": visita.estado,
                    "tecnico": visita.nombre_tecnico,
                    "observaciones": visita.observaciones or "",
                    "formularios": sum(len(it.formularios) for it in visita.items),
                    "fotos": sum(len(it.fotos) for it in visita.items),
                    "visita_id": visita.id,
                }
            )
    # Documentos sueltos (informes de alineación, trabajos especiales, etc.)
    # -- no son una visita, se listan aparte con su propio link de descarga.
    for doc in instalacion.documentos:
        filas.append(
            {
                "fecha": doc.fecha_documento,
                "contrato": "-",
                "servicio": doc.titulo,
                "estado_item": "-",
                "estado_visita": "Documento",
                "tecnico": doc.subido_por.nombre_completo if doc.subido_por else "-",
                "observaciones": doc.descripcion or "",
                "formularios": 0,
                "fotos": 1,  # el documento en sí, para que la columna "Documentos" lo cuente
                "visita_id": None,
                "tipo": "documento",
                "documento_id": doc.id,
                "documento_archivo": doc.nombre_archivo,
            }
        )
    return sorted(filas, key=lambda f: f["fecha"], reverse=True)


@historial_bp.route("/<int:instalacion_id>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def ver(instalacion_id):
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_acceso_cliente(instalacion.cliente)
    filas = _filas_historial(instalacion)
    observaciones = sorted(instalacion.deficiencias, key=lambda o: o.fecha_carga, reverse=True)
    return render_template(
        "historial/ver.html", instalacion=instalacion, filas=filas, observaciones=observaciones
    )


@historial_bp.route("/<int:instalacion_id>/exportar.csv")
@rol_requerido("Administrador", "Jefe", "Técnico")
def exportar_csv(instalacion_id):
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_acceso_cliente(instalacion.cliente)
    filas = _filas_historial(instalacion)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["Fecha", "Contrato", "Servicio", "Estado servicio", "Estado visita", "Técnico", "Observaciones", "Formularios", "Fotos"]
    )
    for f in filas:
        writer.writerow(
            [
                f["fecha"].strftime("%d/%m/%Y"),
                f["contrato"],
                f["servicio"],
                f["estado_item"],
                f["estado_visita"],
                f["tecnico"],
                f["observaciones"],
                f["formularios"],
                f["fotos"],
            ]
        )

    nombre_archivo = f"historial_{instalacion.nombre.replace(' ', '_')}.csv"
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"},
    )
