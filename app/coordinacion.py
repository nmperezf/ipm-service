"""Generación y coordinación de visitas mes a mes — reemplaza la vieja
Contrato.generar_visitas() (todo el año de una, con la fecha del contrato
sin confirmar). Acá la Visita/OT recién nacen cuando alguien coordina."""

from datetime import date, datetime

from dateutil.relativedelta import relativedelta

from app import db
from app.models import (
    Contrato,
    CoordinacionAudit,
    ItemVisita,
    OrdenTrabajo,
    SolicitudCoordinacion,
    Visita,
)


def servicios_del_mes(contrato, anio, mes):
    """Servicios activos del contrato cuya fechas_ocurrencia() cae en ese
    año/mes puntual."""
    return [
        s
        for s in contrato.servicios
        if s.activo and any(f.year == anio and f.month == mes for f in s.fechas_ocurrencia())
    ]


def generar_solicitudes_mes(empresa_id, anio, mes):
    """Crea una SolicitudCoordinacion por cada contrato activo de la
    empresa que tenga algún servicio programado ese mes y todavía no
    tenga solicitud ni visita ya cargada (a mano o de una generación
    vieja) para ese mes — no duplica, se puede volver a apretar el botón
    sin problema. Devuelve cuántas creó."""
    primer_dia_mes = date(anio, mes, 1)
    primer_dia_siguiente_mes = primer_dia_mes + relativedelta(months=1)
    contratos = (
        Contrato.query.join(Contrato.instalacion)
        .filter(
            Contrato.activo == True,  # noqa: E712
            Contrato.estado == "Activo",
            Contrato.fecha_inicio < primer_dia_siguiente_mes,
            Contrato.fecha_fin > primer_dia_mes,
        )
        .all()
    )
    contratos = [c for c in contratos if c.instalacion.cliente.empresa_id == empresa_id]

    creadas = 0
    for contrato in contratos:
        if not servicios_del_mes(contrato, anio, mes):
            continue
        ya_existe = SolicitudCoordinacion.query.filter_by(contrato_id=contrato.id, anio=anio, mes=mes).first()
        if ya_existe:
            continue
        # Si ya hay una visita real cargada ese mes (de la generación vieja,
        # o cargada a mano), se considera ya resuelta — no pedir coordinar
        # de nuevo algo que ya tiene fecha.
        ya_tiene_visita = any(v.fecha.year == anio and v.fecha.month == mes for v in contrato.visitas)
        if ya_tiene_visita:
            continue
        db.session.add(SolicitudCoordinacion(contrato_id=contrato.id, anio=anio, mes=mes))
        creadas += 1
    db.session.commit()
    return creadas


def coordinar_solicitud(solicitud, fecha, notas, usuario):
    """Confirma la fecha real de una solicitud. La primera vez, crea la
    Visita + sus ItemVisita + la OrdenTrabajo preventiva (mismo criterio
    que la vieja generación automática, pero con la fecha que de verdad
    se acordó). Si ya estaba coordinada, es una recoordinación: mueve la
    fecha de la Visita/OT existentes. Siempre deja un renglón de
    auditoría con la fecha anterior y la nueva."""
    fecha_anterior = solicitud.fecha_coordinada
    contrato = solicitud.contrato

    if solicitud.visita:
        visita = solicitud.visita
        visita.fecha = fecha
        if visita.orden_trabajo:
            visita.orden_trabajo.fecha_apertura = fecha
    else:
        visita = Visita(
            instalacion_id=contrato.instalacion_id,
            contrato_id=contrato.id,
            fecha=fecha,
            estado="Pendiente",
        )
        db.session.add(visita)
        db.session.flush()
        for servicio in servicios_del_mes(contrato, solicitud.anio, solicitud.mes):
            db.session.add(
                ItemVisita(visita_id=visita.id, servicio_contrato_id=servicio.id, estado="Pendiente")
            )
        ot = OrdenTrabajo(
            instalacion_id=contrato.instalacion_id,
            visita_id=visita.id,
            tipo="Preventivo",
            prioridad="Media",
            estado="Pendiente",
            fecha_apertura=fecha,
        )
        db.session.add(ot)
        db.session.flush()
        ot.asignar_numero()
        solicitud.visita_id = visita.id

    solicitud.coordinada = True
    solicitud.fecha_coordinada = fecha
    solicitud.notas = notas
    solicitud.coordinado_por_id = usuario.id
    solicitud.fecha_coordinacion = datetime.now()

    db.session.add(
        CoordinacionAudit(
            solicitud_id=solicitud.id,
            fecha_anterior=fecha_anterior,
            fecha_nueva=fecha,
            usuario_id=usuario.id,
            nota=notas,
        )
    )
    db.session.commit()
    return visita
