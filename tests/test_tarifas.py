"""Tarifa por hora editable por la coordinadora: permisos, validación, persistencia y cotizaciones congeladas."""
from fastapi.testclient import TestClient

from app import carga_datos, coordinacion, db
from app.main import app
from tests.base_prueba import BasePrueba

FRANJA = {'inicio': '2030-01-10T14:00', 'fin': '2030-01-10T16:00'}


class PruebasTarifas(BasePrueba):
    def setUp(self):
        super().setUp()
        self.assertTrue(carga_datos.cargar_datos()['ok'])

    def api(self, rol, metodo, ruta, **datos):
        self.usar_identidad(rol, f'dev-{rol}')
        with TestClient(app) as cliente:
            return getattr(cliente, metodo)('/api' + ruta, **datos)

    def fijar(self, valor, rol='coordinadora', espacio='E02', **extra):
        return self.api(rol, 'put', f'/espacios/{espacio}/tarifa', **(extra or {'json': {'tarifa_hora': valor}}))

    def tarifa(self, espacio='E02'):
        return next(e['tarifa_hora'] for e in self.api('profesor', 'get', '/espacios').json() if e['id'] == espacio)

    def test_coordinadora_edita_y_persiste_tras_recargar_csv(self):
        self.assertEqual(self.fijar(50000).status_code, 200)
        self.assertTrue(carga_datos.cargar_datos()['ok'])
        self.assertEqual(self.tarifa(), 50000.0)

    def test_otros_roles_no_editan(self):
        for rol in ('profesor', 'empresa', 'estudiante', 'administrativo'):
            with self.subTest(rol=rol):
                respuesta = self.fijar(1000, rol=rol)
                self.assertEqual(respuesta.status_code, 403)
                self.assertEqual(respuesta.json()['codigo'], 'sin_permiso')
        self.assertEqual(self.fijar(1000, rol=None).status_code, 401)
        self.assertIsNone(self.tarifa())

    def test_valores_no_validos_se_rechazan_en_espanol(self):
        casos = [{'json': {'tarifa_hora': -1}}, {'json': {'tarifa_hora': 'cincuenta'}}, {'json': {'tarifa_hora': True}},
                 {'content': '{"tarifa_hora": NaN}', 'headers': {'Content-Type': 'application/json'}},
                 {'json': {'tarifa_hora': 10 ** 9}}, {'json': {'tarifa_hora': 5, 'rol': 'x'}}]
        for caso in casos:
            with self.subTest(caso=caso):
                respuesta = self.fijar(None, **caso)
                self.assertEqual(respuesta.status_code, 422)
                self.assertEqual(respuesta.json()['codigo'], 'tarifa_no_valida')
        self.assertEqual(self.fijar(5, espacio='NO-EXISTE').status_code, 404)
        self.assertIsNone(self.tarifa())

    def test_quitar_tarifa_vuelve_a_por_definir(self):
        with db.transaccion() as con:
            con.execute("UPDATE espacios SET tarifa_hora = 30000 WHERE id = 'E02'")  # valor del CSV
        self.assertEqual(self.tarifa(), 30000.0)
        self.assertEqual(self.fijar(None).status_code, 200)
        self.assertIsNone(self.tarifa())

    def test_cotizacion_existente_se_conserva_y_la_nueva_usa_la_tarifa_nueva(self):
        self.fijar(50000)
        cuerpo = {'espacio_id': 'E02', **FRANJA, 'personas': 5, 'descripcion': 'Evento'}
        primera = self.api('empresa', 'post', '/solicitudes', json=cuerpo).json()
        self.assertEqual(primera['costo']['total'], 100000.0)
        self.fijar(80000)
        nueva = self.api('empresa', 'post', '/solicitudes', json={**cuerpo, 'inicio': '2030-01-11T14:00', 'fin': '2030-01-11T16:00'}).json()
        filas = {f['id']: f for f in self.api('empresa', 'get', '/solicitudes').json()}
        self.assertEqual(filas[primera['id']]['costo']['total'], 100000.0)
        self.assertEqual(filas[nueva['id']]['costo']['total'], 160000.0)

    def test_historial_registra_quien_y_valores(self):
        self.fijar(50000)
        self.fijar(None)
        historial = db.consultar('SELECT valor_anterior, valor_nuevo, cambiado_por FROM historial_tarifas ORDER BY id')
        self.assertEqual(historial, [
            {'valor_anterior': None, 'valor_nuevo': 50000.0, 'cambiado_por': 'dev-coordinadora'},
            {'valor_anterior': 50000.0, 'valor_nuevo': None, 'cambiado_por': 'dev-coordinadora'},
        ])

    def test_asistente_menciona_aulas_sin_tarifa_como_necesaria(self):
        aviso = next(n for n in coordinacion.resumen()['notificaciones'] if n['tipo'] == 'aulas_sin_tarifa')
        self.assertEqual(aviso['nivel'], 'necesaria')
        ids = {a['id'] for a in aviso['datos']['aulas']}
        self.fijar(1000)
        nuevo = next(n for n in coordinacion.resumen()['notificaciones'] if n['tipo'] == 'aulas_sin_tarifa')
        self.assertEqual({a['id'] for a in nuevo['datos']['aulas']}, ids - {'E02'})
