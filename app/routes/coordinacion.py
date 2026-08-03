from datetime import date, datetime

from dateutil.relativedelta import relativedelta
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import rol_requerido
from app.coordinacion import coordinar_solicitud, generar_solicitudes_mes, servicios_del_mes
from app.models import Instalacion, SolicitudCoordinacion

coordinacion_bp = Blueprint("coordinacion", __name__, url_prefix="/coordinacion")

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def _verificar_solicitud(solicitud):
    if current_user.rol != "Super Admin" and solicitud.contrato.instalacion.cliente.empresa_id != current_user.empresa_id:
        abort(403)


@coordinacion_bp.route("/")
@rol_requerido("Administrador", "Jefe")
def index():
    anio = request.args.get("anio", type=int) or date.today().year
    mes = request.args.get("mes", type=int) or date.today().month
    if mes < 1 or mes > 12:
        return redirect(url_for("coordinacion.index"))

    primer_dia = date(anio, mes, 1)
    mes_anterior = primer_dia - relativedelta(months=1)
    mes_siguiente = primer_dia + relativedelta(months=1)

    solicitudes = (
        SolicitudCoordinacion.query.join(SolicitudCoordinacion.contrato)
        .join(Instalacion)
        .filter(
            SolicitudCoordinacion.anio == anio,
            SolicitudCoordinacion.mes == mes,
            Instalacion.cliente.has(empresa_id=current_user.empresa_id),
        )
        .all()
    )
    # Más recientes / con más para hacer primero: sin coordinar arriba de todo.
    orden_estado = {"sin_coordinar": 0, "coordinada": 1, "asignada": 2, "en_ejecucion": 3, "ejecutada": 4}
    solicitudes.sort(key=lambda s: (orden_estado.get(s.estado_derivado, 9), s.contrato.instalacion.cliente.nombre))

    conteos = {"sin_coordinar": 0, "coordinada": 0, "asignada": 0, "en_ejecucion": 0, "ejecutada": 0}
    servicios_por_solicitud = {}
    for s in solicitudes:
        conteos[s.estado_derivado] += 1
        servicios_por_solicitud[s.id] = servicios_del_mes(s.contrato, s.anio, s.mes)

    return render_template(
        "coordinacion/index.html",
        anio=anio,
        mes=mes,
        titulo_mes=f"{MESES_ES[mes - 1]} {anio}",
        mes_anterior=mes_anterior,
        mes_siguiente=mes_siguiente,
        meses_es=MESES_ES,
        solicitudes=solicitudes,
        servicios_por_solicitud=servicios_por_solicitud,
        conteos=conteos,
        total=len(solicitudes),
        asignadas_o_mas=conteos["asignada"] + conteos["en_ejecucion"] + conteos["ejecutada"],
        hoy=date.today(),
    )


@coordinacion_bp.route("/generar", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def generar():
    anio = request.form.get("anio", type=int) or date.today().year
    mes = request.form.get("mes", type=int) or date.today().month
    creadas = generar_solicitudes_mes(current_user.empresa_id, anio, mes)
    if creadas:
        flash(f"Se generaron {creadas} solicitud{'es' if creadas != 1 else ''} de coordinación.", "success")
    else:
        flash("No hay nada nuevo para coordinar ese mes — ya está todo generado.", "info")
    return redirect(url_for("coordinacion.index", anio=anio, mes=mes))


@coordinacion_bp.route("/<int:solicitud_id>/coordinar", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def coordinar(solicitud_id):
    solicitud = SolicitudCoordinacion.query.get_or_404(solicitud_id)
    _verificar_solicitud(solicitud)

    fecha = datetime.strptime(request.form["fecha"], "%Y-%m-%d").date()
    notas = request.form.get("notas") or None
    coordinar_solicitud(solicitud, fecha, notas, current_user)
    flash(f"{solicitud.contrato.instalacion.nombre} — visita coordinada para el {fecha.strftime('%d/%m/%Y')}.", "success")
    return redirect(url_for("coordinacion.index", anio=solicitud.anio, mes=solicitud.mes))
