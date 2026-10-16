"""Panel comercial: costo calculado en el servidor, franjas libres y prioridad académica sobre lo comercial."""
from datetime import datetime

from fastapi.testclient import TestClient

from app import carga_datos, coordinacion, db, solicitudes
from app.main import app
from tests.base_prueba import BasePrueba

FRANJA = {'inicio': '2030-01-10T14:00', 'fin': '2030-01-10T16:00'}


class PruebasPanelComercial(BasePrueba):
    def setUp(self):
        super().setUp()
        self.assertTrue(carga_datos.cargar_datos()['ok'])
        with db.transaccion() as con:
            con.execute("UPDATE espacios SET tarifa_hora = 50000 WHERE id = 'E02'")

    def api(self, rol, metodo, ruta, **datos):
        self.usar_identidad(rol, f'dev-{rol}')
        with TestClient(app) as cliente:
            return getattr(cliente, metodo)('/api' + ruta, **datos)

    def pedir(self, rol, espacio='E02', descripcion='Evento de la empresa', **extra):
        cuerpo = {'espacio_id': espacio, **FRANJA, 'personas': 5, 'descripcion': descripcion, **extra}
        return self.api(rol, 'post', '/solicitudes', json=cuerpo)

    def test_costo_calculado_en_el_servidor(self):
        respuesta = self.pedir('empresa')
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.json()['costo'], {'tarifa_hora': 50000.0, 'horas': 2.0, 'total': 100000.0, 'moneda': 'COP'})
        self.assertEqual(respuesta.json()['estado_pago'], 'pendiente')
        # El navegador no puede enviar el costo.
        self.assertEqual(self.pedir('empresa', costo=1).status_code, 422)

    def test_sin_tarifa_el_costo_queda_por_definir(self):
        respuesta = self.pedir('estudiante', espacio='E03')
        self.assertEqual(respuesta.status_code, 201)
        self.assertIsNone(respuesta.json()['costo']['tarifa_hora'])
        self.assertIsNone(respuesta.json()['costo']['total'])

    def test_disponibilidad_comercial_incluye_costo_y_excluye_franjas_academicas(self):
        self.assertEqual(self.pedir('profesor', espacio='E03', descripcion='Clase de SER').status_code, 201)
        inicio, fin = datetime(2030, 1, 10, 14), datetime(2030, 1, 10, 16)
        comercial = {e['id']: e for e in solicitudes.espacios_disponibles(inicio, fin, 5, comercial=True)}
        self.assertNotIn('E03', comercial)
        self.assertEqual(comercial['E02']['costo']['total'], 100000.0)
        self.assertIn('E03', {e['id'] for e in solicitudes.espacios_disponibles(inicio, fin, 5)})

    def test_comercial_rechazada_sobre_franja_academica(self):
        self.assertEqual(self.pedir('profesor', descripcion='Clase de inglés').status_code, 201)
        respuesta = self.pedir('empresa')
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.json()['codigo'], 'franja_no_libre')

    def test_academica_gana_sobre_comercial_pendiente(self):
        comercial = self.pedir('empresa').json()['id']
        academica = self.pedir('profesor', descripcion='Clase de SER').json()['id']
        self.assertEqual(self.api('coordinadora', 'post', f'/solicitudes/{academica}/aprobar').status_code, 200)
        respuesta = self.api('coordinadora', 'post', f'/solicitudes/{comercial}/aprobar')
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.json()['codigo'], 'bloqueada_por_academica')
        propia = next(f for f in self.api('empresa', 'get', '/solicitudes').json() if f['id'] == comercial)
        self.assertEqual(propia['estado'], 'pendiente')
        self.assertIn('académica aprobada', propia['bloqueo'])

    def test_comercial_aprobada_no_se_desplaza_y_se_escala(self):
        comercial = self.pedir('empresa').json()['id']
        self.assertEqual(self.api('coordinadora', 'post', f'/solicitudes/{comercial}/aprobar').status_code, 200)
        academica = self.pedir('profesor', descripcion='Clase de SER').json()['id']
        respuesta = self.api('coordinadora', 'post', f'/solicitudes/{academica}/aprobar')
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.json()['codigo'], 'comercial_aprobada')
        estados = {f['id']: f['estado'] for f in db.consultar('SELECT id, estado FROM solicitudes')}
        self.assertEqual(estados, {comercial: 'aprobada', academica: 'pendiente'})
        cruce = [n for n in coordinacion.resumen()['notificaciones'] if n['tipo'] == 'conflicto_comercial']
        self.assertEqual(len(cruce), 1)
        self.assertEqual(cruce[0]['nivel'], 'importante')

    def test_comercial_no_aprueba_ni_ve_datos(self):
        academica = self.pedir('profesor', descripcion='Clase de SER').json()['id']
        for rol in ('empresa', 'estudiante'):
            with self.subTest(rol=rol):
                self.assertEqual(self.api(rol, 'post', f'/solicitudes/{academica}/aprobar').status_code, 403)
                for ruta in ('/calidad-datos', '/cohortes', '/coordinacion/resumen'):
                    self.assertEqual(self.api(rol, 'get', ruta).status_code, 403)

    def test_carga_valida_la_tarifa(self):
        (self.carpeta_datos / 'espacios.csv').write_text(
            'id,nombre,tipo,aforo,estado,tarifa_hora\n'
            'E01,Auditorio,auditorio,100,activo,\nE02,Cosmos,salon,25,activo,80000\n'
            'E03,Skylab,salon,20,activo,-5\nE04,Sputnik,salon,38,activo,gratis\n', encoding='utf-8')
        resultado = carga_datos.cargar_datos()
        self.assertTrue(resultado['ok'])
        tarifas = {f['id']: f['tarifa_hora'] for f in db.consultar('SELECT id, tarifa_hora FROM espacios')}
        self.assertEqual(tarifas.get('E01', 'falta'), None)
        self.assertEqual(tarifas['E02'], 80000.0)
        self.assertNotIn('E03', tarifas)
        self.assertNotIn('E04', tarifas)
        self.assertGreaterEqual(self.contar('registros_rechazados'), 2)

    def test_api_disponibilidad_muestra_costo_solo_a_comerciales(self):
        parametros = {'inicio': FRANJA['inicio'], 'fin': FRANJA['fin'], 'personas': 5}
        aulas = {a['id']: a for a in self.api('empresa', 'get', '/disponibilidad', params=parametros).json()}
        self.assertEqual(aulas['E02']['costo']['total'], 100000.0)
        self.assertNotIn('costo', self.api('profesor', 'get', '/disponibilidad', params=parametros).json()[0])
