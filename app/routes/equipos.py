from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import db
from app.auth_utils import rol_requerido, verificar_acceso_cliente, verificar_escritura_cliente
from app.models import Equipo, Formulario, Instalacion, TIPOS_EQUIPO

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
        "equipos/form.html", instalacion=instalacion, equipo=None, tipos=TIPOS_EQUIPO, manifolds=manifolds
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
        "equipos/form.html", instalacion=equipo.instalacion, equipo=equipo, tipos=TIPOS_EQUIPO, manifolds=manifolds
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

    por_tipo = {}
    for formulario in formularios:
        por_tipo.setdefault(formulario.tipo_formulario, []).append(formulario)

    secciones = []
    for tipo_formulario, lista in por_tipo.items():
        campos_numericos = []
        campos_otros = []
        for campo in tipo_formulario.campos():
            if campo["tipo"] == "numero":
                serie = _serie_numerica(lista, campo["campo"])
                puntos, minimo, maximo = _polilinea_svg(serie)
                campos_numericos.append(
                    {"label": campo["label"], "serie": serie, "puntos": puntos, "minimo": minimo, "maximo": maximo}
                )
            else:
                historial = [
                    (f.fecha_creacion, f.datos().get(campo["campo"])) for f in reversed(lista)
                ]
                campos_otros.append({"label": campo["label"], "historial": historial})
        secciones.append(
            {"tipo_formulario": tipo_formulario, "campos_numericos": campos_numericos, "campos_otros": campos_otros}
        )

    deficiencias_abiertas = [o for o in equipo.deficiencias if not o.resuelto]
    deficiencias_resueltas = [o for o in equipo.deficiencias if o.resuelto]

    return render_template(
        "equipos/detalle.html",
        equipo=equipo,
        secciones=secciones,
        deficiencias_abiertas=deficiencias_abiertas,
        deficiencias_resueltas=deficiencias_resueltas,
    )


def _serie_numerica(formularios, nombre_campo):
    """(fecha, valor) para un campo numérico, en orden cronológico,
    ignorando los formularios donde ese campo quedó vacío o no numérico."""
    serie = []
    for f in formularios:
        valor = f.datos().get(nombre_campo)
        try:
            valor_float = float(valor)
        except (TypeError, ValueError):
            continue
        serie.append((f.fecha_creacion.date(), valor_float))
    return serie


def _polilinea_svg(serie, ancho=520, alto=90, padding=12):
    """Puntos para un <polyline> de una gráfica simple, sin dependencias
    de JS: solo necesita al menos 2 valores numéricos para dibujar algo."""
    if len(serie) < 2:
        return None, None, None
    valores = [v for _, v in serie]
    minimo, maximo = min(valores), max(valores)
    rango = (maximo - minimo) or 1
    n = len(serie)
    puntos = []
    for i, (_, v) in enumerate(serie):
        x = padding + (ancho - 2 * padding) * (i / (n - 1))
        y = alto - padding - (alto - 2 * padding) * ((v - minimo) / rango)
        puntos.append(f"{x:.1f},{y:.1f}")
    return " ".join(puntos), minimo, maximo
