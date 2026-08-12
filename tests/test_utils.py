from datetime import date

import pytest

from app.utils import calcular_presion_ajustada, parse_fecha, validar_nfpa25


class TestParseFecha:
    def test_valor_valido(self):
        assert parse_fecha("2026-03-15") == date(2026, 3, 15)

    def test_valor_vacio_devuelve_default(self):
        hoy = date.today()
        assert parse_fecha("", hoy) == hoy
        assert parse_fecha(None, hoy) == hoy

    def test_valor_vacio_sin_default_devuelve_none(self):
        assert parse_fecha("") is None
        assert parse_fecha(None) is None

    def test_formato_invalido_propaga_value_error_por_defecto(self):
        with pytest.raises(ValueError):
            parse_fecha("15/03/2026")

    def test_formato_invalido_silencioso_devuelve_default(self):
        hoy = date.today()
        assert parse_fecha("15/03/2026", hoy, silencioso=True) == hoy

    def test_formato_invalido_silencioso_sin_default(self):
        assert parse_fecha("no-es-fecha", silencioso=True) is None


class TestCalcularPresionAjustada:
    def test_rpm_igual_no_ajusta(self):
        assert calcular_presion_ajustada(100.0, 1750, 1750) == 100.0

    def test_rpm_ensayada_menor_ajusta_hacia_arriba(self):
        # P ajustada = P_medida * (rpm_fabrica / rpm_ensayada)^2
        resultado = calcular_presion_ajustada(100.0, 1000, 2000)
        assert resultado == 400.0

    def test_rpm_ensayada_cero_devuelve_presion_sin_ajustar(self):
        assert calcular_presion_ajustada(85.3, 0, 1750) == 85.3


class TestValidarNfpa25:
    def test_ensayo_que_cumple_los_3_criterios(self):
        # Presiones netas ajustadas [0%, 50%, 100%, 150%] vs. curva de fábrica
        ajustadas = [140.0, 120.0, 100.0, 70.0]
        fabrica = [150.0, 125.0, 105.0, 75.0]
        resultado = validar_nfpa25(ajustadas, fabrica)
        assert resultado["criterio_1"]["paso"] is True
        assert resultado["criterio_2"]["paso"] is True
        assert resultado["criterio_3"]["paso"] is True

    def test_criterio_1_falla_si_presion_a_cero_es_excesiva(self):
        # P@0% > 1.4 * P@100% -> falla el criterio de shutoff
        ajustadas = [200.0, 120.0, 100.0, 70.0]
        fabrica = [150.0, 125.0, 105.0, 75.0]
        resultado = validar_nfpa25(ajustadas, fabrica)
        assert resultado["criterio_1"]["paso"] is False

    def test_criterio_2_falla_si_presion_a_100_muy_por_debajo_de_fabrica(self):
        ajustadas = [130.0, 110.0, 90.0, 60.0]
        fabrica = [150.0, 125.0, 105.0, 75.0]
        resultado = validar_nfpa25(ajustadas, fabrica)
        assert resultado["criterio_2"]["paso"] is False

    def test_criterio_3_falla_si_presion_a_150_cae_demasiado(self):
        ajustadas = [140.0, 120.0, 100.0, 50.0]
        fabrica = [150.0, 125.0, 105.0, 75.0]
        resultado = validar_nfpa25(ajustadas, fabrica)
        assert resultado["criterio_3"]["paso"] is False
