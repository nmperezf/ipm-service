from datetime import date

from dateutil.relativedelta import relativedelta
from flask import Blueprint, Response, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.orm import selectinload

from app import db
from app.auth_utils import (
    clientes_visibles,
    rol_requerido,
    tecnicos_de_la_empresa,
    verificar_acceso_cliente,
    verificar_password_confirmacion,
)
from app.models import (
    Cliente,
    Instalacion,
    ItemVisita,
    OrdenTrabajo,
    PRIORIDADES_OT,
    TIPOS_OT_MANUAL,
    Visita,
)
from app.notificaciones import notificar_gestion
from app.pdf_reporte_periodo import generar_pdf_reporte_periodo
from app.utils import es_ajax, parse_fecha

clientes_bp = Blueprint("clientes", __name__, url_prefix="/clientes")


@clientes_bp.route("/")
@rol_requerido("Administrador", "Jefe", "Técnico")
def listar():
    q = request.args.get("q", "").strip()
    # eager loading: deficiencias_abiertas() recorre instalaciones ->
    # deficiencias por cada cliente del listado — sin esto sería 1 query
    # por cliente más 1 por instalación (N+1).
    query = clientes_visibles().options(
        selectinload(Cliente.instalaciones).selectinload(Instalacion.deficiencias)
    )
    if q:
        query = query.filter(Cliente.nombre.ilike(f"%{q}%"))
    clientes = query.order_by(Cliente.nombre).all()
    clientes_con_criticas = sum(1 for c in clientes if c.deficiencias_abiertas()["Deficiencia crítica"])
    contexto = dict(clientes=clientes, q=q, clientes_con_criticas=clientes_con_criticas)
    template = "clientes/_contenido.html" if es_ajax() else "clientes/list.html"
    return render_template(template, **contexto)


@clientes_bp.route("/nuevo", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def nuevo():
    if request.method == "POST":
        cliente = Cliente(
            empresa_id=current_user.empresa_id,
            nombre=request.form["nombre"],
            direccion=request.form.get("direccion"),
            contacto=request.form.get("contacto"),
            telefono=request.form.get("telefono"),
            email=request.form.get("email"),
            observaciones=request.form.get("observaciones"),
            activo=bool(request.form.get("activo")),
        )
        db.session.add(cliente)
        db.session.commit()
        mensaje = f"Cliente '{cliente.nombre}' creado correctamente."
        if es_ajax():
            return jsonify(ok=True, mensaje=mensaje)
        flash(mensaje, "success")
        return redirect(url_for("clientes.listar"))
    template = "clientes/_form_fragment.html" if es_ajax() else "clientes/form.html"
    return render_template(template, cliente=None)


@clientes_bp.route("/visita-rapida", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe", "Técnico")
def visita_rapida():
    """Alta en una sola pantalla para un cliente que todavía no existe en
    el sistema (ej. visita a un prospecto sin contrato, para un servicio
    suelto/manual): crea Cliente + Instalación + Visita + OT en el mismo
    guardado, sin pasar por contrato. Queda todo cargado como registros
    reales (no un 'prospecto' aparte), para que si más adelante se le arma
    un contrato, ese historial de visita quede enganchado a la misma
    instalación.

    Abierta también a Técnico: verificar_escritura_cliente (que exige
    tener ya una OT asignada en ese cliente) no aplicaría acá porque el
    cliente todavía no existe para tener nada asignado."""
    tecnicos = tecnicos_de_la_empresa()
    if request.method == "POST":
        cliente = Cliente(
            empresa_id=current_user.empresa_id,
            nombre=request.form["nombre"],
            direccion=request.form.get("direccion"),
            contacto=request.form.get("contacto"),
            telefono=request.form.get("telefono"),
            email=request.form.get("email"),
            activo=True,
        )
        db.session.add(cliente)
        db.session.flush()

        instalacion = Instalacion(
            cliente_id=cliente.id,
            nombre=request.form.get("instalacion_nombre") or cliente.nombre,
            direccion=request.form.get("direccion"),
        )
        db.session.add(instalacion)
        db.session.flush()

        fecha = parse_fecha(request.form.get("fecha"), date.today(), silencioso=True)
        descripcion = request.form.get("descripcion")

        visita = Visita(
            instalacion_id=instalacion.id,
            fecha=fecha,
            observaciones=descripcion,
            estado="Pendiente",
        )
        db.session.add(visita)
        db.session.flush()

        tecnico_id = request.form.get("tecnico_id")
        if not tecnico_id and current_user.rol == "Técnico":
            tecnico_id = current_user.id

        ot = OrdenTrabajo(
            instalacion_id=instalacion.id,
            visita_id=visita.id,
            tipo=request.form.get("tipo") or "Visita técnica",
            prioridad=request.form.get("prioridad", "Media"),
            estado="Pendiente",
            tecnico_id=int(tecnico_id) if tecnico_id else None,
            descripcion=descripcion,
            fecha_apertura=fecha,
        )
        db.session.add(ot)
        db.session.flush()
        ot.asignar_numero()

        if current_user.rol == "Técnico":
            notificar_gestion(
                empresa_id=current_user.empresa_id,
                tipo="cliente_nuevo",
                titulo=f"Cliente nuevo registrado en campo — {cliente.nombre} ({ot.numero})",
                cliente_id=cliente.id,
                enlace=url_for("visitas.detalle", visita_id=visita.id),
                remitente=current_user,
            )

        db.session.commit()
        mensaje = f"Cliente '{cliente.nombre}' y visita {ot.numero} registrados."
        if es_ajax():
            return jsonify(ok=True, mensaje=mensaje)
        flash(mensaje, "success")
        return redirect(url_for("visitas.detalle", visita_id=visita.id))

    template = "clientes/_visita_rapida_fragment.html" if es_ajax() else "clientes/visita_rapida.html"
    return render_template(
        template,
        tipos=TIPOS_OT_MANUAL,
        prioridades=PRIORIDADES_OT,
        tecnicos=tecnicos,
        hoy=date.today().isoformat(),
    )


@clientes_bp.route("/<int:cliente_id>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def detalle(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    verificar_acceso_cliente(cliente)
    return render_template(
        "clientes/detail.html",
        cliente=cliente,
        indicadores=cliente.indicadores(),
        deficiencias=cliente.deficiencias_abiertas(),
        cumplido_anual_pct=cliente.cumplido_anual_pct(),
    )


@clientes_bp.route("/<int:cliente_id>/deficiencias/<clasificacion>")
@rol_requerido("Administrador", "Jefe", "Técnico")
def deficiencias(cliente_id, clasificacion):
    cliente = Cliente.query.get_or_404(cliente_id)
    verificar_acceso_cliente(cliente)
    observaciones = sorted(
        (
            o
            for inst in cliente.instalaciones
            for o in inst.deficiencias
            if not o.resuelto and o.clasificacion == clasificacion
        ),
        key=lambda o: o.fecha_carga,
        reverse=True,
    )
    return render_template(
        "clientes/deficiencias.html", cliente=cliente, observaciones=observaciones, clasificacion=clasificacion
    )


@clientes_bp.route("/<int:cliente_id>/reporte-periodo")
@rol_requerido("Administrador", "Jefe")
def reporte_periodo(cliente_id):
    """Reporte de cumplimiento por período (pensado para 6 meses, pero
    acepta cualquier rango): servicios ejecutados + deficiencias
    encontradas en el período + todas las que siguen abiertas hoy
    (críticas primero). Es lo que un cliente necesita para su propia
    auditoría interna."""
    cliente = Cliente.query.get_or_404(cliente_id)
    verificar_acceso_cliente(cliente)

    hoy = date.today()
    fecha_desde = parse_fecha(request.args.get("fecha_desde"), hoy - relativedelta(months=6), silencioso=True)
    fecha_hasta = parse_fecha(request.args.get("fecha_hasta"), hoy, silencioso=True)

    ids_instalaciones = [i.id for i in cliente.instalaciones]

    items_periodo = (
        ItemVisita.query.join(Visita)
        .filter(
            Visita.instalacion_id.in_(ids_instalaciones),
            Visita.fecha >= fecha_desde,
            Visita.fecha <= fecha_hasta,
        )
        .all()
        if ids_instalaciones
        else []
    )
    resumen_servicios = []
    for inst in cliente.instalaciones:
        items_inst = [it for it in items_periodo if it.visita.instalacion_id == inst.id]
        if not items_inst:
            continue
        cumplidos = sum(1 for it in items_inst if it.estado == "Cumplido")
        resumen_servicios.append(
            {
                "instalacion": inst.nombre,
                "total": len(items_inst),
                "cumplidos": cumplidos,
                "pendientes": sum(1 for it in items_inst if it.estado == "Pendiente"),
                "cancelados": sum(1 for it in items_inst if it.estado == "Cancelado"),
                "pct": round(cumplidos / len(items_inst) * 100, 1),
            }
        )

    deficiencias_periodo = sorted(
        (
            o
            for inst in cliente.instalaciones
            for o in inst.deficiencias
            if fecha_desde <= o.fecha_carga <= fecha_hasta
        ),
        key=lambda o: (o.clasificacion != "Deficiencia crítica", o.fecha_carga),
    )

    deficiencias_abiertas = sorted(
        (o for inst in cliente.instalaciones for o in inst.deficiencias if not o.resuelto),
        key=lambda o: (o.clasificacion != "Deficiencia crítica", -(hoy - o.fecha_carga).days),
    )
    for o in deficiencias_abiertas:
        o.dias_abierta = (hoy - o.fecha_carga).days

    if request.args.get("pdf"):
        pdf_bytes = generar_pdf_reporte_periodo(
            cliente, fecha_desde, fecha_hasta, resumen_servicios, deficiencias_periodo, deficiencias_abiertas
        )
        nombre_archivo = f"Reporte_{cliente.nombre.replace(' ', '_')}_{fecha_desde}_{fecha_hasta}.pdf"
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": f"inline; filename={nombre_archivo}"},
        )

    return render_template(
        "clientes/reporte_periodo.html",
        cliente=cliente,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        resumen_servicios=resumen_servicios,
        deficiencias_periodo=deficiencias_periodo,
        deficiencias_abiertas=deficiencias_abiertas,
    )


@clientes_bp.route("/<int:cliente_id>/editar", methods=["GET", "POST"])
@rol_requerido("Administrador", "Jefe")
def editar(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    verificar_acceso_cliente(cliente)
    if request.method == "POST":
        cliente.nombre = request.form["nombre"]
        cliente.direccion = request.form.get("direccion")
        cliente.contacto = request.form.get("contacto")
        cliente.telefono = request.form.get("telefono")
        cliente.email = request.form.get("email")
        cliente.observaciones = request.form.get("observaciones")
        cliente.activo = bool(request.form.get("activo"))
        db.session.commit()
        mensaje = f"Cliente '{cliente.nombre}' actualizado."
        if es_ajax():
            return jsonify(ok=True, mensaje=mensaje)
        flash(mensaje, "success")
        return redirect(url_for("clientes.detalle", cliente_id=cliente.id))
    template = "clientes/_form_fragment.html" if es_ajax() else "clientes/form.html"
    return render_template(template, cliente=cliente)


@clientes_bp.route("/<int:cliente_id>/eliminar", methods=["POST"])
@rol_requerido("Administrador", "Jefe")
def eliminar(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    verificar_acceso_cliente(cliente)
    if not verificar_password_confirmacion():
        return redirect(url_for("clientes.detalle", cliente_id=cliente.id))
    db.session.delete(cliente)
    db.session.commit()
    flash(f"Cliente '{cliente.nombre}' eliminado.", "info")
    return redirect(url_for("clientes.listar"))
