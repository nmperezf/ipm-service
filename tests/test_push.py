import pytest
from firebase_admin import messaging

from app import db
from app.models import Notificacion, PushToken
from app.push import enviar_push_agrupado


def login(client, usuario, password="clave123"):
    return client.post("/login", data={"username": usuario.username, "password": password}, follow_redirects=True)


def _crear_notificacion(db, empresa, destinatario, tipo, titulo, cliente_id=None):
    n = Notificacion(
        empresa_id=empresa.id, destinatario_id=destinatario.id, cliente_id=cliente_id,
        tipo=tipo, titulo=titulo,
    )
    db.session.add(n)
    db.session.commit()
    return n


def _crear_token(db, usuario, token="token-dispositivo-1"):
    push_token = PushToken(usuario_id=usuario.id, token=token)
    db.session.add(push_token)
    db.session.commit()
    return push_token


@pytest.fixture(autouse=True)
def _firebase_configurado(monkeypatch):
    # enviar_push_agrupado no hace nada si _app_firebase() devuelve None
    # (ver app/push.py) -- se simula un "app" de Firebase ya inicializada
    # sin tocar credenciales reales.
    monkeypatch.setattr("app.push._app_firebase", lambda: object())


class TestEnviarPushAgrupado:
    def test_sin_tokens_no_llama_a_fcm(self, app, db, empresa, usuario_jefe, monkeypatch):
        llamado = {}
        monkeypatch.setattr("app.push.messaging.send", lambda *a, **kw: llamado.setdefault("si", True))
        _crear_notificacion(db, empresa, usuario_jefe, "mensaje_nuevo", "Hola")

        with app.test_request_context():
            enviar_push_agrupado(usuario_jefe.id, "mensaje_nuevo", None)

        assert "si" not in llamado

    def test_sin_firebase_configurado_no_hace_nada(self, app, db, empresa, usuario_jefe, monkeypatch):
        monkeypatch.setattr("app.push._app_firebase", lambda: None)
        llamado = {}
        monkeypatch.setattr("app.push.messaging.send", lambda *a, **kw: llamado.setdefault("si", True))
        _crear_token(db, usuario_jefe)
        _crear_notificacion(db, empresa, usuario_jefe, "mensaje_nuevo", "Hola")

        with app.test_request_context():
            enviar_push_agrupado(usuario_jefe.id, "mensaje_nuevo", None)

        assert "si" not in llamado

    def test_grupo_de_una_sola_usa_el_titulo_puntual(self, app, db, empresa, cliente, usuario_jefe, monkeypatch):
        capturado = {}

        def fake_send(mensaje, app=None):
            capturado["mensaje"] = mensaje

        monkeypatch.setattr("app.push.messaging.send", fake_send)
        _crear_token(db, usuario_jefe)
        _crear_notificacion(
            db, empresa, usuario_jefe, "observacion_nueva", "Observación nueva (Deficiencia crítica) — Bomba 1",
            cliente_id=cliente.id,
        )

        with app.test_request_context():
            enviar_push_agrupado(usuario_jefe.id, "observacion_nueva", cliente.id)

        mensaje = capturado["mensaje"]
        assert mensaje.notification.title == cliente.nombre
        assert mensaje.notification.body == "Observación nueva (Deficiencia crítica) — Bomba 1"
        assert mensaje.android.notification.tag == f"observacion_nueva-{cliente.id}"
        assert mensaje.android.notification.color == "#E2131D"  # observacion_nueva -> severidad "critico"

    def test_grupo_de_varias_usa_cantidad_y_plural(self, app, db, empresa, cliente, usuario_jefe, monkeypatch):
        capturado = {}
        monkeypatch.setattr("app.push.messaging.send", lambda mensaje, app=None: capturado.setdefault("mensaje", mensaje))
        _crear_token(db, usuario_jefe)
        for i in range(3):
            _crear_notificacion(db, empresa, usuario_jefe, "observacion_nueva", f"Observación {i}", cliente_id=cliente.id)

        with app.test_request_context():
            enviar_push_agrupado(usuario_jefe.id, "observacion_nueva", cliente.id)

        mensaje = capturado["mensaje"]
        assert mensaje.notification.title == cliente.nombre
        assert mensaje.notification.body == "3 observaciones nuevas"
        assert mensaje.android.notification.tag == f"observacion_nueva-{cliente.id}"

    def test_notificacion_leida_no_se_cuenta(self, app, db, empresa, cliente, usuario_jefe, monkeypatch):
        llamado = {}
        monkeypatch.setattr("app.push.messaging.send", lambda *a, **kw: llamado.setdefault("si", True))
        n = _crear_notificacion(db, empresa, usuario_jefe, "observacion_nueva", "Ya vista", cliente_id=cliente.id)
        n.leido = True
        db.session.commit()
        _crear_token(db, usuario_jefe)

        with app.test_request_context():
            enviar_push_agrupado(usuario_jefe.id, "observacion_nueva", cliente.id)

        assert "si" not in llamado

    def test_sin_cliente_no_agrupa_y_usa_marca_generica(self, app, db, empresa, usuario_jefe, monkeypatch):
        capturado = {}
        monkeypatch.setattr("app.push.messaging.send", lambda mensaje, app=None: capturado.setdefault("mensaje", mensaje))
        _crear_token(db, usuario_jefe)
        n = _crear_notificacion(db, empresa, usuario_jefe, "mensaje_nuevo", "Mensaje de Juan: Hola")

        with app.test_request_context():
            enviar_push_agrupado(usuario_jefe.id, "mensaje_nuevo", None)

        mensaje = capturado["mensaje"]
        assert mensaje.notification.title == "IPM Manager"
        assert mensaje.notification.body == "Mensaje de Juan: Hola"
        assert mensaje.android.notification.tag == f"mensaje_nuevo-{n.id}"

    def test_token_vencido_se_borra_solo(self, app, db, empresa, cliente, usuario_jefe, monkeypatch):
        def fake_send(mensaje, app=None):
            raise messaging.UnregisteredError("gone")

        monkeypatch.setattr("app.push.messaging.send", fake_send)
        push_token = _crear_token(db, usuario_jefe)
        _crear_notificacion(db, empresa, usuario_jefe, "observacion_nueva", "X", cliente_id=cliente.id)

        with app.test_request_context():
            enviar_push_agrupado(usuario_jefe.id, "observacion_nueva", cliente.id)

        assert db.session.get(PushToken, push_token.id) is None

    def test_otro_error_no_borra_el_token(self, app, db, empresa, cliente, usuario_jefe, monkeypatch):
        def fake_send(mensaje, app=None):
            raise RuntimeError("boom")

        monkeypatch.setattr("app.push.messaging.send", fake_send)
        push_token = _crear_token(db, usuario_jefe)
        _crear_notificacion(db, empresa, usuario_jefe, "observacion_nueva", "X", cliente_id=cliente.id)

        with app.test_request_context():
            enviar_push_agrupado(usuario_jefe.id, "observacion_nueva", cliente.id)

        assert db.session.get(PushToken, push_token.id) is not None


class TestRutasRegistroToken:
    def test_requiere_login(self, client):
        resp = client.post("/push/registrar", json={"token": "abc"})
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_registrar_crea_la_fila(self, client, db, usuario_jefe):
        login(client, usuario_jefe)
        resp = client.post("/push/registrar", json={"token": "token-xyz"})
        assert resp.status_code == 200
        push_token = PushToken.query.filter_by(usuario_id=usuario_jefe.id).first()
        assert push_token is not None
        assert push_token.token == "token-xyz"

    def test_registrar_de_nuevo_actualiza_en_vez_de_duplicar(self, client, db, usuario_jefe):
        login(client, usuario_jefe)
        client.post("/push/registrar", json={"token": "token-xyz"})
        client.post("/push/registrar", json={"token": "token-xyz"})
        assert PushToken.query.filter_by(usuario_id=usuario_jefe.id).count() == 1

    def test_registrar_sin_token_da_400(self, client, usuario_jefe):
        login(client, usuario_jefe)
        resp = client.post("/push/registrar", json={})
        assert resp.status_code == 400

    def test_desregistrar_borra_la_fila(self, client, db, usuario_jefe):
        login(client, usuario_jefe)
        client.post("/push/registrar", json={"token": "token-xyz"})
        resp = client.post("/push/desregistrar", json={"token": "token-xyz"})
        assert resp.status_code == 200
        assert PushToken.query.filter_by(usuario_id=usuario_jefe.id).count() == 0

    def test_no_se_puede_desregistrar_el_token_de_otro_usuario(self, client, db, usuario_jefe, usuario_tecnico):
        login(client, usuario_jefe)
        client.post("/push/registrar", json={"token": "token-xyz"})
        client.get("/logout")

        login(client, usuario_tecnico)
        client.post("/push/desregistrar", json={"token": "token-xyz"})

        assert PushToken.query.filter_by(usuario_id=usuario_jefe.id).count() == 1


class TestIntegracionConNotificaciones:
    def test_mensaje_nuevo_dispara_push_agrupado(self, client, db, empresa, usuario_jefe, usuario_tecnico, monkeypatch):
        """Extremo a extremo: crear un Mensaje (notificar_usuario) dispara,
        vía el hook after_request, un push al destinatario -- sin que la
        ruta de mensajes sepa nada de push (ver app/notificaciones.py y el
        after_request en app/__init__.py)."""
        capturado = {}
        monkeypatch.setattr("app.push.messaging.send", lambda mensaje, app=None: capturado.setdefault("mensaje", mensaje))
        _crear_token(db, usuario_jefe)

        login(client, usuario_tecnico)
        resp = client.post(
            "/mensajes/nuevo",
            data={"destinatario_id": usuario_jefe.id, "titulo": "Falta un repuesto", "prioridad": "Alta"},
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert "mensaje" in capturado, "se esperaba que el after_request disparara el push"
        assert "Falta un repuesto" in capturado["mensaje"].notification.body
