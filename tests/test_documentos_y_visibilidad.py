import io
import shutil
import tempfile

import pytest

from app.models import Cliente, Documento, Empresa, Instalacion, Observacion, Usuario
from tests.conftest import login


@pytest.fixture(autouse=True)
def _upload_folder_temporal(app):
    """Los uploads de estos tests no deben escribir en app/static/uploads
    real -- se redirige UPLOAD_FOLDER a un directorio temporal por test."""
    original = app.config["UPLOAD_FOLDER"]
    tmp_dir = tempfile.mkdtemp()
    app.config["UPLOAD_FOLDER"] = tmp_dir
    yield
    app.config["UPLOAD_FOLDER"] = original
    shutil.rmtree(tmp_dir, ignore_errors=True)


def _usuario_cliente(db, cliente, username="cliente_test"):
    u = Usuario(username=username, nombre_completo="Cliente de prueba", rol="Cliente", cliente_id=cliente.id)
    u.set_password("clave123")
    db.session.add(u)
    db.session.commit()
    return u


class TestDocumentos:
    def test_subir_documento_aparece_en_historial(self, client, db, instalacion, usuario_jefe):
        login(client, usuario_jefe)
        data = {
            "titulo": "Informe de alineación láser",
            "archivo": (io.BytesIO(b"%PDF-1.4 contenido de prueba"), "informe.pdf"),
        }
        resp = client.post(
            f"/documentos/subir/{instalacion.id}",
            data=data,
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert Documento.query.count() == 1
        doc = Documento.query.first()
        assert doc.titulo == "Informe de alineación láser"
        assert doc.instalacion_id == instalacion.id

        resp = client.get(f"/historial/{instalacion.id}")
        assert "Informe de alineación láser".encode("utf-8") in resp.data
        assert b"Descargar" in resp.data

    def test_extension_no_permitida_no_crea_documento(self, client, db, instalacion, usuario_jefe):
        login(client, usuario_jefe)
        data = {
            "titulo": "Archivo raro",
            "archivo": (io.BytesIO(b"hola"), "notas.txt"),
        }
        client.post(
            f"/documentos/subir/{instalacion.id}", data=data, content_type="multipart/form-data", follow_redirects=True
        )
        assert Documento.query.count() == 0

    def test_titulo_vacio_no_crea_documento(self, client, db, instalacion, usuario_jefe):
        login(client, usuario_jefe)
        data = {
            "titulo": "",
            "archivo": (io.BytesIO(b"%PDF-1.4"), "informe.pdf"),
        }
        client.post(
            f"/documentos/subir/{instalacion.id}", data=data, content_type="multipart/form-data", follow_redirects=True
        )
        assert Documento.query.count() == 0

    def test_eliminar_documento(self, client, db, instalacion, usuario_jefe):
        login(client, usuario_jefe)
        data = {
            "titulo": "Para borrar",
            "archivo": (io.BytesIO(b"%PDF-1.4"), "borrar.pdf"),
        }
        client.post(
            f"/documentos/subir/{instalacion.id}", data=data, content_type="multipart/form-data", follow_redirects=True
        )
        doc = Documento.query.one()
        client.post(f"/documentos/{doc.id}/eliminar", follow_redirects=True)
        assert Documento.query.count() == 0

    def test_no_se_puede_descargar_documento_de_otra_empresa(self, client, db, usuario_jefe):
        otra_empresa = Empresa(nombre="Otra Empresa")
        db.session.add(otra_empresa)
        db.session.flush()
        otro_cliente = Cliente(nombre="Otro Cliente", empresa_id=otra_empresa.id, activo=True)
        db.session.add(otro_cliente)
        db.session.flush()
        otra_instalacion = Instalacion(cliente_id=otro_cliente.id, nombre="Otra Instalación")
        db.session.add(otra_instalacion)
        db.session.flush()
        documento = Documento(
            instalacion_id=otra_instalacion.id,
            titulo="Privado",
            nombre_archivo="2/2/2/documentos/privado.pdf",
            subido_por_id=usuario_jefe.id,
        )
        db.session.add(documento)
        db.session.commit()

        login(client, usuario_jefe)
        respuesta = client.get(f"/documentos/ver/{documento.nombre_archivo}")

        assert respuesta.status_code == 403

    def test_post_sin_csrf_se_rechaza_cuando_esta_activo(self, client, app):
        app.config["CSRF_ENABLED"] = True
        try:
            respuesta = client.post("/login", data={"username": "nadie", "password": "nada"})
            assert respuesta.status_code == 400
        finally:
            app.config["CSRF_ENABLED"] = False


class TestVisibilidadObservaciones:
    def _crear_observacion(self, db, instalacion, visibilidad, creado_por):
        obs = Observacion(
            instalacion_id=instalacion.id,
            clasificacion="Deficiencia crítica",
            descripcion="Contenido sensible de la observación",
            visibilidad=visibilidad,
            estado_revision="Pendiente",
            creado_por_id=creado_por.id,
        )
        db.session.add(obs)
        db.session.commit()
        return obs

    def test_observacion_interna_no_llega_al_portal(self, client, db, cliente, instalacion, usuario_jefe):
        obs = self._crear_observacion(db, instalacion, "Interna", usuario_jefe)
        obs.aprobar(usuario_jefe.id)
        db.session.commit()

        usuario_cliente = _usuario_cliente(db, cliente)
        login(client, usuario_cliente)

        resp = client.get("/portal/")
        assert b"Contenido sensible" not in resp.data

        resp = client.get("/portal/deficiencias/Deficiencia%20cr%C3%ADtica")
        assert b"Contenido sensible" not in resp.data

    def test_observacion_publica_aprobada_si_llega_al_portal(self, client, db, cliente, instalacion, usuario_jefe):
        obs = self._crear_observacion(db, instalacion, "Cliente", usuario_jefe)
        obs.aprobar(usuario_jefe.id)
        db.session.commit()

        usuario_cliente = _usuario_cliente(db, cliente)
        login(client, usuario_cliente)

        resp = client.get("/portal/deficiencias/Deficiencia%20cr%C3%ADtica")
        assert b"Contenido sensible" in resp.data

    def test_observacion_interna_visible_para_staff(self, client, db, instalacion, usuario_jefe):
        self._crear_observacion(db, instalacion, "Interna", usuario_jefe)
        login(client, usuario_jefe)

        resp = client.get(f"/historial/{instalacion.id}")
        assert "Contenido sensible".encode("utf-8") in resp.data
        assert "Interna".encode("utf-8") in resp.data
