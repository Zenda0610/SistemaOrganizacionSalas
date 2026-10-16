"""Parámetros de la demo aplicados al servidor, sin alterar el catálogo físico."""
from datetime import datetime
from unittest import mock

from app import carga_datos, chat, config, db, ia, reglas, solicitudes
from app.identidad import Identidad
from tests.base_prueba import BasePrueba
from tests.test_chat import ia_json


class PruebasConfiguracionDemo(BasePrueba):
    def setUp(self):
        super().setUp()
        self.assertTrue(carga_datos.cargar_datos()['ok'])
        self.profesor = Identidad('profesor-demo', 'profesor', 'desarrollo')
        self.coordinadora = Identidad('coordinadora-demo', 'coordinadora', 'desarrollo')

    def test_aula_preferida_configurable_y_alias_sin_id_fijo(self):
        aulas = [{'id': 'X', 'nombre': 'Azul', 'aforo': 10}, {'id': 'Y', 'nombre': 'Blanca', 'aforo': 12}]
        with mock.patch.object(config, 'AULA_PREFERIDA_ZONA_FRANCA', 'Sala Blanca'):
            self.assertFalse(reglas.es_azul(aulas[0]))
            self.assertTrue(reglas.es_azul(aulas[1]))
            self.assertEqual(reglas.ordenar_candidatos(aulas, True)[0]['id'], 'Y')

    def test_aforo_porcentaje_redondeo_y_limite_fisico(self):
        for porcentaje, esperado in ((50, 6), (33, 3), (150, 12), (-1, 0)):
            with mock.patch.object(config, 'PORCENTAJE_AFORO_MAXIMO', porcentaje):
                self.assertEqual(reglas.aforo_permitido({'aforo': 12}), esperado)

    def test_solicitud_y_aprobacion_revalidan_el_porcentaje(self):
        datos = solicitudes.NuevaSolicitud(espacio_id='E07', inicio='2035-01-08T08:00', fin='2035-01-08T09:00', personas=8, descripcion='Clase SER')
        solicitud = solicitudes.crear_solicitud(self.profesor, datos)
        with mock.patch.object(config, 'PORCENTAJE_AFORO_MAXIMO', 50):
            with self.assertRaises(solicitudes.ErrorSolicitud):
                solicitudes.crear_solicitud(self.profesor, datos)
            with self.assertRaises(solicitudes.ErrorSolicitud):
                solicitudes.aprobar_solicitud(solicitud['id'], self.coordinadora)
            disponibles = solicitudes.espacios_disponibles(datetime(2035, 1, 8, 8), datetime(2035, 1, 8, 9), 8)
            self.assertNotIn('E07', [e['id'] for e in disponibles])
        self.assertEqual(solicitudes.obtener_solicitud(solicitud['id'])['estado'], 'pendiente')

    def test_chat_revalida_porcentaje_al_confirmar(self):
        with mock.patch.object(ia, 'consultar_ia', return_value=ia_json('solicitar_aula', espacio='Sala Blanca', fecha='2035-01-08', inicio='08:00', fin='09:00', personas=8, descripcion='Clase SER')):
            propuesta = chat.procesar(self.profesor, 'Clase SER', 'config-demo-01')
        self.assertEqual(propuesta['datos'][0]['espacio_id'], 'E07')
        with mock.patch.object(config, 'PORCENTAJE_AFORO_MAXIMO', 50), mock.patch.object(ia, 'consultar_ia', return_value=ia_json('confirmar')):
            resultado = chat.procesar(self.profesor, 'Confirmo', 'config-demo-01')
        self.assertNotEqual(resultado['estado'], 'solicitud_creada')
        self.assertEqual(db.consultar('SELECT COUNT(*) AS total FROM solicitudes')[0]['total'], 0)
