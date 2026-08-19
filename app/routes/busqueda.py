from flask import Blueprint, render_template, request

from app.auth_utils import clientes_visibles, rol_requerido
from app.models import Cliente, Equipo, Instalacion, OrdenTrabajo

busqueda_bp = Blueprint("busqueda", __name__, url_prefix="/buscar")

TOPE_POR_TIPO = 5


@busqueda_bp.route("/")
@rol_requerido("Administrador", "Jefe", "Técnico")
def buscar():
    """Buscador global de la topbar: junta Cliente/Instalación/Equipo/OT
    que coincidan con 'q' por nombre o número, acotado a lo que ya puede
    ver el usuario logueado (mismo criterio que clientes_visibles() usa en
    el resto de la app). Devuelve un fragmento HTML para inyectar en el
    panel flotante -- mismo patrón que notificaciones.resumen."""
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return render_template("busqueda/_resultados.html", q=q, resultados=None)

    ids_clientes = [fila[0] for fila in clientes_visibles().with_entities(Cliente.id).all()]
    patron = f"%{q}%"

    clientes = (
        clientes_visibles().filter(Cliente.nombre.ilike(patron)).order_by(Cliente.nombre).limit(TOPE_POR_TIPO).all()
        if ids_clientes
        else []
    )
    instalaciones = (
        Instalacion.query.filter(Instalacion.cliente_id.in_(ids_clientes), Instalacion.nombre.ilike(patron))
        .order_by(Instalacion.nombre)
        .limit(TOPE_POR_TIPO)
        .all()
        if ids_clientes
        else []
    )
    equipos = (
        Equipo.query.join(Instalacion)
        .filter(Instalacion.cliente_id.in_(ids_clientes), Equipo.nombre.ilike(patron))
        .order_by(Equipo.nombre)
        .limit(TOPE_POR_TIPO)
        .all()
        if ids_clientes
        else []
    )
    ordenes = (
        OrdenTrabajo.query.join(Instalacion)
        .filter(Instalacion.cliente_id.in_(ids_clientes), OrdenTrabajo.numero.ilike(patron))
        .order_by(OrdenTrabajo.numero.desc())
        .limit(TOPE_POR_TIPO)
        .all()
        if ids_clientes
        else []
    )

    resultados = {
        "Clientes": clientes,
        "Instalaciones": instalaciones,
        "Equipos": equipos,
        "Órdenes de trabajo": ordenes,
    }
    return render_template("busqueda/_resultados.html", q=q, resultados=resultados)
