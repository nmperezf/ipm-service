import pytest
from flask_login import login_user
from werkzeug.exceptions import Forbidden, Unauthorized

from app.auth_utils import clientes_visibles, rol_requerido, verificar_acceso_cliente, verificar_escritura_cliente
from app.models import Cliente, Empresa, Usuario


def _usuario(db, empresa, rol, username, cliente_id=None):
    u = Usuario(username=username, nombre_completo=username, rol=rol, empresa_id=empresa.id if rol != "Cliente" else None,
                cliente_id=cliente_id)
    u.set_password("x")
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture()
def otra_empresa(db):
    e = Empresa(nombre="Otra Empresa SA")
    db.session.add(e)
    db.session.commit()
    return e


@pytest.fixture()
def cliente_otra_empresa(db, otra_empresa):
    c = Cliente(nombre="Cliente de otra empresa", empresa_id=otra_empresa.id, activo=True)
    db.session.add(c)
    db.session.commit()
    return c


class TestClientesVisibles:
    def test_super_admin_ve_clientes_de_cualquier_empresa(self, app, db, empresa, cliente, cliente_otra_empresa):
        admin = _usuario(db, empresa, "Super Admin", "super1")
        with app.test_request_context():
            login_user(admin)
            ids = {c.id for c in clientes_visibles().all()}
        assert cliente.id in ids
        assert cliente_otra_empresa.id in ids

    def test_administrador_solo_ve_su_propia_empresa(self, app, db, empresa, cliente, cliente_otra_empresa):
        admin = _usuario(db, empresa, "Administrador", "admin1")
        with app.test_request_context():
            login_user(admin)
            ids = {c.id for c in clientes_visibles().all()}
        assert cliente.id in ids
        assert cliente_otra_empresa.id not in ids

    def test_rol_cliente_solo_ve_su_propio_cliente(self, app, db, empresa, cliente):
        otro_cliente = Cliente(nombre="Otro cliente de la misma empresa", empresa_id=empresa.id, activo=True)
        db.session.add(otro_cliente)
        db.session.commit()
        usuario_cliente = _usuario(db, empresa, "Cliente", "cliente1", cliente_id=cliente.id)
        with app.test_request_context():
            login_user(usuario_cliente)
            ids = {c.id for c in clientes_visibles().all()}
        assert ids == {cliente.id}


class TestVerificarAccesoCliente:
    def test_administrador_accede_a_cliente_de_su_empresa(self, app, db, empresa, cliente):
        admin = _usuario(db, empresa, "Administrador", "admin2")
        with app.test_request_context():
            login_user(admin)
            verificar_acceso_cliente(cliente)  # no debe tirar

    def test_administrador_no_accede_a_cliente_de_otra_empresa(self, app, db, empresa, cliente_otra_empresa):
        admin = _usuario(db, empresa, "Administrador", "admin3")
        with app.test_request_context():
            login_user(admin)
            with pytest.raises(Forbidden):
                verificar_acceso_cliente(cliente_otra_empresa)

    def test_rol_cliente_no_accede_a_otro_cliente(self, app, db, empresa, cliente):
        otro_cliente = Cliente(nombre="Otro cliente", empresa_id=empresa.id, activo=True)
        db.session.add(otro_cliente)
        db.session.commit()
        usuario_cliente = _usuario(db, empresa, "Cliente", "cliente2", cliente_id=cliente.id)
        with app.test_request_context():
            login_user(usuario_cliente)
            with pytest.raises(Forbidden):
                verificar_acceso_cliente(otro_cliente)

    def test_super_admin_accede_a_cualquier_cliente(self, app, db, empresa, cliente_otra_empresa):
        admin = _usuario(db, empresa, "Super Admin", "super2")
        with app.test_request_context():
            login_user(admin)
            verificar_acceso_cliente(cliente_otra_empresa)  # no debe tirar


class TestVerificarEscrituraCliente:
    def test_tecnico_sin_ot_asignada_no_puede_escribir(self, app, db, empresa, cliente):
        tecnico = _usuario(db, empresa, "Técnico", "tec1")
        with app.test_request_context():
            login_user(tecnico)
            with pytest.raises(Forbidden):
                verificar_escritura_cliente(cliente)

    def test_administrador_siempre_puede_escribir_en_su_empresa(self, app, db, empresa, cliente):
        admin = _usuario(db, empresa, "Administrador", "admin4")
        with app.test_request_context():
            login_user(admin)
            verificar_escritura_cliente(cliente)  # no debe tirar


class TestRolRequerido:
    def test_sin_sesion_tira_401(self, app):
        @rol_requerido("Administrador")
        def vista():
            return "ok"

        with app.test_request_context():
            with pytest.raises(Unauthorized):
                vista()

    def test_rol_no_permitido_tira_403(self, app, db, empresa):
        tecnico = _usuario(db, empresa, "Técnico", "tec2")

        @rol_requerido("Administrador", "Jefe")
        def vista():
            return "ok"

        with app.test_request_context():
            login_user(tecnico)
            with pytest.raises(Forbidden):
                vista()

    def test_rol_permitido_deja_pasar(self, app, db, empresa):
        jefe = _usuario(db, empresa, "Jefe", "jefe2")

        @rol_requerido("Administrador", "Jefe")
        def vista():
            return "ok"

        with app.test_request_context():
            login_user(jefe)
            assert vista() == "ok"
