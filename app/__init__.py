import json
import secrets

from flask import Flask, abort, g, render_template, request, session
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import OperationalError, ProgrammingError

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object("app.config.Config")
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("SECRET_KEY debe estar configurada antes de iniciar la aplicación")

    @app.context_processor
    def inyectar_csrf():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return {"csrf_token": session["csrf_token"]}

    @app.before_request
    def proteger_csrf():
        if not app.config["CSRF_ENABLED"] or request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None
        token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not token or token != session.get("csrf_token"):
            abort(400, description="Token CSRF inválido o ausente")
        return None

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Iniciá sesión para continuar."
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import Usuario

        return db.session.get(Usuario, int(user_id))

    @app.before_request
    def exigir_login():
        from flask import redirect, request, url_for
        from flask_login import current_user

        # Rutas que quedan afuera del login obligatorio
        endpoints_publicos = {"auth.login", "static"}
        if request.endpoint == "static" and request.path.startswith("/static/uploads/"):
            abort(404)
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

    @app.after_request
    def enviar_pushes_pendientes(response):
        # notificar_usuario/notificar_gestion (app/notificaciones.py) dejan
        # acá qué grupos (destinatario, tipo, cliente) recibieron una
        # Notificacion nueva durante este request. Para cuando llegamos acá,
        # la vista ya hizo su propio db.session.commit() -- recién ahí tiene
        # sentido mandar el push (si hubo rollback, enviar_push_agrupado no
        # encuentra nada y no manda nada).
        pendientes = getattr(g, "_push_pendientes", None)
        if pendientes:
            from app.push import enviar_push_agrupado

            for destinatario_id, tipo, cliente_id in set(pendientes):
                enviar_push_agrupado(destinatario_id, tipo, cliente_id)
        return response

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
    from app.routes.documentos import documentos_bp
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
    from app.routes.busqueda import busqueda_bp
    from app.routes.push import push_bp
    from app.routes.bie import bie_bp
    from app.routes.mangueras import mangueras_bp

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
    app.register_blueprint(documentos_bp)
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
    app.register_blueprint(busqueda_bp)
    app.register_blueprint(push_bp)
    app.register_blueprint(bie_bp)
    app.register_blueprint(mangueras_bp)

    @app.errorhandler(404)
    def error_404(error):
        return render_template("errores/404.html"), 404

    @app.errorhandler(500)
    def error_500(error):
        # Una excepción no controlada puede dejar la sesión de SQLAlchemy en
        # un estado inconsistente — sin este rollback, la próxima query de
        # esta misma request (ej. el context_processor de notificaciones al
        # renderizar la página de error) fallaría también.
        db.session.rollback()
        return render_template("errores/500.html"), 500

    with app.app_context():
        try:
            _seed_super_admin()
            _seed_tipos_equipo()
            _seed_catalogo_nfpa()
        except (OperationalError, ProgrammingError):
            # El esquema todavía no está al día (falta correr "flask db
            # upgrade") — pasa la primera vez que se clona el repo, durante
            # los comandos "flask db init/migrate", y en release.py (que
            # llama a create_app() ANTES de aplicar las migraciones). Se
            # resuelve solo en el próximo arranque, una vez aplicadas.
            # SQLite tira OperationalError tanto para tabla como columna
            # faltante; Postgres tira esa misma OperationalError para tabla
            # faltante pero ProgrammingError (UndefinedColumn) para columna
            # faltante -- sin este segundo tipo, un modelo con una columna
            # nueva todavía no migrada tira acá un 500 crudo en vez de
            # resolverse solo (pasó con matricula_profesional en Postgres:
            # ni release.py ni verificar_schema.py llegaban a correr).
            db.session.rollback()

    return app


def verificar_schema_al_dia():
    """Compara la revisión de Alembic aplicada en la base contra el head de
    migrations/ -- si no coinciden, tira RuntimeError. Requiere un contexto
    de app activo (usa db.engine).

    Existe porque el 14/08/2026 la migración de "visibilidad" nunca se
    aplicó en producción (la fase "release" de Railway venía fallando en
    silencio) y la app siguió sirviendo tráfico igual, con el schema viejo,
    hasta que una query pisó la columna que faltaba y tiró 500 al azar para
    los usuarios. Preferible un deploy visiblemente caído a ese silencio.

    A propósito NO se llama desde create_app(): tanto release.py (que es
    justamente el que aplica las migraciones) como los tests pasan por
    create_app() sin haber corrido Alembic todavía (los tests arman el
    esquema con db.create_all(), no con migraciones). Se llama explícitamente
    desde verificar_schema.py, un paso aparte antes de levantar gunicorn
    (ver Procfile) -- y desde run.py para pegar el mismo chequeo en local."""
    import os

    from alembic.config import Config as AlembicConfig
    from alembic.script import ScriptDirectory

    migrations_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")
    alembic_cfg = AlembicConfig()
    alembic_cfg.set_main_option("script_location", migrations_dir)
    heads_esperados = set(ScriptDirectory.from_config(alembic_cfg).get_heads())

    from sqlalchemy import text

    with db.engine.connect() as conn:
        try:
            heads_actuales = {fila[0] for fila in conn.execute(text("SELECT version_num FROM alembic_version"))}
        except Exception:
            heads_actuales = set()

    if heads_actuales != heads_esperados:
        raise RuntimeError(
            "La base de datos no está al día con las migraciones "
            f"(aplicado: {heads_actuales or 'ninguna'} / esperado: {heads_esperados}). "
            "Corré 'python release.py' antes de levantar la app -- ver Procfile."
        )


def _seed_super_admin():
    """Si todavía no existe ningún usuario, crea un Super Admin por
    defecto — sin esto, un instalación nueva no tendría con qué iniciar
    sesión la primera vez. Cambiar la contraseña apenas se entra."""
    from app.models import Usuario

    if Usuario.query.first():
        return

    import os

    password = os.environ.get("INITIAL_ADMIN_PASSWORD")
    if not password:
        print("No se creó el Super Admin inicial: configurá INITIAL_ADMIN_PASSWORD para el primer arranque.")
        return

    admin = Usuario(username=os.environ.get("INITIAL_ADMIN_USERNAME", "admin"), nombre_completo="Super Administrador", rol="Super Admin")
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    print(f"Usuario Super Admin inicial creado -> usuario: {admin.username}")


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


def _seed_catalogo_nfpa():
    """Catálogo de checklists de inspección NFPA 25 (con estado por punto:
    Conforme/Observado/Deficiencia/N-A) para sala de bombas, ECA y BIE --
    se arma una vez por empresa; cada cliente los importa desde acá (ver
    TipoFormulario.desde_catalogo) en vez de tener que armarlos a mano.
    Las referencias de norma/sección son orientativas -- conviene
    verificarlas contra la edición de NFPA 25 realmente adoptada antes de
    usarlas en un documento de cumplimiento."""
    from app.models import Cliente, Empresa, ServicioTipo, TipoFormulario

    def crear(empresa_id, nombre, tipo_equipo, referencia, campos, por_equipo=True, oculto=False, categoria=None,
              incluir_en_carga_combinada=True):
        if ServicioTipo.query.filter_by(empresa_id=empresa_id, nombre=nombre).first():
            return
        db.session.add(ServicioTipo(
            empresa_id=empresa_id, nombre=nombre, por_equipo=por_equipo,
            tipo_equipo_aplicable=tipo_equipo, referencia_normativa=referencia,
            schema_json=json.dumps(campos), oculto=oculto, categoria=categoria,
            incluir_en_carga_combinada=incluir_en_carga_combinada,
        ))

    def punto_estado(campo, label, descripcion, foto=False):
        d = {"campo": campo, "tipo": "estado", "label": label, "descripcion": descripcion}
        if foto:
            d["requiere_foto"] = True
        return d

    def punto_numero(campo, label, unidad, descripcion):
        return {"campo": campo, "tipo": "numero", "label": label, "unidad": unidad,
                "descripcion": descripcion, "con_estado": True}

    def punto_booleano(campo, label, descripcion):
        return {"campo": campo, "tipo": "booleano", "label": label, "descripcion": descripcion}

    def punto_seleccion(campo, label, opciones, descripcion):
        return {"campo": campo, "tipo": "seleccion", "label": label, "opciones": opciones, "descripcion": descripcion}

    def punto_texto_largo(campo, label, descripcion):
        return {"campo": campo, "tipo": "texto_largo", "label": label, "descripcion": descripcion}

    campos_jockey = [
        punto_numero("presion_arranque", "Presión de arranque", "PSI", "Registrar la presión a la que arranca la bomba jockey."),
        punto_numero("presion_corte", "Presión de corte", "PSI", "Registrar la presión a la que se detiene al alcanzar el setpoint superior."),
        punto_estado("ciclado_excesivo", "Ciclado excesivo", "Verificar que no arranque y pare repetidamente en poco tiempo — indicio de fuga en el sistema."),
        punto_estado("fuga_sello", "Fugas en sello mecánico", "Inspeccionar el sello del eje por goteo excesivo o continuo."),
        punto_numero("amperaje", "Amperaje del motor", "A", "Corriente de línea con la bomba en marcha, comparada contra la placa del motor."),
    ]

    campos_electrobomba = [
        punto_estado("selector_auto", "Selector en modo Automático", "El selector del controlador debe estar siempre en posición Automático."),
        punto_numero("arranques", "Arranques desde la última visita", "arr.", "Contador de arranques del panel menos el valor registrado en la visita anterior."),
        punto_numero("horometro", "Horómetro (horas acumuladas)", "h", "Lectura acumulada del horómetro del panel de control."),
        punto_estado("alarmas_panel", "Alarmas o fallas activas", "Revisar el historial de fallas del controlador desde la última visita."),
        punto_numero("presion_succion", "Presión de succión", "PSI", "Con la bomba operando a régimen normal."),
        punto_numero("presion_descarga", "Presión de descarga", "PSI", "Verificar que esté dentro del rango de la curva característica del fabricante."),
        punto_numero("rpm", "RPM", "rpm", "Velocidad de giro del motor con la bomba a régimen."),
        punto_numero("voltaje", "Voltaje (3 fases)", "V", "Tensión de línea en el tablero de arranque."),
        punto_numero("amperaje", "Amperaje (3 fases)", "A", "Corriente de línea comparada contra la placa del motor."),
        punto_numero("temp_rodamientos", "Temperatura de rodamientos", "°C", "Rodamiento lado acople (drive end), por contacto."),
        punto_numero("temp_motor", "Temperatura de motor", "°C", "Carcasa del motor eléctrico, por contacto, con la bomba en régimen."),
        punto_estado("vibracion", "Vibración anómala", "Verificar ausencia de vibración o ruido inusual en bomba y motor."),
    ]

    campos_motobomba = [
        punto_estado("selector_auto", "Selector en modo Automático", "El selector del controlador debe estar siempre en posición Automático."),
        punto_numero("arranques", "Arranques desde la última visita", "arr.", "Contador de arranques del panel menos el valor registrado en la visita anterior."),
        punto_numero("horometro", "Horómetro (horas acumuladas)", "h", "Lectura acumulada del horómetro del motor diésel."),
        punto_estado("fallas_motor", "Códigos de falla del motor", "Revisar el historial de fallas del motor diésel desde la última visita."),
        punto_numero("presion_descarga", "Presión de descarga", "PSI", "Con el motor diésel en marcha, bomba a régimen."),
        punto_numero("rpm_motor", "RPM del motor", "rpm", "Velocidad de giro del motor diésel a régimen."),
        punto_numero("temp_motor", "Temperatura de motor", "°C", "Temperatura del refrigerante del motor diésel en régimen."),
        punto_numero("presion_aceite", "Presión de aceite de motor", "PSI", "Presión de lubricación del motor diésel a régimen."),
        punto_numero("nivel_combustible", "Nivel de combustible", "%", "Debe mantenerse sobre el 66% de la capacidad del tanque diario."),
        punto_numero("bateria", "Batería de arranque", "V", "Voltaje de cada banco de baterías en reposo."),
        punto_estado("fugas", "Fugas de combustible o aceite", "Inspección visual del motor y sus conexiones."),
    ]

    campos_reserva_agua = [
        punto_numero("nivel_agua", "Nivel de agua", "%", "Verificar que el nivel esté en la marca de rebose o el nivel normal de operación."),
        punto_estado("estado_tanque", "Estado estructural del tanque", "Inspección visual de fisuras, corrosión o daños en paredes y tapa de acceso."),
        punto_estado("valvulas_succion", "Válvulas de succión", "Confirmar que estén completamente abiertas y precintadas o supervisadas."),
        punto_estado("limpieza", "Limpieza y sedimentos", "Verificar ausencia de sedimentos, algas u obstrucciones visibles en el punto de acceso."),
    ]

    campos_senales = [
        punto_estado("falla_energia_normal", "Falla de energía normal", "Simular corte de energía normal y verificar que la señal de falla llegue a la central de alarma."),
        punto_estado("bomba_en_marcha", "Bomba en marcha", "Verificar que la señal de 'bomba en marcha' se transmita correctamente al arrancar."),
        punto_estado("selector_no_automatico", "Selector fuera de Automático", "Simular el selector en Manual/Apagado y verificar que se transmita la señal de supervisión."),
        punto_estado("nivel_bajo_reserva", "Nivel bajo de reserva de agua", "Simular nivel bajo y verificar que la señal llegue a la central."),
        punto_estado("valvula_succion_cerrada", "Válvula de succión no totalmente abierta", "Verificar la señal de supervisión de la válvula de succión/descarga."),
        punto_estado("falla_motor_diesel", "Falla de motor diésel / batería baja", "Si hay bomba de respaldo diésel, verificar que sus fallas se transmitan correctamente. N/A si no aplica."),
    ]

    # ECA: dos planillas separadas -- la inspección de rutina (más
    # frecuente) solo mira posición/manómetros/estado sin accionar nada;
    # la de inspección + prueba agrega los ensayos activos de tamper y
    # sensor de flujo, con una frecuencia más espaciada (semestral es lo
    # típico para el tamper). Ambas comparten los primeros 5 puntos.
    campos_eca_inspeccion = [
        punto_estado("posicion_valvula", "Posición de válvula", "Verificar que la válvula de control esté en la posición correcta (normalmente abierta) y visualmente asegurada/sellada o supervisada."),
        punto_numero("presion_arriba", "Presión manómetro arriba", "PSI", "Lectura del manómetro aguas arriba (lado de suministro)."),
        punto_numero("presion_abajo", "Presión manómetro abajo", "PSI", "Lectura del manómetro aguas abajo (lado de sistema)."),
        punto_estado("estado_eca", "Estado del ECA", "Corrosión, fugas, identificación y accesibilidad de la estación."),
        punto_estado("estado_supervision", "Estado del sistema de supervisión y alarma", "Inspección visual: sin indicación de falla en el panel para esta zona (no se activa la señal en esta planilla)."),
    ]
    campos_eca_inspeccion_prueba = campos_eca_inspeccion + [
        punto_estado("prueba_tamper", "Prueba de tamper de válvula", "Accionar el interruptor de supervisión de la válvula y verificar que la señal llegue correctamente a la central de alarma."),
        punto_estado("prueba_flujo", "Prueba de sensor de flujo", "Abrir el drenaje de prueba (o testigo) y verificar que la alarma de flujo se active y transmita correctamente."),
    ]

    # Mantenimiento anual con desarme -- extremo hidráulico de la bomba
    # (común a Electrobomba y Motobomba, el motor se cubre en checklists
    # aparte). Los puntos de condición física llevan foto para dejar
    # evidencia de lo encontrado al desarmar; las mediciones y las
    # confirmaciones sí/no no la requieren.
    campos_bomba_desarme = [
        punto_estado("alineacion_antes", "Alineación motor-bomba (antes del desarme)",
                      "Verificar visualmente la alineación motor-bomba antes de desacoplar, para comparar contra el estado post-armado.", foto=True),
        punto_numero("desviacion_alineacion", "Desviación de alineación medida (si corresponde corregir)", "mm",
                      "Valor medido con reloj comparador o láser antes de corregir, solo si se detectó desalineación."),
        punto_estado("estado_acoplamiento", "Estado del acoplamiento",
                      "Desgaste, grietas o juego excesivo en el elemento de acoplamiento (goma, disco, etc.).", foto=True),
        punto_seleccion("tipo_sello", "Tipo de sello del eje", ["Mecánico", "Empaquetadura (packing)"],
                         "Según lo encontrado al desarmar."),
        punto_estado("estado_sello_antes", "Estado de la empaquetadura/sello (antes)",
                      "Desgaste, endurecimiento o daño del sello/empaquetadura antes de intervenir.", foto=True),
        punto_booleano("reemplazo_sello", "¿Se reemplazó la empaquetadura/sello?", ""),
        punto_booleano("ajuste_prensaestopas", "Ajuste de prensaestopas realizado", "Aplica solo si el sello es por empaquetadura."),
        punto_estado("estado_rodamientos", "Estado de rodamientos de la bomba",
                      "Juego, ruido o señales de sobrecalentamiento en los rodamientos de la bomba.", foto=True),
        punto_booleano("lubricacion_rodamientos", "¿Se lubricaron los rodamientos?", ""),
        punto_estado("estado_impulsor", "Estado del impulsor/rodete",
                      "Erosión, cavitación, corrosión o desbalance visible del impulsor.", foto=True),
        punto_numero("juego_axial", "Juego axial medido", "mm", "Medido con reloj comparador tras el armado."),
        punto_estado("estado_wear_rings", "Estado de anillos de desgaste (wear rings)",
                      "Holgura entre anillo de desgaste e impulsor, comparada contra la tolerancia del fabricante.", foto=True),
        punto_numero("vibracion_post_armado", "Vibración medida post-armado (si tenés medidor)", "mm/s",
                      "Solo si se dispone de medidor de vibraciones."),
        punto_texto_largo("observaciones_generales", "Observaciones generales", ""),
    ]

    campos_motor_electrico = [
        punto_numero("resistencia_aislacion", "Resistencia de aislación (megado)", "MΩ",
                      "Medida entre fases y a tierra con megóhmetro. El valor mínimo aceptable depende de la tensión y el fabricante del motor."),
        punto_estado("estado_bobinado", "Estado del bobinado",
                      "Inspección visual: decoloración, olor a quemado o daño en el aislamiento del bobinado.", foto=True),
        punto_estado("estado_rodamientos_motor", "Estado de rodamientos del motor",
                      "Juego, ruido o señales de sobrecalentamiento en los rodamientos del motor eléctrico.", foto=True),
        punto_booleano("ajuste_bornera", "Ajuste de bornera de conexiones realizado", ""),
    ]

    campos_motor_diesel = [
        punto_numero("horas_motor", "Horas de motor al momento del servicio", "h", "Lectura del horómetro del motor diésel."),
        punto_estado("nivel_aceite", "Nivel de aceite", "Verificar contra las marcas mín./máx. de la varilla."),
        punto_booleano("cambio_aceite", "Cambio de aceite de motor", ""),
        punto_booleano("cambio_filtro_aceite", "Cambio de filtro de aceite", ""),
        punto_booleano("cambio_filtro_combustible", "Cambio de filtro de combustible", ""),
        punto_booleano("cambio_filtro_aire", "Cambio de filtro de aire", ""),
        punto_estado("nivel_refrigerante", "Nivel de refrigerante", "Verificar contra las marcas del tanque de expansión o radiador."),
        punto_estado("estado_intercambiador", "Estado del intercambiador de calor",
                      "Corrosión, incrustaciones o fugas en el intercambiador de calor.", foto=True),
        punto_booleano("recambio_anodo", "Recambio del ánodo de sacrificio", ""),
        punto_booleano("recambio_termostato", "Recambio del termostato", ""),
        punto_booleano("recambio_bomba_agua", "Recambio de la bomba de agua", ""),
        punto_booleano("recambio_mangones_refrigeracion", "Recambio de mangones de refrigeración", ""),
        punto_estado("estado_mangones_combustible", "Estado de mangones de combustible",
                      "Grietas, resecamiento o fugas en las mangueras de combustible.", foto=True),
        punto_booleano("recambio_correas", "Recambio de correas", ""),
        punto_booleano("kit_recambio_anual", "Kit de recambio anual aplicado", ""),
        punto_booleano("kit_recambio_segundo_anio", "Kit de recambio de segundo año aplicado", ""),
        punto_estado("estado_escape", "Estado del sistema de escape",
                      "Corrosión, fugas o daño visible en el sistema de escape.", foto=True),
        punto_texto_largo("observaciones_generales", "Observaciones generales", ""),
    ]

    campos_bie = [
        punto_estado("manguera", "Estado de la manguera", "Inspección visual: sin cortes, desgaste ni acople dañado."),
        punto_estado("boquilla", "Boquilla / pitón", "Presente, sin obstrucciones, cierra y abre correctamente."),
        punto_estado("valvula_angular", "Válvula angular", "Opera sin trabarse y sin fugas."),
        punto_numero("presion_boca", "Presión en boca", "PSI", "Solo si la boca tiene manómetro propio."),
        punto_estado("gabinete", "Gabinete accesible y en buen estado", "Puerta/vidrio intacto, sin obstrucciones delante, señalización visible."),
    ]

    for empresa in Empresa.query.all():
        eid = empresa.id
        # Los 4 de acá abajo son "miembros" del paquete "Inspecciones y
        # pruebas en sala de bombas" (oculto=True): siguen existiendo para
        # definir su propio checklist por tipo de equipo, pero no se
        # ofrecen sueltos al agregar un servicio a un contrato -- antes,
        # contratarlos uno por uno generaba un ítem de visita por cada
        # equipo (4 tarjetas con el mismo botón de checklist repetido, y 4
        # "marcar cumplido" para un solo trabajo).
        crear(eid, "Inspección semanal — Bomba jockey", "Bomba jockey", "NFPA 25 · §8.3 Inspección semanal", campos_jockey, oculto=True)
        crear(eid, "Inspección semanal — Electrobomba", "Electrobomba", "NFPA 25 · §8.3.3 Prueba de funcionamiento semanal", campos_electrobomba, oculto=True)
        crear(eid, "Inspección semanal — Motobomba", "Motobomba", "NFPA 25 · §8.3 Inspección semanal — motor diésel", campos_motobomba, oculto=True)
        crear(eid, "Inspección — Reserva de agua", "Reserva de agua", "NFPA 25 · §9.2 Inspección de tanques", campos_reserva_agua, oculto=True)
        crear(eid, "Inspecciones y pruebas en sala de bombas", None, None, [], por_equipo=False, categoria="Sala de bombas")
        crear(eid, "Señales de supervisión y falla — Sala de bombas", "Bomba jockey", "NFPA 25 · §4.6 — Señales de supervisión y falla", campos_senales, por_equipo=False)

        # Backfill: versiones ya seedeadas antes de que tipo_equipo_aplicable
        # se completara acá arriba (bug: quedaba en None) -- sin esto, este
        # checklist no aparece agrupado bajo "Sala de bombas" en ningún
        # lado (categoria_de_tipo_equipo(None) da None) y su botón "+"
        # aparece suelto en cualquier ítem de cualquier visita, no solo los
        # de sala de bombas. Se corrige también la copia ya importada de
        # cada cliente (TipoFormulario), no solo el catálogo de empresa.
        NOMBRE_SENALES = "Señales de supervisión y falla — Sala de bombas"
        ServicioTipo.query.filter(
            ServicioTipo.empresa_id == eid,
            ServicioTipo.nombre == NOMBRE_SENALES,
            ServicioTipo.tipo_equipo_aplicable.is_(None),
        ).update({"tipo_equipo_aplicable": "Bomba jockey"}, synchronize_session=False)
        TipoFormulario.query.filter(
            TipoFormulario.cliente_id.in_(db.session.query(Cliente.id).filter(Cliente.empresa_id == eid)),
            TipoFormulario.nombre == NOMBRE_SENALES,
            TipoFormulario.tipo_equipo_aplicable.is_(None),
        ).update({"tipo_equipo_aplicable": "Bomba jockey"}, synchronize_session=False)

        # crear() no toca un ServicioTipo que ya existía (de una corrida
        # anterior de este seed, antes de que existiera el paquete) -- acá
        # se ocultan igual, aunque ya estuvieran cargados.
        ServicioTipo.query.filter(
            ServicioTipo.empresa_id == eid,
            ServicioTipo.nombre.in_([
                "Inspección semanal — Bomba jockey", "Inspección semanal — Electrobomba",
                "Inspección semanal — Motobomba", "Inspección — Reserva de agua",
            ]),
        ).update({"oculto": True}, synchronize_session=False)
        crear(eid, "Inspección — ECA", "ECA", "NFPA 25 · Cap. 13 §13.3.2 — Inspección de válvulas (posición, manómetros, estado)", campos_eca_inspeccion)
        crear(eid, "Inspección + prueba — ECA", "ECA", "NFPA 25 · Cap. 13 §13.3.3 — Prueba de válvula y dispositivos de supervisión/alarma (frecuencia varía según edición adoptada)", campos_eca_inspeccion_prueba)
        crear(eid, "Inspección — BIE", "BIE", "NFPA 25 · Cap. 6 (Standpipe and Hose Systems)", campos_bie)

        # incluir_en_carga_combinada=False: son mantenimientos anuales con
        # desarme, no inspecciones de rutina -- sin esto quedaban mezclados
        # con "Inspecciones y pruebas en sala de bombas" en la pantalla
        # combinada de carga solo por compartir tipo de equipo.
        crear(eid, "Mantenimiento anual — Bomba (desarme) — Electrobomba", "Electrobomba",
              "Mantenimiento preventivo anual con desarme — extremo hidráulico", campos_bomba_desarme,
              incluir_en_carga_combinada=False)
        crear(eid, "Mantenimiento anual — Bomba (desarme) — Motobomba", "Motobomba",
              "Mantenimiento preventivo anual con desarme — extremo hidráulico", campos_bomba_desarme,
              incluir_en_carga_combinada=False)
        crear(eid, "Mantenimiento anual — Motor eléctrico (desarme)", "Electrobomba",
              "Mantenimiento preventivo anual con desarme — motor eléctrico", campos_motor_electrico,
              incluir_en_carga_combinada=False)
        crear(eid, "Mantenimiento anual — Motor diésel (desarme)", "Motobomba",
              "Mantenimiento preventivo anual con desarme — motor diésel", campos_motor_diesel,
              incluir_en_carga_combinada=False)
        # Backfill: empresas que ya tenían estos 4 corridos de una corrida
        # anterior del seed quedaron con incluir_en_carga_combinada=True
        # (el default de la columna) -- crear() no las toca porque ya
        # existen por nombre, así que se corrigen acá aparte. Se corrige
        # también la copia ya importada de cada cliente (TipoFormulario),
        # igual que el backfill de tipo_equipo_aplicable de más arriba.
        NOMBRES_MANTENIMIENTO_DESARME = [
            "Mantenimiento anual — Bomba (desarme) — Electrobomba",
            "Mantenimiento anual — Bomba (desarme) — Motobomba",
            "Mantenimiento anual — Motor eléctrico (desarme)",
            "Mantenimiento anual — Motor diésel (desarme)",
        ]
        ServicioTipo.query.filter(
            ServicioTipo.empresa_id == eid,
            ServicioTipo.nombre.in_(NOMBRES_MANTENIMIENTO_DESARME),
        ).update({"incluir_en_carga_combinada": False}, synchronize_session=False)
        TipoFormulario.query.filter(
            TipoFormulario.cliente_id.in_(db.session.query(Cliente.id).filter(Cliente.empresa_id == eid)),
            TipoFormulario.nombre.in_(NOMBRES_MANTENIMIENTO_DESARME),
        ).update({"incluir_en_carga_combinada": False}, synchronize_session=False)

    db.session.commit()

