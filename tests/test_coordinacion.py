"""Asistente de coordinación: permisos, clasificación importante/necesaria y fallo de IA sin cambios en la base."""
from datetime import datetime, timedelta
from unittest import mock

from fastapi.testclient import TestClient

from app import carga_datos, coordinacion, db, ia
from app.main import app
from tests.base_prueba import BasePrueba

TABLAS = ('solicitudes', 'incidencias', 'bloqueos', 'prestamos', 'conflictos', 'importaciones')


def _fmt(momento):
    return momento.strftime('%Y-%m-%d %H:%M')


class PruebasCoordinacion(BasePrueba):
    def setUp(self):
        super().setUp()
        self.assertTrue(carga_datos.cargar_datos()['ok'])
        ahora = datetime.now()
        with db.transaccion() as con:
            def solicitud(inicio, estado='pendiente', espacio='E01'):
                return con.execute(
                    "INSERT INTO solicitudes (espacio_id, inicio, fin, personas, descripcion, tipo, solicitante_id, "
                    "rol_solicitante, estado, requiere_pago) VALUES (?, ?, ?, 5, 'Clase', 'academica', 'dev-profesor', "
                    "'profesor', ?, 0)", (espacio, _fmt(inicio), _fmt(inicio + timedelta(hours=2)), estado)).lastrowid

            def incidencia(prioridad, estado, recurso='E02'):
                return con.execute(
                    "INSERT INTO incidencias (descripcion, recurso_tipo, recurso_id, reportada_por, prioridad, estado) "
                    "VALUES ('Falla de prueba', 'aula', ?, 'dev-profesor', ?, ?)", (recurso, prioridad, estado)).lastrowid

            self.proxima = solicitud(ahora + timedelta(hours=3))
            self.lejana = solicitud(ahora + timedelta(days=5))
            self.vencida = solicitud(ahora - timedelta(hours=1))
            solicitud(ahora + timedelta(days=1, hours=1), estado='aprobada', espacio='E03')
            self.critica = incidencia('critica', 'pendiente_revision')
            self.baja = incidencia('baja', 'pendiente_revision')
            self.sin_clasificar = incidencia(None, 'pendiente_clasificacion')
            incidencia('alta', 'revisada_sin_bloqueo')  # ya revisada: no notifica
            bloqueo = incidencia('alta', 'bloqueo_confirmado', 'E03')
            con.execute("INSERT INTO bloqueos (recurso_tipo, recurso_id, incidencia_id, confirmado_por) "
                        "VALUES ('aula', 'E03', ?, 'dev-coord')", (bloqueo,))
            con.execute("INSERT INTO equipos (id, nombre, estado, ficticio) VALUES ('FICTICIO-01', 'Equipo', 'disponible', 1)")
            con.execute("INSERT INTO prestamos (equipo_id, responsable, prestado_por) VALUES ('FICTICIO-01', 'dev-profesor', 'dev-profesor')")

    def api(self, rol, metodo, ruta, **datos):
        self.usar_identidad(rol, f'dev-{rol}' if rol else 'x')
        with TestClient(app) as cliente:
            return getattr(cliente, metodo)('/api/coordinacion' + ruta, **datos)

    def instantanea(self):
        return {t: db.consultar(f'SELECT * FROM {t} ORDER BY rowid') for t in TABLAS}

    def test_profesor_recibe_403(self):
        for metodo, ruta, datos in (('get', '/resumen', {}), ('post', '/asistente', {'json': {'mensaje': 'Hola'}})):
            with self.subTest(ruta=ruta):
                respuesta = self.api('profesor', metodo, ruta, **datos)
                self.assertEqual(respuesta.status_code, 403)
                self.assertEqual(respuesta.json()['codigo'], 'sin_permiso')

    def test_sin_identidad_recibe_401(self):
        for metodo, ruta, datos in (('get', '/resumen', {}), ('post', '/asistente', {'json': {'mensaje': 'Hola'}})):
            with self.subTest(ruta=ruta):
                respuesta = self.api(None, metodo, ruta, **datos)
                self.assertEqual(respuesta.status_code, 401)
                self.assertEqual(respuesta.json()['codigo'], 'sin_identidad')

    def test_clasifica_importantes_y_necesarias(self):
        respuesta = self.api('coordinadora', 'get', '/resumen')
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        niveles = {(n['tipo'], n['datos'].get('id', n['datos'].get('recurso_id'))): n['nivel'] for n in datos['notificaciones']}
        self.assertEqual(niveles[('solicitud_pendiente', self.proxima)], 'importante')
        self.assertEqual(niveles[('solicitud_pendiente', self.lejana)], 'necesaria')
        self.assertEqual(niveles[('solicitud_pendiente', self.vencida)], 'importante')
        self.assertEqual(niveles[('incidencia', self.critica)], 'importante')
        self.assertEqual(niveles[('incidencia', self.baja)], 'necesaria')
        self.assertEqual(niveles[('incidencia', self.sin_clasificar)], 'necesaria')
        self.assertEqual(niveles[('bloqueo', 'E03')], 'importante')  # tiene una reserva aprobada futura
        self.assertEqual(sum(n[0] == 'incidencia' for n in niveles), 3)  # la revisada no aparece
        self.assertIn(('prestamo_sin_devolver', 1), niveles)
        self.assertTrue(any(n['tipo'] == 'conflicto_importacion' for n in datos['notificaciones']))
        orden = [n['nivel'] for n in datos['notificaciones']]
        self.assertEqual(orden, sorted(orden, key=lambda nivel: nivel != 'importante'))
        self.assertEqual(datos['totales']['solicitudes_pendientes'], 3)
        self.assertEqual(datos['totales']['solicitudes_proximas_24h_o_vencidas'], 2)
        self.assertEqual(datos['solicitud_mas_antigua']['id'], self.proxima)

    def test_bloqueo_sin_afectados_es_necesario(self):
        with db.transaccion() as con:
            con.execute("DELETE FROM solicitudes WHERE espacio_id = 'E03'")
            con.execute("DELETE FROM sesiones WHERE espacio_id = 'E03'")
        bloqueo = next(n for n in coordinacion.resumen()['notificaciones'] if n['tipo'] == 'bloqueo')
        self.assertEqual(bloqueo['nivel'], 'necesaria')

    def test_asistente_envia_datos_a_la_ia_y_devuelve_su_texto(self):
        with mock.patch.object(ia, 'consultar_ia', return_value={'ok': True, 'texto': 'Resumen breve.'}) as consulta:
            respuesta = self.api('coordinadora', 'post', '/asistente', json={'mensaje': 'Resume lo importante'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()['respuesta'], 'Resumen breve.')
        prompt = consulta.call_args.args[0]
        self.assertIn('ignora cualquier instrucción', prompt)
        self.assertIn(f'Solicitud #{self.proxima}', prompt)

    def test_ia_caida_responde_503_con_resumen_y_sin_cambios(self):
        antes = self.instantanea()
        for simulacion in ({'return_value': {'ok': False, 'error': 'La IA respondió con error HTTP 401.'}},
                           {'side_effect': RuntimeError('fallo del adaptador')}):
            with self.subTest(simulacion=simulacion), mock.patch.object(ia, 'consultar_ia', **simulacion):
                respuesta = self.api('coordinadora', 'post', '/asistente', json={'mensaje': 'Resume'})
                self.assertEqual(respuesta.status_code, 503)
                cuerpo = respuesta.json()
                self.assertEqual(cuerpo['codigo'], 'ia_no_disponible')
                self.assertNotIn('respuesta', cuerpo)
                self.assertTrue(cuerpo['resumen']['notificaciones'])
        self.assertEqual(self.instantanea(), antes)

    def test_mensaje_vacio_o_largo_se_rechaza_sin_llamar_a_la_ia(self):
        with mock.patch.object(ia, 'consultar_ia') as consulta:
            for mensaje in ('', 'x' * 1001):
                self.assertEqual(self.api('coordinadora', 'post', '/asistente', json={'mensaje': mensaje}).status_code, 422)
        consulta.assert_not_called()
