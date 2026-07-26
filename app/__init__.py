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
    from app.routes.planificacion import planificacion_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.ordenes_trabajo import ordenes_bp
    from app.routes.inventario import inventario_bp
    from app.routes.recordatorios import recordatorios_bp
    from app.routes.tipos_formulario import tipos_formulario_bp
    from app.routes.empresas import empresas_bp
    from app.routes.usuarios import usuarios_bp
    from app.routes.portal import portal_bp
    from app.routes.servicios_tipo import servicios_tipo_bp
    from app.routes.curvas import curvas_bp
    from app.routes.salas import salas_bp

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
    app.register_blueprint(planificacion_bp)
    app.register_blueprint(ordenes_bp)
    app.register_blueprint(inventario_bp)
    app.register_blueprint(recordatorios_bp)
    app.register_blueprint(tipos_formulario_bp)
    app.register_blueprint(empresas_bp)
    app.register_blueprint(usuarios_bp)
    app.register_blueprint(portal_bp)
    app.register_blueprint(servicios_tipo_bp)
    app.register_blueprint(curvas_bp)
    app.register_blueprint(salas_bp)

    with app.app_context():
        db.create_all()
        _seed_super_admin()
        _seed_tipos_equipo()

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
        ("BIE", "Bocas de incendio"),
        ("Otro", "Otros equipos"),
    ]
    for nombre, categoria in base:
        db.session.add(TipoEquipo(nombre=nombre, categoria=categoria))
    db.session.commit()

