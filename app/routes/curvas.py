from datetime import datetime

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import rol_requerido, verificar_acceso_cliente, verificar_escritura_cliente
from app.models import CurvaFabrica, EnsayoCaudal, Equipo
from app.pdf_curva_caudal import generar_pdf_ensayo
from app.utils import calcular_presion_ajustada, validar_nfpa25

curvas_bp = Blueprint("curvas", __name__, url_prefix="/equipos")

PUNTOS = ["0", "50", "100", "150"]


def _verificar_es_bomba(equipo):
    if equipo.tipo != "Bomba":
        abort(404)


def _parse_fecha(valor):
    return datetime.strptime(valor, "%Y-%m-%d").date()


@curvas_bp.route("/<int:equipo_id>/curva-fabrica", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def curva_fabrica(equipo_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    _verificar_es_bomba(equipo)
    verificar_escritura_cliente(equipo.instalacion.cliente)

    if request.method == "POST":
        try:
            rpm_nominal = int(request.form["rpm_nominal"])
            valores = {p: float(request.form[f"punto_{p}_presion"]) for p in PUNTOS}
        except (KeyError, ValueError):
            flash("Completá la RPM y las 4 presiones con valores numéricos válidos.", "danger")
            return render_template("equipos/formulario_curva_fabrica.html", equipo=equipo, curva=None)

        if rpm_nominal <= 0:
            flash("La RPM nominal tiene que ser mayor a 0.", "danger")
            return render_template("equipos/formulario_curva_fabrica.html", equipo=equipo, curva=None)

        curva = equipo.curva_fabrica
        if not curva:
            curva = CurvaFabrica(equipo_id=equipo.id)
            db.session.add(curva)
        curva.rpm_nominal = rpm_nominal
        curva.punto_0_presion = valores["0"]
        curva.punto_50_presion = valores["50"]
        curva.punto_100_presion = valores["100"]
        curva.punto_150_presion = valores["150"]
        db.session.commit()
        flash(f"Curva de fábrica de '{equipo.nombre}' guardada.", "success")
        return redirect(url_for("equipos.detalle", equipo_id=equipo.id))

    return render_template("equipos/formulario_curva_fabrica.html", equipo=equipo, curva=equipo.curva_fabrica)


@curvas_bp.route("/<int:equipo_id>/ensayos")
@rol_requerido("Administrador", "Jefe", "Técnico")
def ensayos(equipo_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    _verificar_es_bomba(equipo)
    verificar_acceso_cliente(equipo.instalacion.cliente)

    año_filtro = request.args.get("año", type=int)
    ensayos_lista = sorted(equipo.ensayos_caudal, key=lambda e: e.fecha_ensayo, reverse=True)
    años_disponibles = sorted({e.fecha_ensayo.year for e in ensayos_lista}, reverse=True)
    if año_filtro:
        ensayos_lista = [e for e in ensayos_lista if e.fecha_ensayo.year == año_filtro]

    return render_template(
        "equipos/lista_ensayos.html",
        equipo=equipo,
        ensayos=ensayos_lista,
        años_disponibles=años_disponibles,
        año_filtro=año_filtro,
    )


@curvas_bp.route("/<int:equipo_id>/ensayo/nuevo", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def ensayo_nuevo(equipo_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    _verificar_es_bomba(equipo)
    verificar_escritura_cliente(equipo.instalacion.cliente)

    if not equipo.curva_fabrica:
        flash(
            f"'{equipo.nombre}' todavía no tiene curva de fábrica cargada — cargala antes de registrar un ensayo.",
            "danger",
        )
        return redirect(url_for("equipos.detalle", equipo_id=equipo.id))

    if request.method == "POST":
        try:
            fecha_ensayo = _parse_fecha(request.form["fecha_ensayo"])
            datos_puntos = {}
            for p in PUNTOS:
                rpm = int(request.form[f"rpm_punto_{p}"])
                descarga = float(request.form[f"presion_descarga_punto_{p}"])
                succion = float(request.form[f"presion_succion_punto_{p}"])
                datos_puntos[p] = {"rpm": rpm, "descarga": descarga, "succion": succion, "neta": descarga - succion}
        except (KeyError, ValueError):
            flash("Completá los 4 puntos (RPM, presión de descarga y succión) con valores numéricos.", "danger")
            return render_template("equipos/formulario_ensayo.html", equipo=equipo, curva=equipo.curva_fabrica)

        if EnsayoCaudal.query.filter_by(equipo_id=equipo.id, fecha_ensayo=fecha_ensayo).first():
            flash(f"Ya hay un ensayo cargado para '{equipo.nombre}' con fecha {fecha_ensayo.strftime('%d/%m/%Y')}.", "danger")
            return render_template("equipos/formulario_ensayo.html", equipo=equipo, curva=equipo.curva_fabrica)

        ensayo = EnsayoCaudal(
            equipo_id=equipo.id,
            fecha_ensayo=fecha_ensayo,
            rpm_punto_0=datos_puntos["0"]["rpm"],
            presion_descarga_punto_0=datos_puntos["0"]["descarga"],
            presion_succion_punto_0=datos_puntos["0"]["succion"],
            presion_neta_punto_0=datos_puntos["0"]["neta"],
            rpm_punto_50=datos_puntos["50"]["rpm"],
            presion_descarga_punto_50=datos_puntos["50"]["descarga"],
            presion_succion_punto_50=datos_puntos["50"]["succion"],
            presion_neta_punto_50=datos_puntos["50"]["neta"],
            rpm_punto_100=datos_puntos["100"]["rpm"],
            presion_descarga_punto_100=datos_puntos["100"]["descarga"],
            presion_succion_punto_100=datos_puntos["100"]["succion"],
            presion_neta_punto_100=datos_puntos["100"]["neta"],
            rpm_punto_150=datos_puntos["150"]["rpm"],
            presion_descarga_punto_150=datos_puntos["150"]["descarga"],
            presion_succion_punto_150=datos_puntos["150"]["succion"],
            presion_neta_punto_150=datos_puntos["150"]["neta"],
            creado_por_id=current_user.id,
        )
        db.session.add(ensayo)
        db.session.commit()
        flash(f"Ensayo del {fecha_ensayo.strftime('%d/%m/%Y')} guardado para '{equipo.nombre}'.", "success")
        return redirect(url_for("curvas.ensayo_detalle", equipo_id=equipo.id, ensayo_id=ensayo.id))

    return render_template("equipos/formulario_ensayo.html", equipo=equipo, curva=equipo.curva_fabrica)


@curvas_bp.route("/<int:equipo_id>/ensayo/<int:ensayo_id>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def ensayo_detalle(equipo_id, ensayo_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    _verificar_es_bomba(equipo)
    verificar_acceso_cliente(equipo.instalacion.cliente)
    ensayo = EnsayoCaudal.query.get_or_404(ensayo_id)
    if ensayo.equipo_id != equipo.id:
        abort(404)

    validacion = ensayo.validacion_nfpa25()
    ajustadas = ensayo.puntos_ajustados(equipo.curva_fabrica.rpm_nominal) if equipo.curva_fabrica else None

    return render_template(
        "equipos/detalle_ensayo.html",
        equipo=equipo,
        ensayo=ensayo,
        curva=equipo.curva_fabrica,
        ajustadas=ajustadas,
        validacion=validacion,
        resultado=ensayo.resultado_nfpa25(),
    )


@curvas_bp.route("/<int:equipo_id>/ensayo/<int:ensayo_id>/pdf")
@rol_requerido("Administrador", "Jefe", "Técnico")
def ensayo_pdf(equipo_id, ensayo_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    _verificar_es_bomba(equipo)
    verificar_acceso_cliente(equipo.instalacion.cliente)
    ensayo = EnsayoCaudal.query.get_or_404(ensayo_id)
    if ensayo.equipo_id != equipo.id:
        abort(404)

    pdf_bytes = generar_pdf_ensayo(ensayo)
    nombre_archivo = f"Curva_caudal_{equipo.nombre.replace(' ', '_')}_{ensayo.fecha_ensayo}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"inline; filename={nombre_archivo}"},
    )


@curvas_bp.route("/calcular-preview", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def calcular_preview():
    """Endpoint auxiliar para el botón 'Calcular y validar' del formulario
    de ensayo nuevo — recalcula server-side (misma lógica que al guardar) y
    devuelve JSON, para no duplicar la fórmula en JS de forma divergente."""
    try:
        rpm_nominal_fabrica = int(request.form["rpm_nominal_fabrica"])
        presiones_fabrica = [float(request.form[f"fabrica_{p}"]) for p in PUNTOS]
        netas = []
        rpms = []
        for p in PUNTOS:
            descarga = float(request.form[f"presion_descarga_punto_{p}"])
            succion = float(request.form[f"presion_succion_punto_{p}"])
            netas.append(descarga - succion)
            rpms.append(int(request.form[f"rpm_punto_{p}"]))
    except (KeyError, ValueError):
        return {"error": "Completá todos los campos con valores numéricos."}, 400

    ajustadas = [calcular_presion_ajustada(n, r, rpm_nominal_fabrica) for n, r in zip(netas, rpms)]
    validacion = validar_nfpa25(ajustadas, presiones_fabrica)
    aprobado = all(c["paso"] for c in validacion.values())
    return {
        "netas": [round(n, 1) for n in netas],
        "ajustadas": ajustadas,
        "validacion": validacion,
        "aprobado": aprobado,
    }
