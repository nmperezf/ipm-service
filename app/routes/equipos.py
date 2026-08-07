from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import (
    rol_requerido,
    verificar_acceso_cliente,
    verificar_escritura_cliente,
    verificar_password_confirmacion,
)
from app.models import Equipo, Formulario, Instalacion, TIPOS_BOMBA_PRINCIPAL, TIPOS_CON_DATOS_PLACA, nombres_tipos_equipo
from app.notificaciones import notificar_gestion
from app.utils import es_ajax, filas_checklist

equipos_bp = Blueprint("equipos", __name__, url_prefix="/equipos")


def _aplicar_datos_bomba(equipo, form):
    """Campos de placa y de motor, que solo se completan para los tipos en
    TIPOS_CON_DATOS_PLACA — se guardan igual si vienen en el form (el
    toggle es solo visual), pero quedan en None para cualquier otro tipo
    de equipo."""
    if form.get("tipo") not in TIPOS_CON_DATOS_PLACA:
        equipo.modelo = None
        equipo.serie = None
        equipo.caudal_nominal = None
        equipo.presion_diseno = None
        equipo.presion_maxima = None
        equipo.presion_sobrecarga = None
        equipo.rpm_nominal = None
        equipo.anio_fabricacion = None
        equipo.otros_datos_placa = None
        _aplicar_datos_motor(equipo, {})
        return

    equipo.modelo = form.get("modelo") or None
    equipo.serie = form.get("serie") or None
    caudal = form.get("caudal_nominal") or None
    equipo.caudal_nominal = float(caudal) if caudal else None
    presion = form.get("presion_diseno") or None
    equipo.presion_diseno = float(presion) if presion else None
    presion_max = form.get("presion_maxima") or None
    equipo.presion_maxima = float(presion_max) if presion_max else None
    presion_sobrecarga = form.get("presion_sobrecarga") or None
    equipo.presion_sobrecarga = float(presion_sobrecarga) if presion_sobrecarga else None
    rpm = form.get("rpm_nominal") or None
    equipo.rpm_nominal = int(float(rpm)) if rpm else None
    anio = form.get("anio_fabricacion") or None
    equipo.anio_fabricacion = int(float(anio)) if anio else None
    equipo.otros_datos_placa = form.get("otros_datos_placa") or None
    _aplicar_datos_motor(equipo, form)


def _aplicar_datos_motor(equipo, form):
    tipo_motor = form.get("tipo_motor") or None
    equipo.tipo_motor = tipo_motor

    potencia = form.get("motor_potencia_hp") or None
    equipo.motor_potencia_hp = float(potencia) if potencia else None

    if tipo_motor == "Eléctrico":
        voltaje = form.get("motor_voltaje") or None
        equipo.motor_voltaje = float(voltaje) if voltaje else None
        amperaje = form.get("motor_amperaje") or None
        equipo.motor_amperaje = float(amperaje) if amperaje else None
        fases = form.get("motor_fases") or None
        equipo.motor_fases = int(fases) if fases else None
        equipo.motor_marca_modelo = None
        equipo.motor_combustible_litros = None
        equipo.motor_horas_uso = None
        equipo.motor_estado_bateria = None
    elif tipo_motor == "Diesel":
        equipo.motor_voltaje = None
        equipo.motor_amperaje = None
        equipo.motor_fases = None
        equipo.motor_marca_modelo = form.get("motor_marca_modelo") or None
        combustible = form.get("motor_combustible_litros") or None
        equipo.motor_combustible_litros = float(combustible) if combustible else None
        horas = form.get("motor_horas_uso") or None
        equipo.motor_horas_uso = float(horas) if horas else None
        equipo.motor_estado_bateria = form.get("motor_estado_bateria") or None
    else:
        equipo.motor_voltaje = None
        equipo.motor_amperaje = None
        equipo.motor_fases = None
        equipo.motor_marca_modelo = None
        equipo.motor_combustible_litros = None
        equipo.motor_horas_uso = None
        equipo.motor_estado_bateria = None


@equipos_bp.route("/nuevo/<int:instalacion_id>", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def nuevo(instalacion_id):
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_escritura_cliente(instalacion.cliente)
    manifolds = [e for e in instalacion.equipos if e.tipo == "Manifold" and e.activo]

    if request.method == "POST":
        manifold_id = request.form.get("manifold_id") or None
        equipo = Equipo(
            instalacion_id=instalacion.id,
            tipo=request.form["tipo"],
            nombre=request.form["nombre"],
            ubicacion=request.form.get("ubicacion"),
            manifold_id=int(manifold_id) if manifold_id else None,
        )
        _aplicar_datos_bomba(equipo, request.form)
        db.session.add(equipo)
        db.session.flush()
        notificar_gestion(
            empresa_id=instalacion.cliente.empresa_id,
            tipo="equipo_nuevo",
            titulo=f"Equipo nuevo — {equipo.nombre} ({instalacion.nombre})",
            cliente_id=instalacion.cliente_id,
            enlace=url_for("equipos.detalle", equipo_id=equipo.id),
            remitente=current_user,
        )
        db.session.commit()
        mensaje = f"Equipo '{equipo.nombre}' ({equipo.tipo}) creado."
        if es_ajax():
            return jsonify(ok=True, mensaje=mensaje)
        flash(mensaje, "success")
        return redirect(url_for("instalaciones.detalle", instalacion_id=instalacion.id))

    template = "equipos/_form_fragment.html" if es_ajax() else "equipos/form.html"
    return render_template(
        template,
        instalacion=instalacion,
        equipo=None,
        tipos=nombres_tipos_equipo(),
        manifolds=manifolds,
    )


@equipos_bp.route("/<int:equipo_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def editar(equipo_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    verificar_escritura_cliente(equipo.instalacion.cliente)
    manifolds = [
        e for e in equipo.instalacion.equipos if e.tipo == "Manifold" and e.activo and e.id != equipo.id
    ]

    if request.method == "POST":
        manifold_id = request.form.get("manifold_id") or None
        equipo.tipo = request.form["tipo"]
        equipo.nombre = request.form["nombre"]
        equipo.ubicacion = request.form.get("ubicacion")
        equipo.manifold_id = int(manifold_id) if manifold_id else None
        equipo.activo = bool(request.form.get("activo"))
        _aplicar_datos_bomba(equipo, request.form)
        db.session.commit()
        flash(f"Equipo '{equipo.nombre}' actualizado.", "success")
        return redirect(url_for("instalaciones.detalle", instalacion_id=equipo.instalacion_id))

    return render_template(
        "equipos/form.html",
        instalacion=equipo.instalacion,
        equipo=equipo,
        tipos=nombres_tipos_equipo(),
        manifolds=manifolds,
    )


@equipos_bp.route("/<int:equipo_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar(equipo_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    verificar_escritura_cliente(equipo.instalacion.cliente)
    if not verificar_password_confirmacion():
        return redirect(url_for("equipos.editar", equipo_id=equipo.id))
    instalacion_id = equipo.instalacion_id
    db.session.delete(equipo)
    db.session.commit()
    flash(f"Equipo '{equipo.nombre}' eliminado.", "info")
    return redirect(url_for("instalaciones.detalle", instalacion_id=instalacion_id))


@equipos_bp.route("/<int:equipo_id>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def detalle(equipo_id):
    """Ficha del equipo: histórico y trazabilidad de cada parámetro de su
    checklist a través del tiempo (ej. presión, estado de manguera,
    posición de válvula, mes a mes), más las deficiencias abiertas sobre
    este equipo puntual."""
    equipo = Equipo.query.get_or_404(equipo_id)
    verificar_acceso_cliente(equipo.instalacion.cliente)
    formularios = (
        Formulario.query.filter_by(equipo_id=equipo.id).order_by(Formulario.fecha_creacion).all()
    )
    grupos = filas_checklist(formularios)

    deficiencias_abiertas = sorted((o for o in equipo.deficiencias if not o.resuelto), key=lambda o: o.fecha_carga, reverse=True)
    deficiencias_resueltas = sorted((o for o in equipo.deficiencias if o.resuelto), key=lambda o: o.fecha_carga, reverse=True)

    ultimos_ensayos = []
    if equipo.tipo in TIPOS_BOMBA_PRINCIPAL:
        ultimos_ensayos = sorted(equipo.ensayos_caudal, key=lambda e: e.fecha_ensayo, reverse=True)[:3]

    return render_template(
        "equipos/detalle.html",
        equipo=equipo,
        grupos=grupos,
        deficiencias_abiertas=deficiencias_abiertas,
        deficiencias_resueltas=deficiencias_resueltas,
        ultimos_ensayos=ultimos_ensayos,
    )
