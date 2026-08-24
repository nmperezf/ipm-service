from collections import defaultdict
from datetime import date

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

from app import db
from app.auth_utils import (
    rol_requerido,
    verificar_acceso_cliente,
    verificar_escritura_cliente,
    verificar_password_confirmacion,
)
from app.models import Cliente, Formulario, Instalacion
from app.utils import equipos_por_categoria, es_ajax, filas_checklist

instalaciones_bp = Blueprint("instalaciones", __name__, url_prefix="/instalaciones")

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


@instalaciones_bp.route("/nueva/<int:cliente_id>", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def nueva(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    verificar_escritura_cliente(cliente)
    if request.method == "POST":
        instalacion = Instalacion(
            cliente_id=cliente.id,
            nombre=request.form["nombre"],
            direccion=request.form.get("direccion"),
            observaciones=request.form.get("observaciones"),
            aseguradora=request.form.get("aseguradora", "").strip() or None,
            numero_poliza=request.form.get("numero_poliza", "").strip() or None,
            tag_sala_bombas=request.form.get("tag_sala_bombas", "").strip() or None,
        )
        db.session.add(instalacion)
        db.session.commit()
        mensaje = f"Instalación '{instalacion.nombre}' creada."
        if es_ajax():
            return jsonify(ok=True, mensaje=mensaje)
        flash(mensaje, "success")
        return redirect(url_for("clientes.detalle", cliente_id=cliente.id))
    template = "instalaciones/_form_fragment.html" if es_ajax() else "instalaciones/form.html"
    return render_template(template, cliente=cliente, instalacion=None)


@instalaciones_bp.route("/<int:instalacion_id>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def detalle(instalacion_id):
    """Ficha de la instalación: equipos agrupados por categoría (antes una
    pantalla aparte, "Información de instalación"), observaciones
    abiertas, contratos y su hoja de ruta (todas las visitas, cumplidas y
    pendientes/futuras, agrupadas por mes — antes solo existía a nivel
    cliente mezclando todas sus instalaciones)."""
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_acceso_cliente(instalacion.cliente)
    contratos = sorted(instalacion.contratos, key=lambda c: c.fecha_inicio, reverse=True)
    categorias = equipos_por_categoria(instalacion)

    agrupado = defaultdict(list)
    for v in instalacion.visitas:
        agrupado[(v.fecha.year, v.fecha.month)].append(v)
    meses_ordenados = sorted(agrupado.keys(), reverse=True)
    bloques_hoja_ruta = [
        {
            "titulo": f"{MESES_ES[mes - 1]} {anio}",
            "visitas": sorted(agrupado[(anio, mes)], key=lambda v: v.fecha, reverse=True),
        }
        for (anio, mes) in meses_ordenados
    ]

    # Resumen de un vistazo para la cabecera compacta -- evita que el
    # técnico/administrador tenga que recorrer toda la ficha para saber si
    # hay algo pendiente antes de entrar a mirar el detalle.
    hoy = date.today()
    proxima_visita = min(
        (v for v in instalacion.visitas if v.fecha >= hoy and v.estado != "Cancelado"),
        key=lambda v: v.fecha,
        default=None,
    )
    observaciones_abiertas = sorted(
        (o for o in instalacion.deficiencias if not o.resuelto),
        key=lambda o: (o.clasificacion != "Deficiencia crítica", o.fecha_carga),
    )
    observaciones_anteriores = sorted(
        (o for o in instalacion.deficiencias if o.resuelto),
        key=lambda o: o.fecha_resolucion or o.fecha_carga,
        reverse=True,
    )

    contexto = dict(
        instalacion=instalacion,
        contratos=contratos,
        categorias=categorias,
        bloques_hoja_ruta=bloques_hoja_ruta,
        total_equipos=sum(len(equipos_cat) for _, equipos_cat in categorias),
        contratos_activos=sum(1 for c in contratos if c.estado == "Activo"),
        proxima_visita=proxima_visita,
        observaciones_abiertas=observaciones_abiertas,
        observaciones_anteriores=observaciones_anteriores,
    )
    template = "instalaciones/_contenido.html" if es_ajax() else "instalaciones/detail.html"
    return render_template(template, **contexto)


@instalaciones_bp.route("/<int:instalacion_id>/fotos")
@rol_requerido("Administrador", "Jefe", "Técnico")
def fotos(instalacion_id):
    """Banco de fotos de toda la instalación en una sola tabla (buscable y
    ordenable por columna vía tablas.js) — las fichas de cada equipo
    siguen mostrando su propio mini-grid para contexto rápido, esta
    pantalla es para revisar/auditar todo junto."""
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_acceso_cliente(instalacion.cliente)
    fotos_ordenadas = sorted(
        instalacion.fotos, key=lambda f: f.fecha_toma or f.fecha_subida.date(), reverse=True
    )
    return render_template("instalaciones/fotos.html", instalacion=instalacion, fotos=fotos_ordenadas)


@instalaciones_bp.route("/<int:instalacion_id>/equipos")
@rol_requerido("Administrador", "Jefe", "Técnico")
def equipos_lista(instalacion_id):
    """Categorías de equipos (Bomba/ECA/BIE) de la instalación, cada una
    con su cantidad -- entrada a instalaciones.equipos_categoria."""
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_acceso_cliente(instalacion.cliente)
    categorias = equipos_por_categoria(instalacion)
    return render_template("instalaciones/equipos_lista.html", instalacion=instalacion, categorias=categorias)


@instalaciones_bp.route("/<int:instalacion_id>/informacion/<categoria>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def equipos_categoria(instalacion_id, categoria):
    """Listado liviano de los equipos de una categoría (nombre, ubicación
    y, para bombas, el estado NFPA 25 de su último ensayo). El preview de
    cada equipo (mismo modal de siempre: deficiencias, última actividad,
    fotos) ahora suma su histórico de checklists — una tabla por tipo,
    una fila por carga — para no tener que entrar a la ficha completa
    solo para ver qué se cargó."""
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_acceso_cliente(instalacion.cliente)

    grupos = dict(equipos_por_categoria(instalacion))
    if categoria not in grupos:
        abort(404)
    equipos = grupos[categoria]

    grupos_checklist_por_equipo = {}
    for equipo in equipos:
        formularios = Formulario.query.filter_by(equipo_id=equipo.id).order_by(Formulario.fecha_creacion).all()
        grupos_checklist_por_equipo[equipo.id] = filas_checklist(formularios)

    return render_template(
        "instalaciones/equipos_categoria.html",
        instalacion=instalacion,
        categoria=categoria,
        equipos=equipos,
        grupos_checklist_por_equipo=grupos_checklist_por_equipo,
    )


@instalaciones_bp.route("/<int:instalacion_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def editar(instalacion_id):
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_escritura_cliente(instalacion.cliente)
    if request.method == "POST":
        instalacion.nombre = request.form["nombre"]
        instalacion.direccion = request.form.get("direccion")
        instalacion.observaciones = request.form.get("observaciones")
        instalacion.aseguradora = request.form.get("aseguradora", "").strip() or None
        instalacion.numero_poliza = request.form.get("numero_poliza", "").strip() or None
        instalacion.tag_sala_bombas = request.form.get("tag_sala_bombas", "").strip() or None
        db.session.commit()
        mensaje = f"Instalación '{instalacion.nombre}' actualizada."
        if es_ajax():
            return jsonify(ok=True, mensaje=mensaje)
        flash(mensaje, "success")
        return redirect(url_for("instalaciones.detalle", instalacion_id=instalacion.id))
    template = "instalaciones/_form_fragment.html" if es_ajax() else "instalaciones/form.html"
    return render_template(template, cliente=instalacion.cliente, instalacion=instalacion)


@instalaciones_bp.route("/<int:instalacion_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def eliminar(instalacion_id):
    instalacion = Instalacion.query.get_or_404(instalacion_id)
    verificar_escritura_cliente(instalacion.cliente)
    if not verificar_password_confirmacion():
        return redirect(url_for("instalaciones.detalle", instalacion_id=instalacion.id))
    cliente_id = instalacion.cliente_id
    db.session.delete(instalacion)
    db.session.commit()
    flash(f"Instalación '{instalacion.nombre}' eliminada.", "info")
    return redirect(url_for("clientes.detalle", cliente_id=cliente_id))
