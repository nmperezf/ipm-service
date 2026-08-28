from datetime import date

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import rol_requerido, verificar_acceso_cliente, verificar_escritura_cliente
from app.models import (
    DIAMETROS_BIE,
    ESTADOS_GABINETE,
    ESTADOS_RACOR,
    RESULTADOS_PRUEBA_BOCA,
    TIPOS_BIE,
    TIPOS_PUNTERO,
    TIPOS_RACOR,
    Equipo,
    InspeccionBie,
    ItemVisita,
    Observacion,
)
from app.pdf_bie import generar_pdf_ficha_bie
from app.utils import parse_fecha

bie_bp = Blueprint("bie", __name__, url_prefix="/equipos")


def _contexto_ficha(equipo, item):
    return dict(
        equipo=equipo,
        item=item,
        hoy=date.today().isoformat(),
        tipos_bie=TIPOS_BIE,
        diametros_bie=DIAMETROS_BIE,
        tipos_puntero=TIPOS_PUNTERO,
        tipos_racor=TIPOS_RACOR,
        estados_racor=ESTADOS_RACOR,
        estados_gabinete=ESTADOS_GABINETE,
        resultados_prueba_boca=RESULTADOS_PRUEBA_BOCA,
    )


def _verificar_es_bie(equipo):
    if equipo.tipo != "BIE":
        abort(404)


def _item_visita_de_la_ficha(equipo, item_id):
    """Ítem de visita al que se le va a linkear la ficha, si vino de ese
    flujo — valida que sea de la misma instalación (mismo criterio que
    curvas.py:_item_visita_del_ensayo)."""
    if not item_id:
        return None
    item = ItemVisita.query.get_or_404(item_id)
    if item.visita.instalacion_id != equipo.instalacion_id:
        abort(404)
    return item


def _aplicar_datos_gabinete(equipo, form):
    equipo.tipo_bie = form.get("tipo_bie") or None
    equipo.diametro_nominal = form.get("diametro_nominal") or None
    equipo.tipo_puntero = form.get("tipo_puntero") or None
    equipo.tipo_racor = form.get("tipo_racor") or None
    equipo.estado_racor = form.get("estado_racor") or None
    equipo.llave_spanner = form.get("llave_spanner") == "1"
    equipo.valvula_operable = form.get("valvula_operable") == "1"
    manometro = form.get("manometro_bar", "").strip()
    equipo.manometro_bar = float(manometro) if manometro else None
    equipo.estado_gabinete = form.get("estado_gabinete") or None


def _manguera_activa_asignada(equipo):
    return next((m for m in equipo.mangueras if m.activa), None)


def _verificar_diametro_manguera(equipo):
    """Si hay una manguera activa asignada a esta BIE y su diámetro no
    coincide con el de la boca, genera una Observación de "Deficiencia no
    crítica" -- mismo criterio de "Pendiente" que el resto de la app."""
    manguera = _manguera_activa_asignada(equipo)
    if not manguera or not equipo.diametro_nominal or manguera.diametro == equipo.diametro_nominal:
        return None
    return Observacion(
        instalacion_id=equipo.instalacion_id,
        equipo_id=equipo.id,
        clasificacion="Deficiencia no crítica",
        descripcion=(
            f"Diámetro de la boca ({equipo.diametro_nominal}) no coincide con el de la "
            f"manguera asignada {manguera.numero_serie} ({manguera.diametro})."
        ),
        estado_revision="Pendiente",
        creado_por_id=current_user.id,
    )


CLASIFICACION_POR_VEREDICTO = {
    "Con observaciones": "Deficiencia no crítica",
    "Fuera de servicio": "Deficiencia crítica",
}


@bie_bp.route("/<int:equipo_id>/ficha-bie", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def ficha(equipo_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    _verificar_es_bie(equipo)
    verificar_escritura_cliente(equipo.instalacion.cliente)
    item_id = request.values.get("item_id", type=int)
    item = _item_visita_de_la_ficha(equipo, item_id)

    if request.method == "POST":
        try:
            fecha = parse_fecha(request.form["fecha"])
        except (KeyError, ValueError):
            flash("La fecha de inspección es obligatoria y debe ser válida.", "danger")
            return render_template("equipos/ficha_bie.html", **_contexto_ficha(equipo, item))

        veredicto = request.form.get("veredicto")
        if veredicto not in ("Apta / operativa", "Con observaciones", "Fuera de servicio"):
            flash("Elegí un veredicto válido.", "danger")
            return render_template("equipos/ficha_bie.html", **_contexto_ficha(equipo, item))

        _aplicar_datos_gabinete(equipo, request.form)

        fecha_prueba_boca = parse_fecha(request.form.get("fecha_prueba_boca"), silencioso=True)
        resultado_prueba_boca = request.form.get("resultado_prueba_boca") or None

        inspeccion = InspeccionBie(
            equipo_id=equipo.id,
            item_visita_id=item.id if item else None,
            fecha=fecha,
            fecha_prueba_boca=fecha_prueba_boca,
            resultado_prueba_boca=resultado_prueba_boca,
            veredicto=veredicto,
            dictamen=request.form.get("dictamen") or None,
            realizado_por_id=current_user.id,
        )
        db.session.add(inspeccion)

        clasificacion = CLASIFICACION_POR_VEREDICTO.get(veredicto)
        if clasificacion:
            observacion = Observacion(
                instalacion_id=equipo.instalacion_id,
                equipo_id=equipo.id,
                clasificacion=clasificacion,
                descripcion=inspeccion.dictamen or f"Ficha de inspección BIE — veredicto: {veredicto}.",
                estado_revision="Pendiente",
                creado_por_id=current_user.id,
            )
            db.session.add(observacion)
            db.session.flush()
            inspeccion.observacion_id = observacion.id

        obs_diametro = _verificar_diametro_manguera(equipo)
        if obs_diametro:
            db.session.add(obs_diametro)

        if item:
            item.visita.marcar_item_cumplido(item.id)

        db.session.commit()
        flash(f"Ficha de inspección de '{equipo.nombre}' guardada.", "success")
        if item:
            return redirect(url_for("visitas.detalle", visita_id=item.visita_id))
        return redirect(url_for("equipos.detalle", equipo_id=equipo.id))

    return render_template("equipos/ficha_bie.html", **_contexto_ficha(equipo, item))


@bie_bp.route("/<int:equipo_id>/ficha-bie/pdf")
@rol_requerido("Administrador", "Jefe", "Técnico", "Cliente")
def ficha_pdf(equipo_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    _verificar_es_bie(equipo)
    verificar_acceso_cliente(equipo.instalacion.cliente)

    ultima = sorted(equipo.inspecciones_bie, key=lambda i: i.fecha, reverse=True)[0] if equipo.inspecciones_bie else None
    if not ultima:
        flash(f"'{equipo.nombre}' todavía no tiene ninguna inspección cargada.", "danger")
        return redirect(url_for("equipos.detalle", equipo_id=equipo.id))

    pdf_bytes = generar_pdf_ficha_bie(equipo, ultima)
    nombre_archivo = f"Inspeccion_BIE_{equipo.nombre.replace(' ', '_')}_{ultima.fecha.isoformat()}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"inline; filename={nombre_archivo}"},
    )
