"""SQLite real temporal, API real; clasificación simulada salvo prueba optativa explícita."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import mock, skipIf

from fastapi.testclient import TestClient

from app import carga_datos, db, ia, operaciones, solicitudes, chat
from app.identidad import Identidad
from app.main import app
from tests.base_prueba import BasePrueba

CLASE = dict(categoria='tecnologia', prioridad='alta', area='soporte', justificacion='Revisar conexión eléctrica.')
COORD = Identidad('dev-coordinadora', 'coordinadora', 'desarrollo')
PROFE = Identidad('dev-profesor', 'profesor', 'desarrollo')


class PruebasOperaciones(BasePrueba):
    def setUp(self):
        super().setUp()
        self.assertTrue(carga_datos.cargar_datos()['ok'])
        operaciones.crear_equipo(operaciones.EquipoNuevo(id='FICTICIO-01', nombre='Equipo ficticio para pruebas', ficticio=True), COORD)

    def api(self, rol, metodo, ruta, **datos):
        self.usar_identidad(rol, f'dev-{rol}')
        with TestClient(app) as cliente:
            return getattr(cliente, metodo)('/api' + ruta, **datos)

    def reporte(self, tipo='aula', recurso='E01', respuesta=None):
        with mock.patch.object(ia, 'consultar_ia', return_value=respuesta or {'ok': True, 'texto': json.dumps(CLASE)}):
            return operaciones.reportar(operaciones.Reporte(descripcion='Falla eléctrica, revisar antes de usar.', recurso_tipo=tipo, recurso_id=recurso), PROFE)

    def bloquear(self, tipo='aula', recurso='E01'):
        incidencia = self.reporte(tipo, recurso)
        return operaciones.revisar(incidencia['id'], operaciones.Revision(**CLASE, bloquear=True), COORD)

    def test_prestar_rechazar_segundo_devolver_y_no_devolver_dos_veces(self):
        datos = {'equipo_id': 'FICTICIO-01', 'responsable': 'dev-profesor'}
        prestamo = self.api('profesor', 'post', '/prestamos', json=datos)
        self.assertEqual(prestamo.status_code, 201)
        self.assertEqual(self.api('profesor', 'post', '/prestamos', json=datos).status_code, 409)
        ruta = f"/prestamos/{prestamo.json()['id']}/devolver"
        self.assertEqual(self.api('profesor', 'post', ruta).status_code, 200)
        self.assertEqual(self.api('profesor', 'post', ruta).status_code, 409)
        self.assertEqual(self.api('profesor', 'post', '/prestamos', json=datos).status_code, 201)

    def test_prestamos_simultaneos_un_solo_prestamo(self):
        barrera = threading.Barrier(2)
        def ejecutar():
            barrera.wait()
            try:
                operaciones.prestar(operaciones.PrestamoNuevo(equipo_id='FICTICIO-01', responsable=PROFE.usuario_id), PROFE)
                return 201
            except solicitudes.ErrorSolicitud as error:
                return error.estado
        with ThreadPoolExecutor(2) as pool:
            resultados = list(pool.map(lambda _: ejecutar(), range(2)))
        self.assertEqual(sorted(resultados), [201, 409])
        self.assertEqual(self.contar('prestamos'), 1)

    def test_permiso_directo_api_y_responsable(self):
        self.assertEqual(self.api('profesor', 'post', '/equipos', json={'id': 'x', 'nombre': 'x'}).status_code, 403)
        self.assertEqual(self.api('estudiante', 'post', '/prestamos', json={'equipo_id': 'FICTICIO-01', 'responsable': 'dev-estudiante'}).status_code, 403)
        self.assertEqual(self.api('profesor', 'post', '/prestamos', json={'equipo_id': 'FICTICIO-01', 'responsable': 'otra'}).status_code, 403)
        prestamo = operaciones.prestar(operaciones.PrestamoNuevo(equipo_id='FICTICIO-01', responsable='otro-profesor'), COORD)
        self.assertEqual(self.api('profesor', 'post', f"/prestamos/{prestamo['id']}/devolver").status_code, 403)
        self.assertEqual(self.api('profesor', 'get', '/prestamos').json(), [])
        self.assertEqual(len(self.api('coordinadora', 'get', '/prestamos').json()), 1)

    def test_estados_de_equipo_y_equipo_inexistente(self):
        for estado in ('inhabilitado', 'mantenimiento'):
            operaciones.crear_equipo(operaciones.EquipoNuevo(id=estado, nombre=estado, estado=estado), COORD)
            r = self.api('profesor', 'post', '/prestamos', json={'equipo_id': estado, 'responsable': 'dev-profesor'})
            self.assertEqual(r.status_code, 409)
        self.assertEqual(self.api('profesor', 'post', '/prestamos', json={'equipo_id': 'inexistente', 'responsable': 'dev-profesor'}).status_code, 404)

    def test_ia_fallida_o_invalida_conserva_reporte(self):
        for respuesta in ({'ok': False, 'error': 'sin conexión'}, {'ok': True, 'texto': 'no JSON'},
                          {'ok': True, 'texto': json.dumps({**CLASE, 'prioridad': 'inventada'})},
                          {'ok': True, 'texto': json.dumps({**CLASE, 'bloquear': True})}):
            reporte = self.reporte(respuesta=respuesta)
            self.assertEqual(reporte['estado'], 'pendiente_clasificacion')
            self.assertIsNone(reporte['categoria'])
        self.assertEqual(self.contar('incidencias'), 4)
        self.assertEqual(self.contar('bloqueos'), 0)

    def test_prioridad_no_bloquea_y_revision_sin_bloqueo(self):
        reporte = self.reporte(respuesta={'ok': True, 'texto': json.dumps({**CLASE, 'prioridad': 'critica'})})
        self.assertEqual(reporte['estado'], 'pendiente_revision')
        self.assertEqual(self.contar('bloqueos'), 0)
        resultado = operaciones.revisar(reporte['id'], operaciones.Revision(**CLASE, bloquear=False), COORD)
        self.assertEqual(resultado['estado'], 'revisada_sin_bloqueo')
        self.assertEqual(self.contar('bloqueos'), 0)

    def test_recurso_inexistente_y_estructura_invalida_no_persisten(self):
        for recurso in ('equipo', 'aula'):
            respuesta = self.api('profesor', 'post', '/incidencias', json={'recurso_tipo': recurso, 'recurso_id': 'no-existe', 'descripcion': 'Falla reportada'})
            self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(self.api('profesor', 'post', '/incidencias', json={'recurso_tipo': 'inventado', 'recurso_id': 'E01', 'descripcion': 'Falla reportada'}).status_code, 422)
        self.assertEqual(self.contar('incidencias'), 0)

    def test_bloqueo_autorizado_con_auditoria_impide_nuevas_asignaciones(self):
        reporte = self.reporte()
        ruta = f"/incidencias/{reporte['id']}/revisar"
        self.assertEqual(self.api('profesor', 'post', ruta, json={**CLASE, 'bloquear': True}).status_code, 403)
        respuesta = self.api('coordinadora', 'post', ruta, json={**CLASE, 'bloquear': True})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()['revisada_por'], COORD.usuario_id)
        self.assertTrue(respuesta.json()['revisada_en'])
        self.assertEqual(self.api('coordinadora', 'post', ruta, json={**CLASE, 'bloquear': True}).status_code, 409)
        datos = {'espacio_id': 'E01', 'inicio': '2035-01-08T08:00', 'fin': '2035-01-08T09:00', 'personas': 8, 'descripcion': 'Clase de SER'}
        self.assertEqual(self.api('profesor', 'post', '/solicitudes', json=datos).status_code, 409)
        disponibles = self.api('profesor', 'get', '/disponibilidad?inicio=2035-01-08T08:00&fin=2035-01-08T09:00&personas=8').json()
        self.assertNotIn('E01', [r['id'] for r in disponibles])

    def test_bloqueo_conserva_reservas_afectadas_y_rechaza_aprobacion_pendiente(self):
        datos = solicitudes.NuevaSolicitud(espacio_id='E01', inicio='2035-01-08T08:00', fin='2035-01-08T09:00', personas=8, descripcion='Clase de SER')
        reserva = solicitudes.crear_solicitud(PROFE, datos)
        solicitudes.aprobar_solicitud(reserva['id'], COORD)
        pendiente = solicitudes.crear_solicitud(PROFE, datos.model_copy(update={'inicio': datos.inicio.replace(hour=10), 'fin': datos.fin.replace(hour=11)}))
        bloqueada = self.bloquear()
        self.assertIn(reserva['id'], [r['id'] for r in bloqueada['afectados']['reservas']])
        self.assertEqual(solicitudes.obtener_solicitud(reserva['id'])['estado'], 'aprobada')
        with self.assertRaises(solicitudes.ErrorSolicitud):
            solicitudes.aprobar_solicitud(pendiente['id'], COORD)
        self.assertEqual(solicitudes.obtener_solicitud(pendiente['id'])['estado'], 'pendiente')
        # El bloqueo no desaparece al recargar CSV.
        self.assertTrue(carga_datos.cargar_datos()['ok'])
        with db.transaccion() as con:
            self.assertTrue(db.aula_bloqueada(con, 'E01'))

    def test_bloqueo_equipo_muestra_prestamo_permite_devolver_y_no_represtar(self):
        prestamo = operaciones.prestar(operaciones.PrestamoNuevo(equipo_id='FICTICIO-01', responsable=PROFE.usuario_id), PROFE)
        resultado = self.bloquear('equipo', 'FICTICIO-01')
        self.assertEqual(resultado['afectados']['prestamos'][0]['id'], prestamo['id'])
        operaciones.devolver(prestamo['id'], PROFE)
        with self.assertRaises(solicitudes.ErrorSolicitud):
            operaciones.prestar(operaciones.PrestamoNuevo(equipo_id='FICTICIO-01', responsable=PROFE.usuario_id), PROFE)

    def test_ia_tardia_no_sobrescribe_revision_humana(self):
        entrada, salida = threading.Event(), threading.Event()
        def inferir(_prompt):
            entrada.set()
            self.assertTrue(salida.wait(5))
            return {'ok': True, 'texto': json.dumps(CLASE)}
        with mock.patch.object(ia, 'consultar_ia', side_effect=inferir), ThreadPoolExecutor(1) as pool:
            futuro = pool.submit(operaciones.reportar, operaciones.Reporte(descripcion='Cable dañado en aula.', recurso_tipo='aula', recurso_id='E01'), PROFE)
            self.assertTrue(entrada.wait(5))
            identificador = db.consultar('SELECT id FROM incidencias')[0]['id']
            try:
                operaciones.revisar(identificador, operaciones.Revision(**{**CLASE, 'prioridad': 'baja'}, bloquear=False), COORD)
            finally:
                salida.set()
            resultado = futuro.result(5)
        self.assertEqual(resultado['prioridad'], 'baja')
        self.assertEqual(resultado['estado'], 'revisada_sin_bloqueo')

    def test_flujo_chat_simulado_aprobar_calendario_y_confirmacion_tras_bloqueo(self):
        def inferencia(accion, **parametros):
            return mock.patch.object(ia, 'consultar_ia', return_value={'ok': True, 'texto': json.dumps({'accion': accion, 'parametros': parametros})})
        with inferencia('solicitar_aula', espacio='Auditorio', fecha='2035-01-08', inicio='08:00', fin='09:00', personas=8, descripcion='Clase SER'):
            propuesta = chat.procesar(PROFE, 'Una clase SER', 'integracion-01')
        self.assertEqual(propuesta['estado'], 'propuesta')
        with inferencia('confirmar'):
            creada = chat.procesar(PROFE, 'Confirmo', 'integracion-01')
            repetida = chat.procesar(PROFE, 'Confirmo', 'integracion-01')
        self.assertEqual(creada['estado'], 'solicitud_creada')
        self.assertEqual(self.contar('solicitudes'), 1)
        self.assertEqual(repetida['estado'], 'ya_creada')
        identificador = db.consultar('SELECT id FROM solicitudes')[0]['id']
        solicitudes.aprobar_solicitud(identificador, COORD)
        self.assertEqual(solicitudes.listar_reservas(None)[0]['id'], identificador)
        with inferencia('solicitar_aula', espacio='Auditorio', fecha='2035-01-09', inicio='08:00', fin='09:00', personas=8, descripcion='Clase SER'):
            self.assertEqual(chat.procesar(PROFE, 'Otra clase', 'integracion-02')['estado'], 'propuesta')
        self.bloquear()
        with inferencia('confirmar'):
            chat.procesar(PROFE, 'Confirmo', 'integracion-02')
        self.assertEqual(self.contar('solicitudes'), 1)

    def test_reporte_visible_solo_al_autor_o_coordinadora(self):
        self.reporte()
        self.assertEqual(len(self.api('profesor', 'get', '/incidencias').json()), 1)
        self.assertEqual(self.api('estudiante', 'get', '/incidencias').json(), [])
        self.assertEqual(len(self.api('coordinadora', 'get', '/incidencias').json()), 1)

    def test_excepcion_inesperada_del_adaptador_conserva_reporte(self):
        with mock.patch.object(ia, 'consultar_ia', side_effect=RuntimeError('fallo del adaptador')):
            resultado = self.api('profesor', 'post', '/incidencias', json={'descripcion': 'Falla del aula reportada', 'recurso_tipo': 'aula', 'recurso_id': 'E01'})
        self.assertEqual(resultado.status_code, 201)
        self.assertEqual(resultado.json()['estado'], 'pendiente_clasificacion')
        self.assertEqual(self.contar('incidencias'), 1)

    def test_devoluciones_simultaneas_solo_una_se_aplica(self):
        prestamo = operaciones.prestar(operaciones.PrestamoNuevo(equipo_id='FICTICIO-01', responsable=PROFE.usuario_id), PROFE)
        barrera = threading.Barrier(2)
        def ejecutar(_):
            barrera.wait()
            try:
                operaciones.devolver(prestamo['id'], PROFE)
                return 200
            except solicitudes.ErrorSolicitud as error:
                return error.estado
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sorted(pool.map(ejecutar, range(2))), [200, 409])
        self.assertTrue(db.consultar('SELECT devuelto_por FROM prestamos')[0]['devuelto_por'])

    def test_revisiones_simultaneas_un_solo_bloqueo_auditado(self):
        reporte = self.reporte()
        barrera = threading.Barrier(2)
        def ejecutar(_):
            barrera.wait()
            try:
                operaciones.revisar(reporte['id'], operaciones.Revision(**CLASE, bloquear=True), COORD)
                return 200
            except solicitudes.ErrorSolicitud as error:
                return error.estado
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sorted(pool.map(ejecutar, range(2))), [200, 409])
        self.assertEqual(self.contar('bloqueos'), 1)


class PruebaProveedorIncidencias(BasePrueba):
    @skipIf(ia._problema_configuracion() is not None, 'Proveedor real sin configurar: falta clave o configuración.')
    def test_clasificacion_real(self):
        self.assertTrue(carga_datos.cargar_datos()['ok'])
        reporte = operaciones.reportar(operaciones.Reporte(descripcion='El proyector no enciende en esta aula. Revisar conexión.', recurso_tipo='aula', recurso_id='E01'), PROFE)
        self.assertEqual(reporte['estado'], 'pendiente_revision', 'La inferencia real no produjo una clasificación válida.')
        self.assertIn(reporte['categoria'], ('infraestructura', 'tecnologia', 'limpieza', 'seguridad', 'otra'))
