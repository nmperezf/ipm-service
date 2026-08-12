from datetime import date, timedelta

from app.models import Contrato, ServicioContrato, Visita


def _crear_contrato(db, instalacion, fecha_inicio, fecha_fin, estado="Activo"):
    contrato = Contrato(
        instalacion_id=instalacion.id, nombre="Contrato Test",
        fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, estado=estado, activo=True,
    )
    db.session.add(contrato)
    db.session.commit()
    return contrato


class TestFechasOcurrenciaServicio:
    def test_frecuencia_mensual_en_contrato_de_un_anio(self, db, instalacion):
        inicio = date(2026, 1, 15)
        fin = inicio.replace(year=inicio.year + 1)
        contrato = _crear_contrato(db, instalacion, inicio, fin)
        servicio = ServicioContrato(contrato_id=contrato.id, nombre="Mantenimiento", frecuencia="mensual")
        db.session.add(servicio)
        db.session.commit()

        fechas = servicio.fechas_ocurrencia()

        assert len(fechas) == 12
        assert fechas[0] == inicio
        assert fechas[-1] == date(2026, 12, 15)
        # ninguna ocurrencia llega a pisar (ni superar) la fecha de fin del contrato
        assert all(f < fin for f in fechas)

    def test_frecuencia_anual_genera_una_sola_fecha(self, db, instalacion):
        inicio = date(2026, 3, 1)
        fin = inicio.replace(year=inicio.year + 1)
        contrato = _crear_contrato(db, instalacion, inicio, fin)
        servicio = ServicioContrato(contrato_id=contrato.id, nombre="Inspección anual", frecuencia="anual")
        db.session.add(servicio)
        db.session.commit()

        fechas = servicio.fechas_ocurrencia()

        assert fechas == [inicio]

    def test_frecuencia_semestral(self, db, instalacion):
        inicio = date(2026, 1, 1)
        fin = date(2027, 1, 1)
        contrato = _crear_contrato(db, instalacion, inicio, fin)
        servicio = ServicioContrato(contrato_id=contrato.id, nombre="Prueba semestral", frecuencia="semestral")
        db.session.add(servicio)
        db.session.commit()

        assert servicio.fechas_ocurrencia() == [date(2026, 1, 1), date(2026, 7, 1)]

    def test_fecha_inicio_propia_distinta_a_la_del_contrato(self, db, instalacion):
        """Un servicio puede arrancar más tarde que el contrato (ej. se
        agrega a mitad de año) — sus ocurrencias parten de su propia
        fecha_inicio, no de la del contrato, pero igual respetan el fin
        del contrato."""
        inicio_contrato = date(2026, 1, 1)
        fin_contrato = date(2027, 1, 1)
        contrato = _crear_contrato(db, instalacion, inicio_contrato, fin_contrato)
        servicio = ServicioContrato(
            contrato_id=contrato.id, nombre="Servicio agregado a mitad de año",
            frecuencia="trimestral", fecha_inicio=date(2026, 7, 1),
        )
        db.session.add(servicio)
        db.session.commit()

        assert servicio.fechas_ocurrencia() == [date(2026, 7, 1), date(2026, 10, 1)]


class TestActualizarEstadoPorVencimientoVisita:
    def test_fecha_pasada_pendiente_pasa_a_vencido(self, db, instalacion):
        visita = Visita(instalacion_id=instalacion.id, fecha=date.today() - timedelta(days=1), estado="Pendiente")
        visita.actualizar_estado_por_vencimiento()
        assert visita.estado == "Vencido"

    def test_fecha_futura_vencido_vuelve_a_pendiente(self, db, instalacion):
        """Si se reprograma una visita vencida para el futuro, vuelve a
        Pendiente sola (no queda 'Vencido' colgado)."""
        visita = Visita(instalacion_id=instalacion.id, fecha=date.today() + timedelta(days=5), estado="Vencido")
        visita.actualizar_estado_por_vencimiento()
        assert visita.estado == "Pendiente"

    def test_realizado_no_se_toca_aunque_la_fecha_sea_pasada(self, db, instalacion):
        visita = Visita(instalacion_id=instalacion.id, fecha=date.today() - timedelta(days=30), estado="Realizado")
        visita.actualizar_estado_por_vencimiento()
        assert visita.estado == "Realizado"

    def test_cancelado_no_se_toca(self, db, instalacion):
        visita = Visita(instalacion_id=instalacion.id, fecha=date.today() - timedelta(days=30), estado="Cancelado")
        visita.actualizar_estado_por_vencimiento()
        assert visita.estado == "Cancelado"


class TestActualizarEstadoPorVencimientoContrato:
    def test_fecha_fin_pasada_pasa_a_vencido(self, db, instalacion):
        contrato = _crear_contrato(
            db, instalacion, date.today() - timedelta(days=400), date.today() - timedelta(days=1)
        )
        contrato.actualizar_estado_por_vencimiento()
        assert contrato.estado == "Vencido"

    def test_fecha_fin_futura_queda_activo(self, db, instalacion):
        contrato = _crear_contrato(
            db, instalacion, date.today() - timedelta(days=30), date.today() + timedelta(days=335)
        )
        contrato.actualizar_estado_por_vencimiento()
        assert contrato.estado == "Activo"

    def test_renovado_no_se_toca(self, db, instalacion):
        contrato = _crear_contrato(
            db, instalacion, date.today() - timedelta(days=400), date.today() - timedelta(days=1), estado="Renovado"
        )
        contrato.actualizar_estado_por_vencimiento()
        assert contrato.estado == "Renovado"
