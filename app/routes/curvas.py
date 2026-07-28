from datetime import datetime

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import (
    rol_requerido,
    verificar_acceso_cliente,
    verificar_escritura_cliente,
    verificar_password_confirmacion,
)
from app.models import CurvaFabrica, EnsayoCaudal, Equipo
from app.notificaciones import notificar_gestion, notificar_usuario
from app.pdf_curva_caudal import generar_pdf_ensayo
from app.utils import calcular_presion_ajustada, curva_suavizada, validar_nfpa25

curvas_bp = Blueprint("curvas", __name__, url_prefix="/equipos")

PUNTOS = ["0", "50", "100", "150"]


def _verificar_es_bomba(equipo):
    if equipo.tipo != "Bomba":
        abort(404)


def _parse_fecha(valor):
    return datetime.strptime(valor, "%Y-%m-%d").date()


def _float_opcional(form, nombre):
    valor = form.get(nombre, "").strip()
    return float(valor) if valor else None


def _parse_puntos_ensayo(form):
    """Levanta los 4 puntos (RPM, descarga, succión, y opcionalmente caudal
    medido y potencia absorbida) del form y calcula la presión neta de cada
    uno. Lanza (KeyError, ValueError) si falta o hay algún valor no numérico
    en los campos obligatorios — el caller decide qué hacer con eso."""
    datos_puntos = {}
    for p in PUNTOS:
        rpm = int(form[f"rpm_punto_{p}"])
        descarga = float(form[f"presion_descarga_punto_{p}"])
        succion = float(form[f"presion_succion_punto_{p}"])
        datos_puntos[p] = {
            "rpm": rpm, "descarga": descarga, "succion": succion, "neta": descarga - succion,
            "gpm": _float_opcional(form, f"caudal_gpm_punto_{p}"),
            # Potencia absorbida queda deliberadamente en blanco si no hay forma
            # de medirla (ej. motor diésel sin instrumentación).
            "abs": _float_opcional(form, f"potencia_absorbida_punto_{p}"),
        }
    return datos_puntos


def _aplicar_puntos_ensayo(ensayo, datos_puntos):
    for p in PUNTOS:
        d = datos_puntos[p]
        setattr(ensayo, f"rpm_punto_{p}", d["rpm"])
        setattr(ensayo, f"presion_descarga_punto_{p}", d["descarga"])
        setattr(ensayo, f"presion_succion_punto_{p}", d["succion"])
        setattr(ensayo, f"presion_neta_punto_{p}", d["neta"])
        setattr(ensayo, f"caudal_gpm_punto_{p}", d["gpm"])
        setattr(ensayo, f"potencia_absorbida_punto_{p}", d["abs"])


def _aplicar_condiciones_prueba(ensayo, form):
    ensayo.temperatura_ambiente = _float_opcional(form, "temperatura_ambiente")
    ensayo.presion_atmosferica_mbar = _float_opcional(form, "presion_atmosferica_mbar")
    ensayo.presion_succion_estatica = _float_opcional(form, "presion_succion_estatica")
    ensayo.normativa_aplicable = form.get("normativa_aplicable", "").strip() or None


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

        potencias = {}
        for p in PUNTOS:
            valor = request.form.get(f"punto_{p}_potencia_kw", "").strip()
            potencias[p] = float(valor) if valor else None

        curva = equipo.curva_fabrica
        if not curva:
            curva = CurvaFabrica(equipo_id=equipo.id)
            db.session.add(curva)
        curva.rpm_nominal = rpm_nominal
        curva.punto_0_presion = valores["0"]
        curva.punto_50_presion = valores["50"]
        curva.punto_100_presion = valores["100"]
        curva.punto_150_presion = valores["150"]
        curva.punto_0_potencia_kw = potencias["0"]
        curva.punto_50_potencia_kw = potencias["50"]
        curva.punto_100_potencia_kw = potencias["100"]
        curva.punto_150_potencia_kw = potencias["150"]
        db.session.commit()
        flash(f"Curva de fábrica de '{equipo.nombre}' guardada.", "success")
        return redirect(url_for("equipos.detalle", equipo_id=equipo.id))

    return render_template("equipos/formulario_curva_fabrica.html", equipo=equipo, curva=equipo.curva_fabrica)


@curvas_bp.route("/<int:equipo_id>/ensayos")
@rol_requerido("Administrador", "Jefe", "Técnico", "Cliente")
def ensayos(equipo_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    _verificar_es_bomba(equipo)
    verificar_acceso_cliente(equipo.instalacion.cliente)

    ensayos_lista = sorted(equipo.ensayos_caudal, key=lambda e: e.fecha_ensayo, reverse=True)
    if current_user.rol == "Cliente":
        # El cliente solo ve lo que ya pasó el control de calidad del
        # Jefe/Administrador — mismo criterio que Observacion/Formulario.
        ensayos_lista = [e for e in ensayos_lista if e.estado_revision == "Validado"]

    año_filtro = request.args.get("año", type=int)
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
            datos_puntos = _parse_puntos_ensayo(request.form)
        except (KeyError, ValueError):
            flash("Completá los 4 puntos (RPM, presión de descarga y succión) con valores numéricos.", "danger")
            return render_template("equipos/formulario_ensayo.html", equipo=equipo, curva=equipo.curva_fabrica, ensayo=None)

        if EnsayoCaudal.query.filter_by(equipo_id=equipo.id, fecha_ensayo=fecha_ensayo).first():
            flash(f"Ya hay un ensayo cargado para '{equipo.nombre}' con fecha {fecha_ensayo.strftime('%d/%m/%Y')}.", "danger")
            return render_template("equipos/formulario_ensayo.html", equipo=equipo, curva=equipo.curva_fabrica, ensayo=None)

        ensayo = EnsayoCaudal(equipo_id=equipo.id, fecha_ensayo=fecha_ensayo, creado_por_id=current_user.id)
        _aplicar_puntos_ensayo(ensayo, datos_puntos)
        _aplicar_condiciones_prueba(ensayo, request.form)
        ensayo.comentarios = request.form.get("comentarios") or None
        db.session.add(ensayo)
        db.session.flush()
        notificar_gestion(
            empresa_id=current_user.empresa_id,
            tipo="ensayo_nuevo",
            titulo=f"Nuevo ensayo de curva de caudal — {equipo.nombre}",
            cliente_id=equipo.instalacion.cliente_id,
            enlace=url_for("curvas.ensayo_detalle", equipo_id=equipo.id, ensayo_id=ensayo.id),
            remitente=current_user,
        )
        db.session.commit()
        flash(f"Ensayo del {fecha_ensayo.strftime('%d/%m/%Y')} guardado para '{equipo.nombre}'.", "success")
        return redirect(url_for("curvas.ensayo_detalle", equipo_id=equipo.id, ensayo_id=ensayo.id))

    return render_template("equipos/formulario_ensayo.html", equipo=equipo, curva=equipo.curva_fabrica, ensayo=None)


@curvas_bp.route("/<int:equipo_id>/ensayo/<int:ensayo_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def ensayo_editar(equipo_id, ensayo_id):
    """Solo Administrador/Jefe puede corregir un ensayo ya cargado por un
    técnico — un técnico que se equivocó tiene que pedirle a su Jefe que lo
    corrija, no lo edita directamente."""
    equipo = Equipo.query.get_or_404(equipo_id)
    _verificar_es_bomba(equipo)
    verificar_escritura_cliente(equipo.instalacion.cliente)
    ensayo = EnsayoCaudal.query.get_or_404(ensayo_id)
    if ensayo.equipo_id != equipo.id:
        abort(404)

    if request.method == "POST":
        try:
            fecha_ensayo = _parse_fecha(request.form["fecha_ensayo"])
            datos_puntos = _parse_puntos_ensayo(request.form)
        except (KeyError, ValueError):
            flash("Completá los 4 puntos (RPM, presión de descarga y succión) con valores numéricos.", "danger")
            return render_template("equipos/formulario_ensayo.html", equipo=equipo, curva=equipo.curva_fabrica, ensayo=ensayo)

        conflicto = EnsayoCaudal.query.filter(
            EnsayoCaudal.equipo_id == equipo.id,
            EnsayoCaudal.fecha_ensayo == fecha_ensayo,
            EnsayoCaudal.id != ensayo.id,
        ).first()
        if conflicto:
            flash(f"Ya hay otro ensayo cargado para '{equipo.nombre}' con fecha {fecha_ensayo.strftime('%d/%m/%Y')}.", "danger")
            return render_template("equipos/formulario_ensayo.html", equipo=equipo, curva=equipo.curva_fabrica, ensayo=ensayo)

        cambio_datos = ensayo.fecha_ensayo != fecha_ensayo or any(
            getattr(ensayo, f"rpm_punto_{p}") != datos_puntos[p]["rpm"]
            or getattr(ensayo, f"presion_descarga_punto_{p}") != datos_puntos[p]["descarga"]
            or getattr(ensayo, f"presion_succion_punto_{p}") != datos_puntos[p]["succion"]
            for p in PUNTOS
        )

        ensayo.fecha_ensayo = fecha_ensayo
        _aplicar_puntos_ensayo(ensayo, datos_puntos)
        _aplicar_condiciones_prueba(ensayo, request.form)
        ensayo.comentarios = request.form.get("comentarios") or None

        if cambio_datos:
            # Corregir los datos vuelve a dejar el ensayo pendiente de
            # revisión — la validación anterior era sobre valores que ya no
            # son estos. Si solo se tocó el comentario, la revisión no se
            # toca.
            ensayo.estado_revision = "Pendiente"
            ensayo.validado_por_id = None
            ensayo.fecha_validacion = None
            db.session.commit()
            flash(f"Ensayo del {fecha_ensayo.strftime('%d/%m/%Y')} actualizado. Queda pendiente de revisión otra vez.", "success")
        else:
            db.session.commit()
            flash(f"Ensayo del {fecha_ensayo.strftime('%d/%m/%Y')} actualizado.", "success")
        return redirect(url_for("curvas.ensayo_detalle", equipo_id=equipo.id, ensayo_id=ensayo.id))

    return render_template("equipos/formulario_ensayo.html", equipo=equipo, curva=equipo.curva_fabrica, ensayo=ensayo)


@curvas_bp.route("/<int:equipo_id>/ensayo/<int:ensayo_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def ensayo_eliminar(equipo_id, ensayo_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    _verificar_es_bomba(equipo)
    verificar_escritura_cliente(equipo.instalacion.cliente)
    ensayo = EnsayoCaudal.query.get_or_404(ensayo_id)
    if ensayo.equipo_id != equipo.id:
        abort(404)
    if not verificar_password_confirmacion():
        return redirect(url_for("curvas.ensayo_detalle", equipo_id=equipo.id, ensayo_id=ensayo.id))

    fecha = ensayo.fecha_ensayo
    db.session.delete(ensayo)
    db.session.commit()
    flash(f"Ensayo del {fecha.strftime('%d/%m/%Y')} eliminado.", "info")
    return redirect(url_for("curvas.ensayos", equipo_id=equipo.id))


@curvas_bp.route("/<int:equipo_id>/ensayo/<int:ensayo_id>/validar", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def ensayo_validar(equipo_id, ensayo_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    _verificar_es_bomba(equipo)
    verificar_escritura_cliente(equipo.instalacion.cliente)
    ensayo = EnsayoCaudal.query.get_or_404(ensayo_id)
    if ensayo.equipo_id != equipo.id:
        abort(404)

    ensayo.validar(current_user.id)
    if ensayo.creado_por:
        notificar_usuario(
            ensayo.creado_por,
            tipo="ensayo_validado",
            titulo=f"Ensayo validado — {equipo.nombre} ({ensayo.fecha_ensayo.strftime('%d/%m/%Y')})",
            empresa_id=current_user.empresa_id,
            cliente_id=equipo.instalacion.cliente_id,
            enlace=url_for("curvas.ensayo_detalle", equipo_id=equipo.id, ensayo_id=ensayo.id),
            remitente=current_user,
        )
    db.session.commit()
    flash(f"Ensayo del {ensayo.fecha_ensayo.strftime('%d/%m/%Y')} validado.", "success")
    return redirect(url_for("curvas.ensayo_detalle", equipo_id=equipo.id, ensayo_id=ensayo.id))


@curvas_bp.route("/<int:equipo_id>/ensayo/<int:ensayo_id>/rechazar", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def ensayo_rechazar(equipo_id, ensayo_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    _verificar_es_bomba(equipo)
    verificar_escritura_cliente(equipo.instalacion.cliente)
    ensayo = EnsayoCaudal.query.get_or_404(ensayo_id)
    if ensayo.equipo_id != equipo.id:
        abort(404)

    ensayo.rechazar(current_user.id)
    if ensayo.creado_por:
        notificar_usuario(
            ensayo.creado_por,
            tipo="ensayo_rechazado",
            titulo=f"Ensayo rechazado — {equipo.nombre} ({ensayo.fecha_ensayo.strftime('%d/%m/%Y')})",
            empresa_id=current_user.empresa_id,
            cliente_id=equipo.instalacion.cliente_id,
            enlace=url_for("curvas.ensayo_detalle", equipo_id=equipo.id, ensayo_id=ensayo.id),
            remitente=current_user,
        )
    db.session.commit()
    flash(f"Ensayo del {ensayo.fecha_ensayo.strftime('%d/%m/%Y')} rechazado.", "info")
    return redirect(url_for("curvas.ensayo_detalle", equipo_id=equipo.id, ensayo_id=ensayo.id))


@curvas_bp.route("/<int:equipo_id>/ensayo/<int:ensayo_id>/forzar-resultado", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def ensayo_forzar_resultado(equipo_id, ensayo_id):
    """Deja que el Administrador/Jefe fije a mano el resultado NFPA 25
    (independiente del cálculo de los 3 criterios) — para los casos donde
    el criterio de ingeniería difiere del cálculo estricto. 'Automatico'
    vuelve a dejar que decida el cálculo."""
    equipo = Equipo.query.get_or_404(equipo_id)
    _verificar_es_bomba(equipo)
    verificar_escritura_cliente(equipo.instalacion.cliente)
    ensayo = EnsayoCaudal.query.get_or_404(ensayo_id)
    if ensayo.equipo_id != equipo.id:
        abort(404)

    valor = request.form.get("resultado")
    if valor not in ("Aprobado", "Rechazado", "Automatico"):
        abort(400)
    ensayo.resultado_manual = None if valor == "Automatico" else valor
    db.session.commit()
    if valor == "Automatico":
        flash("Resultado NFPA 25 vuelve a decidirse por el cálculo automático.", "info")
    else:
        flash(f"Resultado NFPA 25 fijado manualmente como '{valor}'.", "success")
    return redirect(url_for("curvas.ensayo_detalle", equipo_id=equipo.id, ensayo_id=ensayo.id))


@curvas_bp.route("/<int:equipo_id>/ensayo/<int:ensayo_id>")
@rol_requerido("Administrador", "Jefe", "Técnico", "Cliente")
def ensayo_detalle(equipo_id, ensayo_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    _verificar_es_bomba(equipo)
    verificar_acceso_cliente(equipo.instalacion.cliente)
    ensayo = EnsayoCaudal.query.get_or_404(ensayo_id)
    if ensayo.equipo_id != equipo.id:
        abort(404)
    if current_user.rol == "Cliente" and ensayo.estado_revision != "Validado":
        abort(403)

    validacion = ensayo.validacion_nfpa25()
    ajustadas = ensayo.puntos_ajustados(equipo.curva_fabrica.rpm_nominal) if equipo.curva_fabrica else None
    sin_ajustar = [round(n, 1) for n in ensayo.puntos_netos()]

    grafico = None
    if equipo.curva_fabrica:
        caudales = [0, 50, 100, 150]
        _, presiones_fabrica = equipo.curva_fabrica.puntos()
        xs_fabrica, ys_fabrica = curva_suavizada(caudales, presiones_fabrica)
        xs_ensayo, ys_ensayo = curva_suavizada(caudales, ajustadas)
        xs_sin_ajustar, ys_sin_ajustar = curva_suavizada(caudales, sin_ajustar)
        grafico = {
            "caudales": caudales,
            "fabrica": {"puntos": presiones_fabrica, "suave_x": xs_fabrica, "suave_y": ys_fabrica},
            "ensayo": {"puntos": ajustadas, "suave_x": xs_ensayo, "suave_y": ys_ensayo},
            "sin_ajustar": {"puntos": sin_ajustar, "suave_x": xs_sin_ajustar, "suave_y": ys_sin_ajustar},
        }

    return render_template(
        "equipos/detalle_ensayo.html",
        equipo=equipo,
        ensayo=ensayo,
        curva=equipo.curva_fabrica,
        ajustadas=ajustadas,
        sin_ajustar=sin_ajustar,
        validacion=validacion,
        resultado_automatico=ensayo.resultado_nfpa25(),
        resultado=ensayo.resultado_final(),
        grafico=grafico,
    )


@curvas_bp.route("/<int:equipo_id>/ensayo/<int:ensayo_id>/pdf")
@rol_requerido("Administrador", "Jefe", "Técnico", "Cliente")
def ensayo_pdf(equipo_id, ensayo_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    _verificar_es_bomba(equipo)
    verificar_acceso_cliente(equipo.instalacion.cliente)
    ensayo = EnsayoCaudal.query.get_or_404(ensayo_id)
    if ensayo.equipo_id != equipo.id:
        abort(404)
    if current_user.rol == "Cliente" and ensayo.estado_revision != "Validado":
        abort(403)

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
