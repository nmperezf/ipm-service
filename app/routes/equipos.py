from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.auth_utils import rol_requerido, verificar_acceso_cliente, verificar_escritura_cliente
from app.models import Equipo, Formulario, Instalacion, nombres_tipos_equipo
from app.utils import construir_secciones_historico

equipos_bp = Blueprint("equipos", __name__, url_prefix="/equipos")


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
        db.session.add(equipo)
        db.session.commit()
        flash(f"Equipo '{equipo.nombre}' ({equipo.tipo}) creado.", "success")
        return redirect(url_for("instalaciones.detalle", instalacion_id=instalacion.id))

    return render_template(
        "equipos/form.html", instalacion=instalacion, equipo=None, tipos=nombres_tipos_equipo(), manifolds=manifolds
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
        db.session.commit()
        flash(f"Equipo '{equipo.nombre}' actualizado.", "success")
        return redirect(url_for("instalaciones.detalle", instalacion_id=equipo.instalacion_id))

    return render_template(
        "equipos/form.html", instalacion=equipo.instalacion, equipo=equipo, tipos=nombres_tipos_equipo(), manifolds=manifolds
    )


@equipos_bp.route("/<int:equipo_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar(equipo_id):
    equipo = Equipo.query.get_or_404(equipo_id)
    verificar_escritura_cliente(equipo.instalacion.cliente)
    instalacion_id = equipo.instalacion_id
    db.session.delete(equipo)
    db.session.commit()
    flash(f"Equipo '{equipo.nombre}' eliminado.", "info")
    return redirect(url_for("instalaciones.detalle", instalacion_id=instalacion_id))


@equipos_bp.route("/<int:equipo_id>")
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
    secciones = construir_secciones_historico(formularios)

    deficiencias_abiertas = [o for o in equipo.deficiencias if not o.resuelto]
    deficiencias_resueltas = [o for o in equipo.deficiencias if o.resuelto]

    return render_template(
        "equipos/detalle.html",
        equipo=equipo,
        secciones=secciones,
        deficiencias_abiertas=deficiencias_abiertas,
        deficiencias_resueltas=deficiencias_resueltas,
    )
