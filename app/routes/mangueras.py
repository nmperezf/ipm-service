from datetime import date

from dateutil.relativedelta import relativedelta
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import (
    rol_requerido,
    verificar_acceso_cliente,
    verificar_escritura_cliente,
    verificar_password_confirmacion,
)
from app.models import (
    DESTINOS_ESPECIALES_MANGUERA,
    DIAMETROS_BIE,
    MATERIALES_MANGUERA,
    RESULTADOS_PH,
    Instalacion,
    Manguera,
    NotaMantenimientoManguera,
    Observacion,
    PruebaHidrostatica,
    ReubicacionManguera,
)
from app.utils import es_ajax, parse_fecha

mangueras_bp = Blueprint("mangueras", __name__, url_prefix="/instalaciones/<int:instalacion_id>/mangueras")


def _instalacion_con_acceso(instalacion_id, escritura=False):
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    if escritura:
        verificar_escritura_cliente(instalacion.cliente)
    else:
        verificar_acceso_cliente(instalacion.cliente)
    return instalacion


def _manguera_de_la_instalacion(instalacion, manguera_id):
    manguera = Manguera.query.get_or_404(manguera_id)
    if manguera.instalacion_id != instalacion.id:
        abort(404)
    return manguera


def _bies_activas(instalacion):
    return [e for e in instalacion.equipos if e.tipo == "BIE" and e.activo]


@mangueras_bp.route("/")
@rol_requerido("Administrador", "Jefe", "Técnico", "Cliente")
def lista(instalacion_id):
    instalacion = _instalacion_con_acceso(instalacion_id)
    mangueras = sorted(
        (m for m in instalacion.mangueras if m.activa),
        key=lambda m: (m.equipo.nombre if m.equipo else "", m.numero_serie),
    )
    stats = {
        "total": len(mangueras),
        "vigentes": sum(1 for m in mangueras if m.estado_ph == "Vigente"),
        "por_vencer": sum(1 for m in mangueras if m.estado_ph == "Por vencer"),
        "vencidas": sum(1 for m in mangueras if m.estado_ph == "Vencida"),
    }
    template = "mangueras/_contenido.html" if es_ajax() else "mangueras/lista.html"
    return render_template(
        template,
        instalacion=instalacion,
        mangueras=mangueras,
        stats=stats,
        bies=_bies_activas(instalacion),
    )


@mangueras_bp.route("/nueva", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def nueva(instalacion_id):
    instalacion = _instalacion_con_acceso(instalacion_id, escritura=True)

    if request.method == "POST":
        equipo_id = request.form.get("equipo_id") or None
        equipo = None
        if equipo_id:
            equipo = next((e for e in _bies_activas(instalacion) if e.id == int(equipo_id)), None)
            if not equipo:
                abort(400)
        ubicacion_libre = request.form.get("ubicacion_libre") or None
        lugar = equipo.ubicacion if equipo else (ubicacion_libre or "Sin ubicación")

        manguera = Manguera(
            instalacion_id=instalacion.id,
            equipo_id=equipo.id if equipo else None,
            ubicacion_libre=None if equipo else ubicacion_libre,
            numero_serie=request.form["numero_serie"],
            diametro=request.form["diametro"],
            longitud_metros=float(request.form["longitud_metros"]) if request.form.get("longitud_metros") else None,
            material=request.form.get("material") or None,
            lugar_origen=lugar,
        )
        db.session.add(manguera)
        db.session.commit()
        mensaje = f"Manguera '{manguera.numero_serie}' agregada."
        if es_ajax():
            return jsonify(ok=True, mensaje=mensaje)
        flash(mensaje, "success")
        return redirect(url_for("mangueras.lista", instalacion_id=instalacion.id))

    template = "mangueras/_form_fragment.html" if es_ajax() else "mangueras/form.html"
    return render_template(
        template,
        instalacion=instalacion,
        bies=_bies_activas(instalacion),
        diametros=DIAMETROS_BIE,
        materiales=MATERIALES_MANGUERA,
        destinos_especiales=DESTINOS_ESPECIALES_MANGUERA,
    )


@mangueras_bp.route("/<int:manguera_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def editar(instalacion_id, manguera_id):
    """Solo los datos propios de la manguera (serie, diámetro, longitud,
    material). Cambiar dónde está instalada es un movimiento con historial
    propio -- ver mangueras.reubicar, no se toca acá."""
    instalacion = _instalacion_con_acceso(instalacion_id, escritura=True)
    manguera = _manguera_de_la_instalacion(instalacion, manguera_id)

    if request.method == "POST":
        manguera.numero_serie = request.form["numero_serie"]
        manguera.diametro = request.form["diametro"]
        manguera.longitud_metros = float(request.form["longitud_metros"]) if request.form.get("longitud_metros") else None
        manguera.material = request.form.get("material") or None
        manguera.activa = bool(request.form.get("activa"))
        db.session.commit()
        mensaje = f"Manguera '{manguera.numero_serie}' actualizada."
        if es_ajax():
            return jsonify(ok=True, mensaje=mensaje)
        flash(mensaje, "success")
        return redirect(url_for("mangueras.lista", instalacion_id=instalacion.id))

    template = "mangueras/_editar_fragment.html" if es_ajax() else "mangueras/editar_form.html"
    return render_template(template, instalacion=instalacion, manguera=manguera, diametros=DIAMETROS_BIE, materiales=MATERIALES_MANGUERA)


@mangueras_bp.route("/<int:manguera_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar(instalacion_id, manguera_id):
    instalacion = _instalacion_con_acceso(instalacion_id, escritura=True)
    manguera = _manguera_de_la_instalacion(instalacion, manguera_id)
    if not verificar_password_confirmacion():
        return redirect(url_for("mangueras.lista", instalacion_id=instalacion.id))

    numero_serie = manguera.numero_serie
    db.session.delete(manguera)
    db.session.commit()
    flash(f"Manguera '{numero_serie}' eliminada.", "info")
    return redirect(url_for("mangueras.lista", instalacion_id=instalacion.id))


@mangueras_bp.route("/<int:manguera_id>/ph", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def registrar_ph(instalacion_id, manguera_id):
    instalacion = _instalacion_con_acceso(instalacion_id, escritura=True)
    manguera = _manguera_de_la_instalacion(instalacion, manguera_id)

    if request.method == "POST":
        resultado = request.form.get("resultado")
        if resultado not in RESULTADOS_PH:
            abort(400)
        try:
            fecha = parse_fecha(request.form["fecha"])
        except (KeyError, ValueError):
            abort(400)

        prueba = PruebaHidrostatica(
            manguera_id=manguera.id,
            fecha=fecha,
            presion_aplicada=float(request.form["presion_aplicada"]) if request.form.get("presion_aplicada") else None,
            tiempo_minutos=float(request.form["tiempo_minutos"]) if request.form.get("tiempo_minutos") else None,
            resultado=resultado,
            certificado=request.form.get("certificado") or None,
            realizado_por_id=current_user.id,
        )
        db.session.add(prueba)

        manguera.fecha_ultima_ph = fecha
        manguera.fecha_vencimiento_ph = fecha + relativedelta(years=5)
        manguera.resultado_ultima_ph = resultado

        if resultado == "Rechazada":
            observacion = Observacion(
                instalacion_id=instalacion.id,
                equipo_id=manguera.equipo_id,
                clasificacion="Deficiencia crítica",
                descripcion=f"Manguera {manguera.numero_serie} rechazada en prueba hidrostática del {fecha.strftime('%d/%m/%Y')}.",
                estado_revision="Pendiente",
                creado_por_id=current_user.id,
            )
            db.session.add(observacion)
            db.session.flush()
            prueba.observacion_id = observacion.id

        db.session.commit()
        mensaje = f"Prueba hidrostática registrada para '{manguera.numero_serie}'."
        if es_ajax():
            return jsonify(ok=True, mensaje=mensaje)
        flash(mensaje, "success")
        return redirect(url_for("mangueras.lista", instalacion_id=instalacion.id))

    template = "mangueras/_ph_fragment.html" if es_ajax() else "mangueras/ph_form.html"
    return render_template(
        template, instalacion=instalacion, manguera=manguera, resultados=RESULTADOS_PH, hoy=date.today().isoformat()
    )


@mangueras_bp.route("/<int:manguera_id>/reubicar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def reubicar(instalacion_id, manguera_id):
    instalacion = _instalacion_con_acceso(instalacion_id, escritura=True)
    manguera = _manguera_de_la_instalacion(instalacion, manguera_id)
    bies = [e for e in _bies_activas(instalacion) if e.id != manguera.equipo_id]

    if request.method == "POST":
        origen = manguera.lugar_actual
        destino_equipo_id = request.form.get("destino_equipo_id") or None
        destino_libre = request.form.get("destino_libre") or None

        if destino_equipo_id:
            equipo = next((e for e in bies if e.id == int(destino_equipo_id)), None)
            if not equipo:
                abort(400)
            manguera.equipo_id = equipo.id
            manguera.ubicacion_libre = None
            destino = equipo.ubicacion
        elif destino_libre in DESTINOS_ESPECIALES_MANGUERA:
            manguera.equipo_id = None
            manguera.ubicacion_libre = destino_libre
            destino = destino_libre
        else:
            abort(400)

        reubicacion = ReubicacionManguera(
            manguera_id=manguera.id,
            fecha=date.today(),
            origen=origen,
            destino=destino,
            motivo=request.form.get("motivo") or None,
            realizado_por_id=current_user.id,
        )
        db.session.add(reubicacion)
        db.session.commit()
        mensaje = f"'{manguera.numero_serie}' reubicada a {destino}."
        if es_ajax():
            return jsonify(ok=True, mensaje=mensaje)
        flash(mensaje, "success")
        return redirect(url_for("mangueras.lista", instalacion_id=instalacion.id))

    template = "mangueras/_reubicar_fragment.html" if es_ajax() else "mangueras/reubicar_form.html"
    return render_template(
        template, instalacion=instalacion, manguera=manguera, bies=bies,
        destinos_especiales=DESTINOS_ESPECIALES_MANGUERA,
    )


@mangueras_bp.route("/<int:manguera_id>/historial")
@rol_requerido("Administrador", "Jefe", "Técnico", "Cliente")
def historial(instalacion_id, manguera_id):
    instalacion = _instalacion_con_acceso(instalacion_id)
    manguera = _manguera_de_la_instalacion(instalacion, manguera_id)

    eventos = []
    for p in manguera.pruebas:
        eventos.append({"fecha": p.fecha, "tipo": "ph", "texto": f"Prueba hidrostática — {p.resultado}, {p.presion_aplicada or '-'} PSI / {p.tiempo_minutos or '-'} min"})
    for r in manguera.reubicaciones:
        eventos.append({"fecha": r.fecha, "tipo": "reubicacion", "texto": f"Reubicada: {r.origen} → {r.destino}"})
    for n in manguera.notas:
        eventos.append({"fecha": n.fecha, "tipo": "nota", "texto": n.texto})
    eventos.sort(key=lambda e: e["fecha"], reverse=True)

    return render_template("mangueras/_historial_fragment.html", instalacion=instalacion, manguera=manguera, eventos=eventos)


@mangueras_bp.route("/<int:manguera_id>/nota", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def nota(instalacion_id, manguera_id):
    instalacion = _instalacion_con_acceso(instalacion_id, escritura=True)
    manguera = _manguera_de_la_instalacion(instalacion, manguera_id)

    if request.method == "POST":
        db.session.add(
            NotaMantenimientoManguera(
                manguera_id=manguera.id,
                fecha=date.today(),
                texto=request.form["texto"],
                realizado_por_id=current_user.id,
            )
        )
        db.session.commit()
        mensaje = "Nota agregada al historial."
        if es_ajax():
            return jsonify(ok=True, mensaje=mensaje)
        flash(mensaje, "success")
        return redirect(url_for("mangueras.lista", instalacion_id=instalacion.id))

    template = "mangueras/_nota_fragment.html" if es_ajax() else "mangueras/nota_form.html"
    return render_template(template, instalacion=instalacion, manguera=manguera)
