from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.auth_utils import rol_requerido
from app.models import ESTADOS_PRESUPUESTO, Presupuesto

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
    """Dashboard de presupuestos de la empresa, agrupados por estado."""
    estado_filtro = request.args.get("estado", "")
    query = Presupuesto.query.filter_by(empresa_id=current_user.empresa_id)
    if estado_filtro in ESTADOS_PRESUPUESTO:
        query = query.filter_by(estado=estado_filtro)
    presupuestos = query.order_by(Presupuesto.fecha_creacion.desc()).all()

    por_estado = {estado: [] for estado in ESTADOS_PRESUPUESTO}
    for p in presupuestos:
        por_estado[p.estado].append(p)

    return render_template(
        "presupuestos/lista.html", por_estado=por_estado, estados=ESTADOS_PRESUPUESTO, estado_filtro=estado_filtro
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
