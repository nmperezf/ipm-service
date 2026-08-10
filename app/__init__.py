import json
import random
from datetime import date, datetime, timedelta

from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Iniciá sesión para continuar."
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import Usuario

        return Usuario.query.get(int(user_id))

    @app.before_request
    def exigir_login():
        from flask import redirect, request, url_for
        from flask_login import current_user

        # Rutas que quedan afuera del login obligatorio
        endpoints_publicos = {"auth.login", "static"}
        if request.endpoint in endpoints_publicos or request.endpoint is None:
            return None
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.path))
        return None

    @app.context_processor
    def inyectar_notificaciones_no_leidas():
        from flask_login import current_user

        from app.models import Notificacion

        if not current_user.is_authenticated:
            return {}
        return {
            "notificaciones_no_leidas": Notificacion.query.filter_by(
                destinatario_id=current_user.id, leido=False
            ).count()
        }

    @app.context_processor
    def inyectar_tipos_bomba_principal():
        # Varios templates necesitan distinguir bombas principales (con
        # curva de caudal) del resto de los equipos — antes cada uno
        # hardcodeaba su propia tupla ('Bomba', 'Electrobomba', 'Motobomba'),
        # con riesgo de desincronizarse de la constante real si esta cambia.
        from app.models import TIPOS_BOMBA_PRINCIPAL

        return {"TIPOS_BOMBA_PRINCIPAL": TIPOS_BOMBA_PRINCIPAL}

    @app.context_processor
    def inyectar_estados_checklist():
        from app.models import ESTADOS_CHECKLIST, ESTADOS_CHECKLIST_LABEL

        return {"ESTADOS_CHECKLIST": ESTADOS_CHECKLIST, "ESTADOS_CHECKLIST_LABEL": ESTADOS_CHECKLIST_LABEL}

    # Registro de blueprints (cada módulo queda desacoplado del resto)
    from app.routes.auth import auth_bp
    from app.routes.clientes import clientes_bp
    from app.routes.instalaciones import instalaciones_bp
    from app.routes.equipos import equipos_bp
    from app.routes.tipos_equipo import tipos_equipo_bp
    from app.routes.contratos import contratos_bp
    from app.routes.visitas import visitas_bp
    from app.routes.formularios import formularios_bp
    from app.routes.fotos import fotos_bp
    from app.routes.historial import historial_bp
    from app.routes.observaciones import observaciones_bp
    from app.routes.presupuestos import presupuestos_bp
    from app.routes.planificacion import planificacion_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.ordenes_trabajo import ordenes_bp
    from app.routes.inventario import inventario_bp
    from app.routes.mensajes import mensajes_bp
    from app.routes.notificaciones import notificaciones_bp
    from app.routes.tipos_formulario import tipos_formulario_bp
    from app.routes.empresas import empresas_bp
    from app.routes.usuarios import usuarios_bp
    from app.routes.portal import portal_bp
    from app.routes.servicios_tipo import servicios_tipo_bp
    from app.routes.curvas import curvas_bp
    from app.routes.coordinacion import coordinacion_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(clientes_bp)
    app.register_blueprint(instalaciones_bp)
    app.register_blueprint(equipos_bp)
    app.register_blueprint(tipos_equipo_bp)
    app.register_blueprint(contratos_bp)
    app.register_blueprint(visitas_bp)
    app.register_blueprint(formularios_bp)
    app.register_blueprint(fotos_bp)
    app.register_blueprint(historial_bp)
    app.register_blueprint(observaciones_bp)
    app.register_blueprint(presupuestos_bp)
    app.register_blueprint(planificacion_bp)
    app.register_blueprint(ordenes_bp)
    app.register_blueprint(inventario_bp)
    app.register_blueprint(mensajes_bp)
    app.register_blueprint(notificaciones_bp)
    app.register_blueprint(tipos_formulario_bp)
    app.register_blueprint(empresas_bp)
    app.register_blueprint(usuarios_bp)
    app.register_blueprint(portal_bp)
    app.register_blueprint(servicios_tipo_bp)
    app.register_blueprint(curvas_bp)
    app.register_blueprint(coordinacion_bp)

    with app.app_context():
        db.create_all()
        _migrar_columnas_faltantes()
        _seed_super_admin()
        _seed_tipos_equipo()
        _seed_clientes_demo()

    return app


def _migrar_columnas_faltantes():
    """Alta de columnas nuevas en tablas ya existentes -- sin Alembic,
    db.create_all() no las agrega solo a una tabla que ya existía. Cada
    entrada se agrega con ALTER TABLE si todavía no está (sirve tanto
    para SQLite local como para Postgres en producción)."""
    from sqlalchemy import inspect, text

    columnas_nuevas = [
        ("tipos_formulario", "referencia_normativa", "VARCHAR(200)"),
        ("tipos_formulario", "orden", "INTEGER DEFAULT 0"),
    ]
    inspector = inspect(db.engine)
    tablas_existentes = set(inspector.get_table_names())
    cambio = False
    for tabla, columna, tipo_sql in columnas_nuevas:
        if tabla not in tablas_existentes:
            continue
        columnas_existentes = {c["name"] for c in inspector.get_columns(tabla)}
        if columna not in columnas_existentes:
            db.session.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo_sql}"))
            cambio = True
    if cambio:
        db.session.commit()


def _seed_super_admin():
    """Si todavía no existe ningún usuario, crea un Super Admin por
    defecto — sin esto, un instalación nueva no tendría con qué iniciar
    sesión la primera vez. Cambiar la contraseña apenas se entra."""
    from app.models import Usuario

    if Usuario.query.first():
        return

    admin = Usuario(username="admin", nombre_completo="Super Administrador", rol="Super Admin")
    admin.set_password("admin123")
    db.session.add(admin)
    db.session.commit()
    print("Usuario Super Admin creado por defecto -> usuario: admin / contraseña: admin123 (cambiala)")


def _seed_tipos_equipo():
    """Carga el catálogo base de tipos de equipo la primera vez que se
    levanta la app. De ahí en más, los tipos nuevos se agregan a mano
    desde la pantalla de Tipos de equipo."""
    from app.models import TipoEquipo

    if TipoEquipo.query.first():
        return

    base = [
        ("ECA", "Estaciones de control y alarma"),
        ("Manifold", "Estaciones de control y alarma"),
        ("Bomba", "Sala de bombas"),
        ("Electrobomba", "Sala de bombas"),
        ("Motobomba", "Sala de bombas"),
        ("Bomba jockey", "Sala de bombas"),
        ("Reserva de agua", "Sala de bombas"),
        ("BIE", "Bocas de incendio"),
        ("Otro", "Otros equipos"),
    ]
    for nombre, categoria in base:
        db.session.add(TipoEquipo(nombre=nombre, categoria=categoria))
    db.session.commit()


def _seed_clientes_demo():
    """Carga 10 clientes de ejemplo (con instalaciones, equipos, contratos,
    hoja de ruta e historial de checklists) para que nmperezf pueda probar
    la app con datos realistas -- se corre en cada arranque pero cada
    cliente se crea una sola vez (se salta si ya existe por nombre)."""
    from app.models import (
        Cliente, Contrato, Equipo, Formulario, Instalacion, ItemVisita,
        Observacion, OrdenTrabajo, Presupuesto, ServicioContrato,
        TipoFormulario, Usuario, Visita,
    )

    ref = Usuario.query.filter_by(username="nmperezf").first()
    if not ref:
        return
    empresa_id = ref.empresa_id
    hoy = date.today()
    rng = random.Random(42)

    perfiles = {
        "chico": {"bombas": 2, "eca": 2, "bie": 3, "otros": 2},
        "mediano": {"bombas": 3, "eca": 5, "bie": 8, "otros": 3},
        "grande": {"bombas": 4, "eca": 12, "bie": 15, "otros": 5},
    }

    clientes_demo = [
        {"nombre": "Frigorifico del Norte SA", "contacto": "Martin Silveira", "telefono": "099123001",
         "instalaciones": [("Planta Salto", "Ruta 3 km 480, Salto", "grande", 28)]},
        {"nombre": "Supermercados La Emilia", "contacto": "Cecilia Bordon", "telefono": "099123002",
         "instalaciones": [("Sucursal Pocitos", "Av. Brasil 2450, Montevideo", "mediano", None),
                           ("Sucursal Carrasco", "Av. Arocena 1620, Montevideo", "mediano", None)]},
        {"nombre": "Hotel Costa Azul", "contacto": "Rodrigo Farias", "telefono": "099123003",
         "instalaciones": [("Hotel Costa Azul", "Parada 8, Punta del Este", "mediano", None)]},
        {"nombre": "Textil Uruguaya SA", "contacto": "Lucia Perez", "telefono": "099123004",
         "instalaciones": [("Planta Textil", "Camino Maldonado 5200, Montevideo", "chico", None)]},
        {"nombre": "Shopping Nuevocentro", "contacto": "Andres Bianchi", "telefono": "099123005",
         "instalaciones": [("Shopping Nuevocentro", "Bulevar Artigas 1250, Montevideo", "grande", None)]},
        {"nombre": "Bodega Los Cerros", "contacto": "Valentina Suarez", "telefono": "099123006",
         "instalaciones": [("Bodega Los Cerros", "Ruta 74 km 12, Canelones", "chico", None)]},
        {"nombre": "Laboratorios Salud SA", "contacto": "Diego Ramallo", "telefono": "099123007",
         "instalaciones": [("Planta Laboratorios", "Camino Carrasco 4300, Montevideo", "mediano", None)]},
        {"nombre": "Deposito Logistico Sur", "contacto": "Natalia Correa", "telefono": "099123008",
         "instalaciones": [("Deposito Sur", "Ruta 5 km 22, Canelones", "chico", None)]},
        {"nombre": "Colegio San Martin", "contacto": "Beatriz Nunez", "telefono": "099123009",
         "instalaciones": [("Colegio San Martin", "Bulevar España 2100, Montevideo", "chico", None)]},
        {"nombre": "Planta Quimica Andina", "contacto": "Federico Acosta", "telefono": "099123010",
         "instalaciones": [("Planta Quimica", "Camino Cibils 3400, Montevideo", "mediano", None)]},
    ]

    def crear_tipos_formulario(cliente):
        t_bomba = TipoFormulario(
            cliente_id=cliente.id, nombre="Inspeccion mensual bomba", por_equipo=True,
            schema_json=json.dumps([
                {"campo": "presion_descarga", "label": "Presion descarga", "tipo": "numero"},
                {"campo": "presion_succion", "label": "Presion succion", "tipo": "numero"},
                {"campo": "rpm", "label": "RPM", "tipo": "numero"},
                {"campo": "estado", "label": "Estado general", "tipo": "texto"},
            ]),
        )
        t_eca = TipoFormulario(
            cliente_id=cliente.id, nombre="Inspeccion mensual ECA", por_equipo=True,
            tipo_equipo_aplicable="ECA",
            schema_json=json.dumps([
                {"campo": "voltaje", "label": "Voltaje bateria", "tipo": "numero"},
                {"campo": "zona", "label": "Estado zona", "tipo": "texto"},
            ]),
        )
        t_bie = TipoFormulario(
            cliente_id=cliente.id, nombre="Inspeccion mensual BIE", por_equipo=True,
            tipo_equipo_aplicable="BIE",
            schema_json=json.dumps([
                {"campo": "presion", "label": "Presion manometro", "tipo": "numero"},
                {"campo": "manguera", "label": "Estado manguera", "tipo": "texto"},
            ]),
        )
        db.session.add_all([t_bomba, t_eca, t_bie])
        db.session.flush()
        return t_bomba, t_eca, t_bie

    def crear_equipos(inst, perfil, n_eca_override):
        p = perfiles[perfil]
        equipos = {"bomba": [], "eca": [], "bie": [], "otro": []}
        nombres_bomba = ["Bomba principal", "Bomba jockey", "Bomba reserva", "Bomba auxiliar"]
        for i in range(p["bombas"]):
            tipo = "Bomba" if i == 0 else ("Bomba jockey" if i == 1 else "Electrobomba")
            e = Equipo(instalacion_id=inst.id, nombre=nombres_bomba[i % len(nombres_bomba)] + (f" {i+1}" if i >= len(nombres_bomba) else ""),
                      tipo=tipo, ubicacion="Sala de bombas")
            db.session.add(e)
            equipos["bomba"].append(e)
        n_eca = n_eca_override or p["eca"]
        for i in range(n_eca):
            e = Equipo(instalacion_id=inst.id, nombre=f"ECA Sector {chr(65 + i % 26)}{i // 26 or ''}",
                      tipo="ECA", ubicacion=f"Sector {chr(65 + i % 26)}")
            db.session.add(e)
            equipos["eca"].append(e)
        for i in range(p["bie"]):
            e = Equipo(instalacion_id=inst.id, nombre=f"BIE {i+1}", tipo="BIE", ubicacion=f"Planta, punto {i+1}")
            db.session.add(e)
            equipos["bie"].append(e)
        for i in range(p["otros"]):
            e = Equipo(instalacion_id=inst.id, nombre=f"Extintor {i+1}", tipo="Otro", ubicacion=f"Pasillo {i+1}")
            db.session.add(e)
            equipos["otro"].append(e)
        db.session.flush()
        return equipos

    def datos_bomba(base):
        return {"presion_descarga": round(base + rng.uniform(-4, 4), 0),
                "presion_succion": round(base * 0.15 + rng.uniform(-1, 1), 0),
                "rpm": 1770 + rng.choice([-5, 0, 0, 5]),
                "estado": rng.choice(["OK", "OK", "OK", "Revisar"])}

    def datos_eca():
        return {"voltaje": round(13.2 + rng.uniform(-0.3, 0.4), 1), "zona": "OK"}

    def datos_bie():
        return {"presion": round(90 + rng.uniform(-10, 10), 0), "manguera": rng.choice(["OK", "OK", "Cambiar"])}

    for cdata in clientes_demo:
        if Cliente.query.filter_by(nombre=cdata["nombre"]).first():
            continue
        cliente = Cliente(empresa_id=empresa_id, nombre=cdata["nombre"], contacto=cdata["contacto"],
                          telefono=cdata["telefono"], activo=True)
        db.session.add(cliente)
        db.session.flush()

        t_bomba, t_eca, t_bie = crear_tipos_formulario(cliente)

        for idx_inst, (nombre_inst, direccion, perfil, n_eca_override) in enumerate(cdata["instalaciones"]):
            inst = Instalacion(cliente_id=cliente.id, nombre=nombre_inst, direccion=direccion)
            db.session.add(inst)
            db.session.flush()

            equipos = crear_equipos(inst, perfil, n_eca_override)

            contrato = Contrato(instalacion_id=inst.id, nombre=f"Contrato anual {hoy.year}",
                                fecha_inicio=hoy - timedelta(days=200), fecha_fin=hoy + timedelta(days=165),
                                estado="Activo", activo=True)
            db.session.add(contrato)
            db.session.flush()
            servicio = ServicioContrato(contrato_id=contrato.id, nombre="Mantenimiento preventivo mensual", frecuencia="mensual")
            db.session.add(servicio)
            db.session.flush()

            muestra_bomba = equipos["bomba"][:2]
            muestra_eca = equipos["eca"][:2]
            muestra_bie = equipos["bie"][:2]

            for dias_atras in (75, 45, 15):
                fecha_v = hoy - timedelta(days=dias_atras)
                v = Visita(instalacion_id=inst.id, contrato_id=contrato.id, fecha=fecha_v,
                          tecnico="Diego Fernandez", estado="Realizado", cerrada=True, fecha_cierre=fecha_v)
                db.session.add(v)
                db.session.flush()
                ot = OrdenTrabajo(instalacion_id=inst.id, visita_id=v.id, tipo="Preventivo", prioridad="Media",
                                  estado="Finalizada", fecha_apertura=fecha_v, fecha_cierre=fecha_v)
                db.session.add(ot)
                db.session.flush()
                ot.asignar_numero()
                item = ItemVisita(visita_id=v.id, servicio_contrato_id=servicio.id, estado="Cumplido")
                db.session.add(item)
                db.session.flush()

                for eq in muestra_bomba:
                    f = Formulario(item_visita_id=item.id, tipo_formulario_id=t_bomba.id, equipo_id=eq.id,
                                   fecha_creacion=datetime.combine(fecha_v, datetime.min.time()))
                    f.set_datos(datos_bomba(118))
                    db.session.add(f)
                for eq in muestra_eca:
                    f = Formulario(item_visita_id=item.id, tipo_formulario_id=t_eca.id, equipo_id=eq.id,
                                   fecha_creacion=datetime.combine(fecha_v, datetime.min.time()))
                    f.set_datos(datos_eca())
                    db.session.add(f)
                for eq in muestra_bie:
                    f = Formulario(item_visita_id=item.id, tipo_formulario_id=t_bie.id, equipo_id=eq.id,
                                   fecha_creacion=datetime.combine(fecha_v, datetime.min.time()))
                    f.set_datos(datos_bie())
                    db.session.add(f)

            for dias_adelante in (10, 35):
                fecha_v = hoy + timedelta(days=dias_adelante)
                v = Visita(instalacion_id=inst.id, contrato_id=contrato.id, fecha=fecha_v,
                          tecnico="Diego Fernandez", estado="Pendiente")
                db.session.add(v)

            if rng.random() < 0.5 and muestra_bie:
                obs = Observacion(instalacion_id=inst.id, equipo_id=muestra_bie[0].id,
                                  clasificacion=rng.choice(["Deficiencia crítica", "Deficiencia no crítica"]),
                                  descripcion="Manguera con desgaste visible, evaluar cambio.",
                                  fecha_carga=hoy - timedelta(days=10), resuelto=False,
                                  estado_revision="Aprobada", requiere_presupuesto=True)
                db.session.add(obs)
                db.session.flush()
                presu = Presupuesto(codigo=f"PRESUP-{hoy.year}-{1000 + cliente.id * 10 + idx_inst}",
                                    empresa_id=empresa_id, observacion_id=obs.id, estado="Pendiente")
                db.session.add(presu)

        db.session.commit()

