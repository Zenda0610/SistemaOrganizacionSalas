"""Vistas por rol: Datos solo para la coordinadora; solicitudes e incidencias propias para los demás."""
from fastapi.testclient import TestClient

from app import carga_datos, db
from app.main import app
from tests.base_prueba import BasePrueba


class PruebasVistasPorRol(BasePrueba):
    def setUp(self):
        super().setUp()
        self.assertTrue(carga_datos.cargar_datos()['ok'])
        with db.transaccion() as con:
            for usuario in ('dev-profesor', 'otro-profesor'):
                con.execute(
                    "INSERT INTO solicitudes (espacio_id, inicio, fin, personas, descripcion, tipo, solicitante_id, "
                    "rol_solicitante, estado, requiere_pago) VALUES ('E01', '2030-01-10 08:00', '2030-01-10 10:00', 5, "
                    "'Clase', 'academica', ?, 'profesor', 'pendiente', 0)", (usuario,))
                con.execute("INSERT INTO incidencias (descripcion, recurso_tipo, recurso_id, reportada_por) "
                            "VALUES ('Falla de prueba', 'aula', 'E02', ?)", (usuario,))

    def get(self, rol, ruta, usuario=None):
        self.usar_identidad(rol, usuario or f'dev-{rol}')
        with TestClient(app) as cliente:
            return cliente.get('/api' + ruta)

    def test_datos_solo_para_coordinadora(self):
        for ruta in ('/calidad-datos', '/cohortes'):
            with self.subTest(ruta=ruta):
                for rol in ('profesor', 'administrativo', 'estudiante', 'empresa'):
                    respuesta = self.get(rol, ruta)
                    self.assertEqual(respuesta.status_code, 403, rol)
                    self.assertEqual(respuesta.json()['codigo'], 'sin_permiso')
                self.assertEqual(self.get(None, ruta).status_code, 401)
                self.assertEqual(self.get('coordinadora', ruta).status_code, 200)

    def test_profesor_ve_solo_sus_solicitudes_e_incidencias(self):
        for ruta, campo in (('/solicitudes', 'solicitante_id'), ('/incidencias', 'reportada_por')):
            with self.subTest(ruta=ruta):
                filas = self.get('profesor', ruta, 'dev-profesor').json()
                self.assertEqual({f[campo] for f in filas}, {'dev-profesor'})

    def test_coordinadora_ve_todas(self):
        for ruta, campo in (('/solicitudes', 'solicitante_id'), ('/incidencias', 'reportada_por')):
            with self.subTest(ruta=ruta):
                filas = self.get('coordinadora', ruta).json()
                self.assertEqual({f[campo] for f in filas}, {'dev-profesor', 'otro-profesor'})
