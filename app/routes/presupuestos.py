from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func

from app import db
from app.auth_utils import rol_requerido, verificar_password_confirmacion
from app.models import ESTADOS_PRESUPUESTO, Presupuesto
from app.utils import PAGINA_TAMANO, parse_orden

presupuestos_bp = Blueprint("presupuestos", __name__, url_prefix="/presupuestos")

# Transiciones permitidas desde cada estado — Cerrado y Rechazado son
# terminales (Cerrado lo pone solo el cierre de la OT correctiva, ver
# ordenes_trabajo.editar). Se valida acá, no solo en el <select> del
# template, para no confiar en lo que mande el navegador.
TRANSICIONES_VALIDAS = {
    "Pendiente": ["Cotizado"],
    "Cotizado": ["Aprobado", "Rechazado"],
}


@presupuestos_bp.route("/")
@rol_requerido("Administrador", "Jefe")
def listar():
    """Dashboard de presupuestos de la empresa. Sin filtro de estado,
    resumen agrupado (así se ve todo el flujo de un vistazo, cada balde
    suele ser chico). Con un estado elegido, lista completa y paginada de
    ese balde — ahí es donde se puede acumular historial con los años
    (sobre todo Cerrado/Rechazado)."""
    estado_filtro = request.args.get("estado", "")

    conteo_por_estado = dict(
        db.session.query(Presupuesto.estado, func.count(Presupuesto.id))
        .filter_by(empresa_id=current_user.empresa_id)
        .group_by(Presupuesto.estado)
        .all()
    )

    pagination = None
    por_estado = None
    orden_actual = dir_actual = None
    if estado_filtro in ESTADOS_PRESUPUESTO:
        columnas_orden = {"fecha_creacion": Presupuesto.fecha_creacion, "codigo": Presupuesto.codigo}
        orden_actual, dir_actual, orden_sql = parse_orden(columnas_orden, "fecha_creacion")
        pagina = request.args.get("pagina", 1, type=int)
        pagination = (
            Presupuesto.query.filter_by(empresa_id=current_user.empresa_id, estado=estado_filtro)
            .order_by(orden_sql)
            .paginate(page=pagina, per_page=PAGINA_TAMANO, error_out=False)
        )
    else:
        presupuestos = (
            Presupuesto.query.filter_by(empresa_id=current_user.empresa_id)
            .order_by(Presupuesto.fecha_creacion.desc())
            .all()
        )
        por_estado = {estado: [] for estado in ESTADOS_PRESUPUESTO}
        for p in presupuestos:
            por_estado[p.estado].append(p)

    return render_template(
        "presupuestos/lista.html",
        estados=ESTADOS_PRESUPUESTO,
        estado_filtro=estado_filtro,
        conteo_por_estado=conteo_por_estado,
        por_estado=por_estado,
        pagination=pagination,
        orden_actual=orden_actual,
        dir_actual=dir_actual,
    )


@presupuestos_bp.route("/<int:presupuesto_id>", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def detalle(presupuesto_id):
    presupuesto = Presupuesto.query.get_or_404(presupuesto_id)
    if presupuesto.empresa_id != current_user.empresa_id:
        abort(403)

    if request.method == "POST":
        nuevo_estado = request.form.get("estado")
        nota = request.form.get("nota", "").strip() or None
        if nuevo_estado not in TRANSICIONES_VALIDAS.get(presupuesto.estado, []):
            flash("Ese cambio de estado no es válido desde el estado actual.", "danger")
            return redirect(url_for("presupuestos.detalle", presupuesto_id=presupuesto.id))
        presupuesto.cambiar_estado(nuevo_estado, current_user.id, nota)
        db.session.commit()
        flash(f"Presupuesto {presupuesto.codigo} → {nuevo_estado}.", "success")
        return redirect(url_for("presupuestos.detalle", presupuesto_id=presupuesto.id))

    return render_template(
        "presupuestos/detalle.html",
        presupuesto=presupuesto,
        siguientes_estados=TRANSICIONES_VALIDAS.get(presupuesto.estado, []),
    )


@presupuestos_bp.route("/<int:presupuesto_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def eliminar(presupuesto_id):
    presupuesto = Presupuesto.query.get_or_404(presupuesto_id)
    if presupuesto.empresa_id != current_user.empresa_id:
        abort(403)
    if not verificar_password_confirmacion():
        return redirect(url_for("presupuestos.detalle", presupuesto_id=presupuesto.id))
    codigo = presupuesto.codigo
    db.session.delete(presupuesto)
    db.session.commit()
    flash(f"Presupuesto {codigo} eliminado.", "info")
    return redirect(url_for("presupuestos.listar"))
