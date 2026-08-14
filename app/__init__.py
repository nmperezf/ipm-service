import json
import random
from datetime import date, timedelta

from flask import Flask, render_template
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import OperationalError

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

    db.init_app(app)
    migrate.init_app(app, db)
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
            _seed_clientes_demo()
        except OperationalError:
            # El esquema todavía no existe (falta correr "flask db upgrade")
            # — pasa la primera vez que se clona el repo, y durante los
            # comandos "flask db init/migrate". Se resuelve solo en el
            # próximo arranque, una vez aplicadas las migraciones.
            db.session.rollback()

    return app


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


def _seed_catalogo_nfpa():
    """Catálogo de checklists de inspección NFPA 25 (con estado por punto:
    Aprobado/Observado/Deficiencia/N-A) para sala de bombas, ECA y BIE --
    se arma una vez por empresa; cada cliente los importa desde acá (ver
    TipoFormulario.desde_catalogo) en vez de tener que armarlos a mano.
    Las referencias de norma/sección son orientativas -- conviene
    verificarlas contra la edición de NFPA 25 realmente adoptada antes de
    usarlas en un documento de cumplimiento."""
    from app.models import Empresa, ServicioTipo

    def crear(empresa_id, nombre, tipo_equipo, referencia, campos, por_equipo=True, oculto=False, categoria=None):
        if ServicioTipo.query.filter_by(empresa_id=empresa_id, nombre=nombre).first():
            return
        db.session.add(ServicioTipo(
            empresa_id=empresa_id, nombre=nombre, por_equipo=por_equipo,
            tipo_equipo_aplicable=tipo_equipo, referencia_normativa=referencia,
            schema_json=json.dumps(campos), oculto=oculto, categoria=categoria,
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
        crear(eid, "Señales de supervisión y falla — Sala de bombas", None, "NFPA 25 · §4.6 — Señales de supervisión y falla", campos_senales, por_equipo=False)

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

        crear(eid, "Mantenimiento anual — Bomba (desarme) — Electrobomba", "Electrobomba",
              "Mantenimiento preventivo anual con desarme — extremo hidráulico", campos_bomba_desarme)
        crear(eid, "Mantenimiento anual — Bomba (desarme) — Motobomba", "Motobomba",
              "Mantenimiento preventivo anual con desarme — extremo hidráulico", campos_bomba_desarme)
        crear(eid, "Mantenimiento anual — Motor eléctrico (desarme)", "Electrobomba",
              "Mantenimiento preventivo anual con desarme — motor eléctrico", campos_motor_electrico)
        crear(eid, "Mantenimiento anual — Motor diésel (desarme)", "Motobomba",
              "Mantenimiento preventivo anual con desarme — motor diésel", campos_motor_diesel)

    db.session.commit()


def _seed_clientes_demo():
    """Carga 10 clientes de ejemplo (con instalaciones, equipos, contratos,
    hoja de ruta e historial de checklists) para que nmperezf pueda probar
    la app con datos realistas -- se corre en cada arranque pero cada
    cliente se crea una sola vez (se salta si ya existe por nombre)."""
    from app.models import (
        Cliente, Contrato, Equipo, Instalacion, ItemVisita,
        Observacion, OrdenTrabajo, Presupuesto, ServicioContrato,
        ServicioTipo, TipoFormulario, Usuario, Visita,
    )

    ref = Usuario.query.filter_by(username="nmperezf").first()
    if not ref:
        return
    empresa_id = ref.empresa_id
    hoy = date.today()
    rng = random.Random(42)

    perfiles = {
        "chico": {"eca": 2, "bie": 3, "otros": 2},
        "mediano": {"eca": 5, "bie": 8, "otros": 3},
        "grande": {"eca": 12, "bie": 15, "otros": 5},
    }

    # Las 4 combinaciones de sala de bombas que se ven en la práctica --
    # se van rotando entre los 10 clientes de ejemplo para mostrar todas.
    # Todas llevan además su reserva de agua (se agrega aparte, siempre).
    combos_sala_bombas = [
        [("Bomba jockey", "Bomba jockey"), ("Electrobomba", "Bomba principal")],
        [("Bomba jockey", "Bomba jockey"), ("Electrobomba", "Bomba principal"), ("Electrobomba", "Bomba secundaria")],
        [("Bomba jockey", "Bomba jockey"), ("Motobomba", "Bomba principal (diésel)")],
        [("Bomba jockey", "Bomba jockey"), ("Electrobomba", "Bomba principal"), ("Motobomba", "Bomba de respaldo (diésel)")],
    ]

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

    def importar_catalogo(cliente):
        for servicio_tipo in ServicioTipo.query.filter_by(empresa_id=empresa_id).all():
            TipoFormulario.desde_catalogo(servicio_tipo, cliente.id)
        db.session.flush()

    def crear_equipos(inst, perfil, n_eca_override, idx_cliente):
        p = perfiles[perfil]
        equipos = {"bomba": [], "eca": [], "bie": [], "otro": []}
        combo = combos_sala_bombas[idx_cliente % len(combos_sala_bombas)]
        for tipo, nombre in combo:
            e = Equipo(instalacion_id=inst.id, nombre=nombre, tipo=tipo, ubicacion="Sala de bombas")
            db.session.add(e)
            equipos["bomba"].append(e)
        reserva = Equipo(instalacion_id=inst.id, nombre="Reserva de agua", tipo="Reserva de agua", ubicacion="Sala de bombas")
        db.session.add(reserva)
        equipos["bomba"].append(reserva)
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

    for idx_cliente, cdata in enumerate(clientes_demo):
        if Cliente.query.filter_by(nombre=cdata["nombre"]).first():
            continue
        cliente = Cliente(empresa_id=empresa_id, nombre=cdata["nombre"], contacto=cdata["contacto"],
                          telefono=cdata["telefono"], activo=True)
        db.session.add(cliente)
        db.session.flush()

        importar_catalogo(cliente)

        for idx_inst, (nombre_inst, direccion, perfil, n_eca_override) in enumerate(cdata["instalaciones"]):
            inst = Instalacion(cliente_id=cliente.id, nombre=nombre_inst, direccion=direccion)
            db.session.add(inst)
            db.session.flush()

            equipos = crear_equipos(inst, perfil, n_eca_override, idx_cliente)

            contrato = Contrato(instalacion_id=inst.id, nombre=f"Contrato anual {hoy.year}",
                                fecha_inicio=hoy - timedelta(days=200), fecha_fin=hoy + timedelta(days=165),
                                estado="Activo", activo=True)
            db.session.add(contrato)
            db.session.flush()
            servicio = ServicioContrato(contrato_id=contrato.id, nombre="Mantenimiento preventivo mensual", frecuencia="mensual")
            db.session.add(servicio)
            db.session.flush()

            muestra_bie = equipos["bie"][:2]

            # Historial de visitas cerradas, sin checklists precargados --
            # quedan listos para que se completen desde la app (mismo
            # criterio que "Cargar checklist de categoría"), en vez de
            # simular datos que no se corresponden con ningún ensayo real.
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

