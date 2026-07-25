from collections import defaultdict
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from flask import Blueprint, redirect, render_template, request, url_for

from app.auth_utils import clientes_visibles, rol_requerido
from app.models import Instalacion, Visita
from app.utils import actualizar_vencimientos

planificacion_bp = Blueprint("planificacion", __name__, url_prefix="/planificacion")

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


@planificacion_bp.route("/calendario")
@rol_requerido("Administrador", "Jefe", "Técnico")
def calendario():
    """Calendario mensual: solo entran visitas que pertenecen a un
    contrato, de clientes visibles para el usuario logueado. Cada día
    muestra los clientes con visita ese día, como chips clickeables
    coloreados según el estado agregado de la visita."""
    actualizar_vencimientos()

    anio = request.args.get("anio", type=int) or date.today().year
    mes = request.args.get("mes", type=int) or date.today().month
    if mes < 1 or mes > 12:
        return redirect(url_for("planificacion.calendario"))

    primer_dia = date(anio, mes, 1)
    ultimo_dia = primer_dia + relativedelta(months=1) - timedelta(days=1)

    ids_clientes = [c.id for c in clientes_visibles().all()]
    visitas = (
        Visita.query.join(Visita.instalacion)
        .filter(Instalacion.cliente_id.in_(ids_clientes))
        .filter(Visita.contrato_id.isnot(None))
        .filter(Visita.fecha >= primer_dia, Visita.fecha <= ultimo_dia)
        .order_by(Visita.fecha)
        .all()
    )

    visitas_por_dia = defaultdict(list)
    for v in visitas:
        visitas_por_dia[v.fecha.day].append(v)

    # Construye semanas completas (lunes a domingo) que cubren el mes
    inicio_grilla = primer_dia - timedelta(days=primer_dia.weekday())
    fin_grilla = ultimo_dia + timedelta(days=(6 - ultimo_dia.weekday()))
    semanas = []
    cursor = inicio_grilla
    while cursor <= fin_grilla:
        semanas.append([cursor + timedelta(days=i) for i in range(7)])
        cursor += timedelta(days=7)

    mes_anterior = primer_dia - relativedelta(months=1)
    mes_siguiente = primer_dia + relativedelta(months=1)

    return render_template(
        "planificacion/calendario.html",
        anio=anio,
        mes=mes,
        titulo_mes=f"{MESES_ES[mes - 1]} {anio}",
        semanas=semanas,
        mes_actual=primer_dia,
        visitas_por_dia=visitas_por_dia,
        mes_anterior=mes_anterior,
        mes_siguiente=mes_siguiente,
    )
