import os
import tempfile

# Tiene que fijarse ANTES de importar app.config (Config.SQLALCHEMY_DATABASE_URI
# se calcula una sola vez, al importar ese módulo por primera vez) — así toda
# la suite corre contra un archivo SQLite temporal, nunca contra la base real.
_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest

from app import create_app
from app import db as _db
from app.models import Cliente, Empresa, Instalacion, Usuario


@pytest.fixture(scope="session")
def _flask_app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False, CSRF_ENABLED=False)
    yield application
    os.close(_db_fd)
    os.unlink(_db_path)


@pytest.fixture()
def app(_flask_app):
    """Contexto de aplicación nuevo por test — Flask-Login guarda el
    usuario logueado en flask.g, que vive atado al contexto de app; con un
    solo contexto para toda la sesión, un test que hace login "contamina"
    a los que corren después dentro del mismo proceso de pytest."""
    with _flask_app.app_context():
        yield _flask_app


@pytest.fixture(autouse=True)
def _esquema_limpio(app):
    """Esquema nuevo por test — create_all()/drop_all() directo sobre los
    modelos, no vía Alembic (las migraciones son para evolucionar una base
    real con el tiempo; un test no tiene historial, solo necesita el
    esquema actual)."""
    _db.create_all()
    yield
    _db.session.remove()
    _db.drop_all()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def empresa(db):
    e = Empresa(nombre="Empresa Test SA")
    db.session.add(e)
    db.session.commit()
    return e


def _crear_usuario(db, empresa, rol, username):
    u = Usuario(username=username, nombre_completo=f"{rol} de prueba", rol=rol, empresa_id=empresa.id, activo=True)
    u.set_password("clave123")
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture()
def usuario_admin(db, empresa):
    return _crear_usuario(db, empresa, "Administrador", "admin_test")


@pytest.fixture()
def usuario_jefe(db, empresa):
    return _crear_usuario(db, empresa, "Jefe", "jefe_test")


@pytest.fixture()
def usuario_tecnico(db, empresa):
    return _crear_usuario(db, empresa, "Técnico", "tecnico_test")


@pytest.fixture()
def cliente(db, empresa):
    c = Cliente(nombre="Cliente Test", empresa_id=empresa.id, activo=True)
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture()
def instalacion(db, cliente):
    from datetime import date

    i = Instalacion(cliente_id=cliente.id, nombre="Instalación Test", fecha_alta=date.today())
    db.session.add(i)
    db.session.commit()
    return i


def login(client, usuario, password="clave123"):
    return client.post("/login", data={"username": usuario.username, "password": password}, follow_redirects=True)
