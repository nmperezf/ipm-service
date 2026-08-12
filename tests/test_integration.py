from datetime import datetime, timedelta

from app.models import Observacion, Presupuesto


def login(client, usuario, password="clave123"):
    return client.post("/login", data={"username": usuario.username, "password": password}, follow_redirects=True)


class TestLoginObligatorio:
    def test_ruta_protegida_sin_sesion_redirige_a_login(self, client):
        resp = client.get("/clientes/")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_credenciales_invalidas_no_inician_sesion(self, client, usuario_jefe):
        resp = client.post(
            "/login", data={"username": usuario_jefe.username, "password": "incorrecta"}, follow_redirects=True
        )
        assert resp.status_code == 200
        assert "incorrectos".encode() in resp.data

    def test_login_correcto_permite_entrar(self, client, usuario_jefe):
        resp = login(client, usuario_jefe)
        assert resp.status_code == 200
        resp = client.get("/clientes/")
        assert resp.status_code == 200


class TestErrorHandlers:
    def test_404_en_ruta_inexistente(self, client, usuario_jefe):
        login(client, usuario_jefe)
        resp = client.get("/esto-no-existe-en-ningun-lado")
        assert resp.status_code == 404
        assert "no encontrada".encode() in resp.data.lower() or "no encontr".encode() in resp.data.lower()


class TestPermisosPorRol:
    def test_tecnico_no_puede_listar_usuarios(self, client, usuario_tecnico):
        login(client, usuario_tecnico)
        resp = client.get("/usuarios/")
        assert resp.status_code == 403

    def test_jefe_si_puede_listar_usuarios(self, client, usuario_jefe):
        login(client, usuario_jefe)
        resp = client.get("/usuarios/")
        assert resp.status_code == 200


class TestDashboardPorRol:
    def test_tecnico_ve_el_dashboard_operativo(self, client, usuario_tecnico):
        login(client, usuario_tecnico)
        resp = client.get("/")
        assert resp.status_code == 200

    def test_jefe_ve_el_dashboard_operativo(self, client, usuario_jefe):
        login(client, usuario_jefe)
        resp = client.get("/")
        assert resp.status_code == 200


class TestPaginacionPresupuestos:
    def _crear_presupuestos(self, db, empresa, instalacion, usuario, cantidad):
        for i in range(cantidad):
            obs = Observacion(
                instalacion_id=instalacion.id, clasificacion="Deficiencia crítica",
                descripcion=f"Deficiencia {i}", resuelto=False, creado_por_id=usuario.id,
            )
            db.session.add(obs)
            db.session.flush()
            db.session.add(Presupuesto(
                codigo=f"PRESUP-2026-{i:04d}", empresa_id=empresa.id, observacion_id=obs.id,
                estado="Pendiente", fecha_creacion=datetime.utcnow() - timedelta(days=i),
            ))
        db.session.commit()

    def test_lista_sin_filtro_no_pagina(self, client, db, empresa, instalacion, usuario_jefe):
        self._crear_presupuestos(db, empresa, instalacion, usuario_jefe, 30)
        login(client, usuario_jefe)
        resp = client.get("/presupuestos/")
        assert resp.status_code == 200
        assert "Página 1 de".encode() not in resp.data

    def test_filtro_por_estado_pagina_de_a_25(self, client, db, empresa, instalacion, usuario_jefe):
        self._crear_presupuestos(db, empresa, instalacion, usuario_jefe, 30)
        login(client, usuario_jefe)
        resp = client.get("/presupuestos/?estado=Pendiente")
        assert resp.status_code == 200
        assert "Página 1 de 2".encode() in resp.data

    def test_segunda_pagina_muestra_el_resto(self, client, db, empresa, instalacion, usuario_jefe):
        self._crear_presupuestos(db, empresa, instalacion, usuario_jefe, 30)
        login(client, usuario_jefe)
        resp = client.get("/presupuestos/?estado=Pendiente&pagina=2")
        assert resp.status_code == 200
        assert "Página 2 de 2".encode() in resp.data

    def test_pagina_fuera_de_rango_no_rompe(self, client, db, empresa, instalacion, usuario_jefe):
        self._crear_presupuestos(db, empresa, instalacion, usuario_jefe, 5)
        login(client, usuario_jefe)
        resp = client.get("/presupuestos/?estado=Pendiente&pagina=999")
        assert resp.status_code == 200
