"""Edición y cancelación de solicitudes; cambios de reservas aprobadas revisados por la coordinadora."""
import json
from unittest import mock

from fastapi.testclient import TestClient

from app import carga_datos, chat, db, ia
from app.identidad import Identidad
from app.main import app
from tests.base_prueba import BasePrueba

DIA = '2030-01-10'


class PruebasCambios(BasePrueba):
    def setUp(self):
        super().setUp()
        self.assertTrue(carga_datos.cargar_datos()['ok'])
        self.ia = mock.patch.object(ia, 'consultar_ia', return_value={'ok': False, 'error': 'caída'})
        self.ia.start()
        self.addCleanup(self.ia.stop)

    def api(self, rol, metodo, ruta, usuario=None, **datos):
        self.usar_identidad(rol, usuario or f'dev-{rol}')
        with TestClient(app) as cliente:
            return getattr(cliente, metodo)('/api' + ruta, **datos)

    def crear(self, rol='profesor', espacio='E02', inicio='14:00', fin='16:00', aprobar=False, descripcion='Clase de SER'):
        cuerpo = {'espacio_id': espacio, 'inicio': f'{DIA}T{inicio}', 'fin': f'{DIA}T{fin}', 'personas': 5, 'descripcion': descripcion}
        solicitud = self.api(rol, 'post', '/solicitudes', json=cuerpo).json()['id']
        if aprobar:
            self.assertEqual(self.api('coordinadora', 'post', f'/solicitudes/{solicitud}/aprobar').status_code, 200)
        return solicitud

    def estado(self, solicitud):
        return db.consultar('SELECT espacio_id, inicio, estado, cancelada_por FROM solicitudes WHERE id = ?', (solicitud,))[0]

    def test_cancelar_pendiente_y_aprobada_libera_la_franja(self):
        pendiente, aprobada = self.crear(), self.crear(espacio='E03', aprobar=True)
        for solicitud in (pendiente, aprobada):
            self.assertEqual(self.api('profesor', 'post', f'/solicitudes/{solicitud}/cancelar').status_code, 200)
            self.assertEqual(self.estado(solicitud)['cancelada_por'], 'dev-profesor')
        self.assertIn('E03', {e['id'] for e in self.api('profesor', 'get', '/disponibilidad',
                                                          params={'inicio': f'{DIA}T14:00', 'fin': f'{DIA}T16:00'}).json()})

    def test_editar_pendiente_valida_e_invalida(self):
        solicitud = self.crear()
        valida = self.api('profesor', 'post', f'/solicitudes/{solicitud}/cambios', json={'inicio': f'{DIA}T09:00', 'fin': f'{DIA}T10:00'})
        self.assertEqual(valida.json()['tipo'], 'edicion')
        self.assertEqual(self.estado(solicitud)['inicio'], f'{DIA} 09:00')
        invalida = self.api('profesor', 'post', f'/solicitudes/{solicitud}/cambios', json={'personas': 5000})
        self.assertEqual(invalida.status_code, 409)
        self.assertIn('aforo', invalida.json()['mensaje'])

    def test_cambio_de_aprobada_conserva_reserva_y_guarda_veredicto_sin_ia(self):
        solicitud = self.crear(aprobar=True)
        cambio = self.api('profesor', 'post', f'/solicitudes/{solicitud}/cambios', json={'inicio': f'{DIA}T18:00', 'fin': f'{DIA}T19:00'}).json()
        self.assertEqual(cambio['tipo'], 'cambio')
        self.assertTrue(cambio['cambio']['factible'])
        self.assertEqual(cambio['cambio']['analisis_ia'], 'Análisis de IA no disponible')
        self.assertEqual(self.estado(solicitud)['inicio'], f'{DIA} 14:00')  # la reserva sigue vigente
        segundo = self.api('profesor', 'post', f'/solicitudes/{solicitud}/cambios', json={'personas': 4})
        self.assertEqual(segundo.json()['codigo'], 'cambio_pendiente_existente')

    def test_aprobar_factible_aplica_y_no_factible_o_descartado_no_cambia(self):
        primera, segunda = self.crear(aprobar=True), self.crear(espacio='E03', aprobar=True)
        aplicable = self.api('profesor', 'post', f'/solicitudes/{primera}/cambios', json={'inicio': f'{DIA}T18:00', 'fin': f'{DIA}T19:00'}).json()['cambio']['id']
        self.assertEqual(self.api('coordinadora', 'post', f'/cambios/{aplicable}/aprobar').json()['estado'], 'aprobado')
        self.assertEqual(self.estado(primera)['inicio'], f'{DIA} 18:00')
        # Pedido factible que deja de serlo: otra reserva ocupa la franja antes de aprobar.
        tardio = self.api('profesor', 'post', f'/solicitudes/{segunda}/cambios', json={'inicio': f'{DIA}T20:00', 'fin': f'{DIA}T21:00'}).json()['cambio']['id']
        self.crear(rol='administrativo', espacio='E03', inicio='20:00', fin='21:00', aprobar=True)
        respuesta = self.api('coordinadora', 'post', f'/cambios/{tardio}/aprobar')
        self.assertEqual(respuesta.json()['codigo'], 'cambio_no_factible')
        self.assertEqual(self.estado(segunda)['inicio'], f'{DIA} 14:00')
        descartado = self.api('coordinadora', 'post', f'/cambios/{tardio}/descartar', json={'motivo': 'Franja ocupada'})
        self.assertEqual(descartado.json()['estado'], 'descartado')
        self.assertEqual(self.estado(segunda)['inicio'], f'{DIA} 14:00')

    def test_permisos(self):
        solicitud = self.crear(aprobar=True)
        self.assertEqual(self.api('profesor', 'post', f'/solicitudes/{solicitud}/cancelar', usuario='otro-profesor').status_code, 403)
        cambio = self.api('profesor', 'post', f'/solicitudes/{solicitud}/cambios', json={'personas': 4}).json()['cambio']['id']
        self.assertEqual(self.api('profesor', 'post', f'/cambios/{cambio}/aprobar').status_code, 403)
        self.assertEqual(self.api('coordinadora', 'post', f'/cambios/{cambio}/aprobar', usuario='dev-profesor').json()['codigo'],
                         'autorrevision_no_permitida')

    def test_comercial_no_toma_franja_academica(self):
        self.crear(espacio='E03')  # clase de SER pendiente en E03
        comercial = self.crear(rol='empresa', espacio='E02', descripcion='Evento')
        respuesta = self.api('empresa', 'post', f'/solicitudes/{comercial}/cambios', json={'espacio_id': 'E03'})
        self.assertEqual(respuesta.status_code, 409)
        self.assertIn('académica', respuesta.json()['mensaje'])

    def test_chat_propone_y_ejecuta_el_cambio_solo_al_confirmar(self):
        solicitud = self.crear(aprobar=True)
        profesor = Identidad('dev-profesor', 'profesor', 'desarrollo')
        acciones = [{'accion': 'cambiar_solicitud', 'parametros': {'solicitud_id': solicitud, 'inicio': '18:00', 'fin': '19:00'}},
                    {'accion': 'confirmar', 'parametros': {}}]
        respuestas = []
        for accion in acciones:
            with mock.patch.object(ia, 'consultar_ia', return_value={'ok': True, 'texto': json.dumps(accion)}):
                respuestas.append(chat.procesar(profesor, 'mueve mi reserva', 'conversacion-cambio'))
            if len(respuestas) == 1:
                self.assertEqual(self.contar('cambios_solicitud'), 0)  # nada sin confirmar
        self.assertEqual([r['estado'] for r in respuestas], ['propuesta', 'cambio_enviado'])
        self.assertEqual(self.contar('cambios_solicitud'), 1)
