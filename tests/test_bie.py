from datetime import date, timedelta

from app.models import (
    Equipo,
    InspeccionBie,
    ItemVisita,
    Manguera,
    Observacion,
    PruebaHidrostatica,
    ReubicacionManguera,
    Visita,
)
from tests.conftest import login


def _crear_bie(db, instalacion, nombre="BIE-01", ubicacion="Planta baja"):
    equipo = Equipo(instalacion_id=instalacion.id, tipo="BIE", nombre=nombre, ubicacion=ubicacion, activo=True)
    db.session.add(equipo)
    db.session.commit()
    return equipo


def _crear_manguera(db, instalacion, equipo=None, numero_serie="M-001", diametro="25mm"):
    m = Manguera(
        instalacion_id=instalacion.id,
        equipo_id=equipo.id if equipo else None,
        numero_serie=numero_serie,
        diametro=diametro,
        lugar_origen=equipo.ubicacion if equipo else "Pañol de reserva",
        activa=True,
    )
    db.session.add(m)
    db.session.commit()
    return m


class TestMangueraPropiedades:
    def test_lugar_actual_usa_ubicacion_del_equipo(self, db, instalacion):
        equipo = _crear_bie(db, instalacion)
        m = _crear_manguera(db, instalacion, equipo=equipo)
        assert m.lugar_actual == equipo.ubicacion

    def test_lugar_actual_usa_ubicacion_libre_sin_equipo(self, db, instalacion):
        m = Manguera(instalacion_id=instalacion.id, numero_serie="M-002", diametro="45mm", lugar_origen="Taller / en prueba", ubicacion_libre="Taller / en prueba")
        db.session.add(m)
        db.session.commit()
        assert m.lugar_actual == "Taller / en prueba"

    def test_reubicada_compara_contra_origen(self, db, instalacion):
        equipo = _crear_bie(db, instalacion)
        m = _crear_manguera(db, instalacion, equipo=equipo)
        assert m.reubicada is False
        m.lugar_origen = "Otro lugar distinto"
        assert m.reubicada is True

    def test_estado_ph_sin_probar(self, db, instalacion):
        m = _crear_manguera(db, instalacion)
        assert m.estado_ph == "Sin probar"

    def test_estado_ph_en_prueba_cuando_esta_en_taller(self, db, instalacion):
        m = Manguera(
            instalacion_id=instalacion.id, numero_serie="M-003", diametro="25mm",
            lugar_origen="Planta baja", ubicacion_libre="Taller / en prueba",
            fecha_vencimiento_ph=date.today() - timedelta(days=10),
        )
        db.session.add(m)
        db.session.commit()
        assert m.estado_ph == "En prueba"

    def test_estado_ph_vigente_por_vencer_y_vencida(self, db, instalacion):
        m = _crear_manguera(db, instalacion)
        m.fecha_vencimiento_ph = date.today() + timedelta(days=200)
        assert m.estado_ph == "Vigente"
        m.fecha_vencimiento_ph = date.today() + timedelta(days=10)
        assert m.estado_ph == "Por vencer"
        m.fecha_vencimiento_ph = date.today() - timedelta(days=1)
        assert m.estado_ph == "Vencida"


class TestFichaBie:
    def test_guardar_ficha_apta_no_genera_observacion(self, client, db, instalacion, usuario_jefe):
        equipo = _crear_bie(db, instalacion)
        login(client, usuario_jefe)

        resp = client.post(
            f"/equipos/{equipo.id}/ficha-bie",
            data={"fecha": date.today().isoformat(), "veredicto": "Apta / operativa", "dictamen": "Todo OK"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert InspeccionBie.query.count() == 1
        inspeccion = InspeccionBie.query.first()
        assert inspeccion.veredicto == "Apta / operativa"
        assert inspeccion.observacion_id is None
        assert Observacion.query.count() == 0

    def test_guardar_ficha_fuera_de_servicio_genera_observacion_critica(self, client, db, instalacion, usuario_jefe):
        equipo = _crear_bie(db, instalacion)
        login(client, usuario_jefe)

        client.post(
            f"/equipos/{equipo.id}/ficha-bie",
            data={"fecha": date.today().isoformat(), "veredicto": "Fuera de servicio", "dictamen": "Válvula trabada"},
            follow_redirects=True,
        )
        inspeccion = InspeccionBie.query.first()
        assert inspeccion.observacion_id is not None
        assert inspeccion.observacion.clasificacion == "Deficiencia crítica"
        assert inspeccion.observacion.estado_revision == "Pendiente"

    def test_guardar_ficha_con_observaciones_genera_deficiencia_no_critica(self, client, db, instalacion, usuario_jefe):
        equipo = _crear_bie(db, instalacion)
        login(client, usuario_jefe)

        client.post(
            f"/equipos/{equipo.id}/ficha-bie",
            data={"fecha": date.today().isoformat(), "veredicto": "Con observaciones", "dictamen": "Gabinete dañado"},
            follow_redirects=True,
        )
        inspeccion = InspeccionBie.query.first()
        assert inspeccion.observacion.clasificacion == "Deficiencia no crítica"

    def test_diametro_incompatible_genera_observacion_extra(self, client, db, instalacion, usuario_jefe):
        equipo = _crear_bie(db, instalacion)
        _crear_manguera(db, instalacion, equipo=equipo, diametro="45mm")
        login(client, usuario_jefe)

        client.post(
            f"/equipos/{equipo.id}/ficha-bie",
            data={"fecha": date.today().isoformat(), "veredicto": "Apta / operativa", "diametro_nominal": "25mm"},
            follow_redirects=True,
        )
        assert Observacion.query.filter_by(clasificacion="Deficiencia no crítica").count() == 1
        assert "diámetro" in Observacion.query.first().descripcion.lower() or "Diámetro" in Observacion.query.first().descripcion

    def test_ficha_con_item_marca_item_cumplido(self, client, db, instalacion, usuario_jefe):
        equipo = _crear_bie(db, instalacion)
        visita = Visita(instalacion_id=instalacion.id, fecha=date.today())
        db.session.add(visita)
        db.session.flush()
        item = ItemVisita(visita_id=visita.id, equipo_id=equipo.id, estado="Pendiente")
        db.session.add(item)
        db.session.commit()
        login(client, usuario_jefe)

        client.post(
            f"/equipos/{equipo.id}/ficha-bie?item_id={item.id}",
            data={"fecha": date.today().isoformat(), "veredicto": "Apta / operativa", "item_id": str(item.id)},
            follow_redirects=True,
        )
        db.session.refresh(item)
        assert item.estado == "Cumplido"
        assert InspeccionBie.query.first().item_visita_id == item.id


class TestMangueraRutas:
    def test_alta_manguera_asignada_a_bie(self, client, db, instalacion, usuario_jefe):
        equipo = _crear_bie(db, instalacion)
        login(client, usuario_jefe)

        resp = client.post(
            f"/instalaciones/{instalacion.id}/mangueras/nueva",
            data={"numero_serie": "M-100", "diametro": "25mm", "equipo_id": str(equipo.id)},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        manguera = Manguera.query.filter_by(numero_serie="M-100").first()
        assert manguera is not None
        assert manguera.lugar_origen == equipo.ubicacion

    def test_ph_rechazada_genera_observacion_y_actualiza_vencimiento(self, client, db, instalacion, usuario_jefe):
        equipo = _crear_bie(db, instalacion)
        manguera = _crear_manguera(db, instalacion, equipo=equipo)
        login(client, usuario_jefe)

        fecha = date.today().isoformat()
        client.post(
            f"/instalaciones/{instalacion.id}/mangueras/{manguera.id}/ph",
            data={"fecha": fecha, "resultado": "Rechazada", "presion_aplicada": "15", "tiempo_minutos": "5"},
            follow_redirects=True,
        )
        db.session.refresh(manguera)
        assert manguera.resultado_ultima_ph == "Rechazada"
        assert manguera.fecha_vencimiento_ph == date.today().replace(year=date.today().year + 5)
        assert PruebaHidrostatica.query.count() == 1
        assert Observacion.query.filter_by(clasificacion="Deficiencia crítica").count() == 1

    def test_ph_aprobada_no_genera_observacion(self, client, db, instalacion, usuario_jefe):
        equipo = _crear_bie(db, instalacion)
        manguera = _crear_manguera(db, instalacion, equipo=equipo)
        login(client, usuario_jefe)

        client.post(
            f"/instalaciones/{instalacion.id}/mangueras/{manguera.id}/ph",
            data={"fecha": date.today().isoformat(), "resultado": "Aprobada"},
            follow_redirects=True,
        )
        assert Observacion.query.count() == 0

    def test_editar_actualiza_datos_propios_sin_tocar_ubicacion(self, client, db, instalacion, usuario_jefe):
        equipo = _crear_bie(db, instalacion)
        manguera = _crear_manguera(db, instalacion, equipo=equipo)
        login(client, usuario_jefe)

        client.post(
            f"/instalaciones/{instalacion.id}/mangueras/{manguera.id}/editar",
            data={"numero_serie": "M-EDITADA", "diametro": "45mm", "material": "Caucho / goma"},
            follow_redirects=True,
        )
        db.session.refresh(manguera)
        assert manguera.numero_serie == "M-EDITADA"
        assert manguera.diametro == "45mm"
        assert manguera.equipo_id == equipo.id

    def test_eliminar_sin_password_no_borra(self, client, db, instalacion, usuario_jefe):
        equipo = _crear_bie(db, instalacion)
        manguera = _crear_manguera(db, instalacion, equipo=equipo)
        login(client, usuario_jefe)

        client.post(
            f"/instalaciones/{instalacion.id}/mangueras/{manguera.id}/eliminar",
            data={},
            follow_redirects=True,
        )
        assert Manguera.query.count() == 1

    def test_eliminar_con_password_correcta_borra(self, client, db, instalacion, usuario_jefe):
        equipo = _crear_bie(db, instalacion)
        manguera = _crear_manguera(db, instalacion, equipo=equipo)
        login(client, usuario_jefe)

        client.post(
            f"/instalaciones/{instalacion.id}/mangueras/{manguera.id}/eliminar",
            data={"password": "clave123"},
            follow_redirects=True,
        )
        assert Manguera.query.count() == 0

    def test_reubicar_actualiza_equipo_y_preserva_lugar_origen(self, client, db, instalacion, usuario_jefe):
        origen_equipo = _crear_bie(db, instalacion, nombre="BIE-01", ubicacion="Planta baja")
        destino_equipo = _crear_bie(db, instalacion, nombre="BIE-02", ubicacion="Planta alta")
        manguera = _crear_manguera(db, instalacion, equipo=origen_equipo)
        lugar_origen_original = manguera.lugar_origen
        login(client, usuario_jefe)

        client.post(
            f"/instalaciones/{instalacion.id}/mangueras/{manguera.id}/reubicar",
            data={"destino_equipo_id": str(destino_equipo.id), "motivo": "prueba"},
            follow_redirects=True,
        )
        db.session.refresh(manguera)
        assert manguera.equipo_id == destino_equipo.id
        assert manguera.lugar_origen == lugar_origen_original
        assert ReubicacionManguera.query.count() == 1
        reubicacion = ReubicacionManguera.query.first()
        assert reubicacion.origen == "Planta baja"
        assert reubicacion.destino == "Planta alta"

    def test_reubicar_a_destino_especial(self, client, db, instalacion, usuario_jefe):
        equipo = _crear_bie(db, instalacion)
        manguera = _crear_manguera(db, instalacion, equipo=equipo)
        login(client, usuario_jefe)

        client.post(
            f"/instalaciones/{instalacion.id}/mangueras/{manguera.id}/reubicar",
            data={"destino_libre": "Pañol de reserva"},
            follow_redirects=True,
        )
        db.session.refresh(manguera)
        assert manguera.equipo_id is None
        assert manguera.ubicacion_libre == "Pañol de reserva"

    def test_historial_une_pruebas_y_reubicaciones(self, client, db, instalacion, usuario_jefe):
        equipo = _crear_bie(db, instalacion)
        manguera = _crear_manguera(db, instalacion, equipo=equipo)
        login(client, usuario_jefe)

        client.post(
            f"/instalaciones/{instalacion.id}/mangueras/{manguera.id}/ph",
            data={"fecha": date.today().isoformat(), "resultado": "Aprobada"},
        )
        client.post(
            f"/instalaciones/{instalacion.id}/mangueras/{manguera.id}/nota",
            data={"texto": "Reempalme de racor"},
        )
        resp = client.get(
            f"/instalaciones/{instalacion.id}/mangueras/{manguera.id}/historial",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert b"Reempalme de racor" in resp.data
        assert "Prueba hidrostática".encode("utf-8") in resp.data

    def test_lista_calcula_stats_por_estado_ph(self, client, db, instalacion, usuario_jefe):
        equipo = _crear_bie(db, instalacion)
        vigente = _crear_manguera(db, instalacion, equipo=equipo, numero_serie="M-V")
        vigente.fecha_vencimiento_ph = date.today() + timedelta(days=400)
        vencida = _crear_manguera(db, instalacion, equipo=equipo, numero_serie="M-X")
        vencida.fecha_vencimiento_ph = date.today() - timedelta(days=5)
        db.session.commit()
        login(client, usuario_jefe)

        resp = client.get(f"/instalaciones/{instalacion.id}/mangueras/")
        assert resp.status_code == 200


class TestVisitaDispatchBie:
    def test_item_suelto_de_bie_ofrece_cargar_ficha(self, client, db, instalacion, usuario_jefe):
        equipo = _crear_bie(db, instalacion)
        visita = Visita(instalacion_id=instalacion.id, fecha=date.today())
        db.session.add(visita)
        db.session.flush()
        item = ItemVisita(visita_id=visita.id, equipo_id=equipo.id, estado="Pendiente")
        db.session.add(item)
        db.session.commit()
        login(client, usuario_jefe)

        resp = client.get(f"/visitas/{visita.id}")
        assert resp.status_code == 200
        assert b"Cargar ficha BIE" in resp.data
