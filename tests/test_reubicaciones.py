"""Prioridades y cambios confirmados: SQLite real, sin inferencia de IA."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from unittest import mock

from app import carga_datos, chat, db, ia, reubicaciones, solicitudes
from app.identidad import ErrorAcceso, Identidad
from app.solicitudes import ErrorSolicitud, NuevaSolicitud
from tests.test_solicitudes import BaseSolicitudes
from tests.test_chat import ia_json

PROFESOR = Identidad("prof-of", "profesor", "desarrollo")
COORDINADORA = Identidad("coord-of", "coordinadora", "desarrollo")
INICIO = "2035-01-08T08:00"
FIN = "2035-01-08T10:00"


class PruebasReubicacion(BaseSolicitudes):
    def setUp(self):
        super().setUp()
        with db.transaccion() as con:
            con.execute("UPDATE espacios SET nombre = 'Sala de estudio' WHERE id = 'E08'")
            con.execute("INSERT INTO espacios (id,nombre,tipo,aforo,estado,archivo_origen,fila_origen) "
                        "VALUES ('of-azul','Azul','sala',10,'activo','prueba',1)")

    def crear(self, actividad="ser", espacio="of-azul", elementos=None, comercial=False):
        identidad = Identidad("empresa-of", "empresa", "desarrollo") if comercial else PROFESOR
        return solicitudes.crear_solicitud(identidad, NuevaSolicitud(espacio_id=espacio,
            inicio=INICIO, fin=FIN, personas=8, descripcion=f"Clase {actividad}", actividad=actividad,
            elementos_requeridos=elementos or []))

    def escenario(self):
        ser = self.crear()
        solicitudes.aprobar_solicitud(ser["id"], COORDINADORA)
        zf = self.crear("zona_franca")
        return ser, zf

    def inalterado(self, ser, zf):
        self.assertEqual(solicitudes.obtener_solicitud(ser["id"])["espacio_id"], "of-azul")
        self.assertEqual(solicitudes.obtener_solicitud(zf["id"])["estado"], "pendiente")

    def test_proponer_no_mueve_confirmar_aplica_y_registra_autor_sin_duplicados(self):
        ser, zf = self.escenario()
        plan = reubicaciones.proponer(zf["id"], COORDINADORA)
        self.inalterado(ser, zf)
        self.assertEqual(plan["aula_origen"], "Azul")
        aplicada = reubicaciones.confirmar(plan["id"], COORDINADORA)
        self.assertEqual(aplicada["estado"], "aplicada")
        self.assertEqual(aplicada["autorizada_por"], COORDINADORA.usuario_id)
        self.assertEqual(solicitudes.obtener_solicitud(ser["id"])["espacio_id"], plan["destino_id"])
        self.assertEqual(solicitudes.obtener_solicitud(zf["id"])["estado"], "aprobada")
        self.assertEqual(reubicaciones.confirmar(plan["id"], COORDINADORA), aplicada)
        self.assertEqual(len(solicitudes.listar_reservas(None)), 2)
        self.assertEqual(self.contar("reubicaciones"), 1)

    def test_confirmaciones_concurrentes_no_duplican_cambio(self):
        _, zf = self.escenario()
        plan = reubicaciones.proponer(zf["id"], COORDINADORA)
        barrera = threading.Barrier(2)
        def confirmar():
            barrera.wait(timeout=10)
            return reubicaciones.confirmar(plan["id"], COORDINADORA)
        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            futuros = [ejecutor.submit(confirmar) for _ in range(2)]
            self.assertEqual([f.result(timeout=15)["estado"] for f in futuros], ["aplicada", "aplicada"])
        self.assertEqual(self.contar("reubicaciones"), 1)

    def test_sin_alternativa_conserva_original(self):
        ser, zf = self.escenario()
        with db.transaccion() as con:
            con.execute("UPDATE espacios SET estado = 'mantenimiento' WHERE id != 'of-azul'")
        with self.assertRaises(ErrorSolicitud) as contexto:
            reubicaciones.proponer(zf["id"], COORDINADORA)
        self.assertEqual(contexto.exception.codigo, "sin_alternativa")
        self.inalterado(ser, zf)

    def test_cambio_de_propuesta_o_reserva_original_invalida_confirmacion(self):
        ser, zf = self.escenario()
        plan = reubicaciones.proponer(zf["id"], COORDINADORA)
        with db.transaccion() as con:
            con.execute("UPDATE solicitudes SET personas = 9 WHERE id = ?", (zf["id"],))
        with self.assertRaises(ErrorSolicitud) as contexto:
            reubicaciones.confirmar(plan["id"], COORDINADORA)
        self.assertEqual(contexto.exception.codigo, "propuesta_desactualizada")
        self.inalterado(ser, zf)

    def test_destino_ocupado_despues_de_proponer_no_mueve_nada(self):
        ser, zf = self.escenario()
        plan = reubicaciones.proponer(zf["id"], COORDINADORA)
        otra = self.crear("ingles", plan["destino_id"])
        solicitudes.aprobar_solicitud(otra["id"], COORDINADORA)
        with self.assertRaises(ErrorSolicitud):
            reubicaciones.confirmar(plan["id"], COORDINADORA)
        self.inalterado(ser, zf)

    def test_aforo_del_destino_cambia_antes_de_confirmar(self):
        ser, zf = self.escenario()
        plan = reubicaciones.proponer(zf["id"], COORDINADORA)
        self.cambiar_aforo(plan["destino_id"], 7)
        with self.assertRaises(ErrorSolicitud):
            reubicaciones.confirmar(plan["id"], COORDINADORA)
        self.inalterado(ser, zf)

    def test_reubicacion_respeta_intervalo_completo_al_cruzar_medianoche(self):
        with mock.patch("tests.test_reubicaciones.INICIO", "2035-01-08T22:00"), mock.patch("tests.test_reubicaciones.FIN", "2035-01-09T02:00"):
            ser, zf = self.escenario()
        plan = reubicaciones.proponer(zf["id"], COORDINADORA)
        reubicaciones.confirmar(plan["id"], COORDINADORA)
        self.assertEqual(solicitudes.obtener_solicitud(ser["id"])["fin"], "2035-01-09 02:00")
        from datetime import date
        self.assertEqual(len(solicitudes.listar_reservas(date(2035, 1, 8))), 2)
        self.assertEqual(len(solicitudes.listar_reservas(date(2035, 1, 9))), 2)

    def test_actividad_iniciada_no_se_mueve_ni_al_confirmar(self):
        ser, zf = self.escenario()
        plan = reubicaciones.proponer(zf["id"], COORDINADORA)
        with mock.patch.object(reubicaciones, "datetime", wraps=datetime) as reloj:
            reloj.now.return_value = datetime(2035, 1, 8, 9)
            with self.assertRaises(ErrorSolicitud) as contexto:
                reubicaciones.confirmar(plan["id"], COORDINADORA)
        self.assertEqual(contexto.exception.codigo, "actividad_iniciada")
        self.inalterado(ser, zf)

    def test_fallo_al_aprobar_revierte_reubicacion_y_auditoria(self):
        ser, zf = self.escenario()
        plan = reubicaciones.proponer(zf["id"], COORDINADORA)
        with mock.patch.object(solicitudes, "aprobar_en", side_effect=ErrorSolicitud(409, "solapamiento", "Conflicto nuevo")):
            with self.assertRaises(ErrorSolicitud):
                reubicaciones.confirmar(plan["id"], COORDINADORA)
        self.inalterado(ser, zf)
        self.assertEqual(reubicaciones.consultar(plan["id"], COORDINADORA)["estado"], "propuesta")

    def test_solo_coordinadora_y_no_autoaprobacion(self):
        _, zf = self.escenario()
        with self.assertRaises(ErrorAcceso):
            reubicaciones.proponer(zf["id"], PROFESOR)
        with self.assertRaises(ErrorSolicitud) as contexto:
            reubicaciones.proponer(zf["id"], Identidad(PROFESOR.usuario_id, "coordinadora", "desarrollo"))
        self.assertEqual(contexto.exception.codigo, "autoaprobacion_no_permitida")
        for rol in ("profesor", "empresa", "estudiante", None):
            self.assertIn(self.api(rol, "post", f"/api/solicitudes/{zf['id']}/reubicacion/proponer").status_code, (401, 403))

    def test_no_desplaza_ingles_ni_comercial_por_preferencia_especifica(self):
        for actividad, comercial in (("ingles", False), ("otra", True)):
            with self.subTest(actividad=actividad):
                origen = self.crear(actividad, comercial=comercial)
                solicitudes.aprobar_solicitud(origen["id"], COORDINADORA)
                zf = self.crear("zona_franca")
                with self.assertRaises(ErrorSolicitud) as contexto:
                    reubicaciones.proponer(zf["id"], COORDINADORA)
                self.assertEqual(contexto.exception.codigo, "reubicacion_no_aplicable")
                # Aislar el siguiente caso sin fingir una cancelación disponible por API.
                with db.transaccion() as con:
                    con.execute("DELETE FROM solicitudes")

    def test_inventario_desconocido_no_satisface_requisitos_y_se_revalida(self):
        with self.assertRaises(ErrorSolicitud):
            self.crear(elementos=["Proyector"])
        with db.transaccion() as con:
            con.execute("UPDATE espacios SET elementos = ? WHERE id IN ('of-azul', 'E07')", (json.dumps(["Proyector"]),))
        ser = self.crear(elementos=["Proyector"])
        solicitudes.aprobar_solicitud(ser["id"], COORDINADORA)
        zf = self.crear("zona_franca")
        plan = reubicaciones.proponer(zf["id"], COORDINADORA)
        self.assertEqual(plan["destino_id"], "E07")
        with db.transaccion() as con:
            con.execute("UPDATE espacios SET elementos = NULL WHERE id = 'E07'")
        with self.assertRaises(ErrorSolicitud):
            reubicaciones.confirmar(plan["id"], COORDINADORA)
        self.inalterado(ser, zf)

    def test_reubica_sesion_ser_futura_conservando_identidad_y_horario(self):
        with db.transaccion() as con:
            con.execute("INSERT INTO sesiones (id,espacio_id,fecha,hora_inicio,hora_fin,tipo,area,es_zona_franca,grupo,cantidad_personas,responsable,estado,archivo_origen,fila_origen) "
                        "VALUES ('SER-OF','of-azul','2035-01-08','08:00','10:00','clase','ser',0,'prueba',8,'ficticio','programada','prueba',1)")
        zf = self.crear("zona_franca")
        plan = reubicaciones.proponer(zf["id"], COORDINADORA)
        self.assertEqual(plan["origen_tipo"], "sesiones")
        reubicaciones.confirmar(plan["id"], COORDINADORA)
        sesion = db.consultar("SELECT * FROM sesiones WHERE id = 'SER-OF'")[0]
        self.assertEqual(sesion["espacio_id"], plan["destino_id"])
        self.assertEqual(sesion["hora_inicio"], "08:00")
        self.assertEqual(sesion["responsable"], "ficticio")

    def test_chat_propone_azul_ocupada_sin_presentarla_como_libre_y_confirma_pendiente(self):
        ser = self.crear()
        solicitudes.aprobar_solicitud(ser["id"], COORDINADORA)
        with mock.patch.object(ia, "consultar_ia", return_value=ia_json("solicitar_aula", fecha="2035-01-08",
                    inicio="08:00", fin="10:00", personas=8, descripcion="Clase Zona Franca")):
            respuesta = chat.procesar(PROFESOR, "Zona Franca", "conv-reubicacion")
        self.assertEqual(respuesta["datos"][0]["espacio_id"], "of-azul")
        self.assertTrue(respuesta["datos"][0]["requiere_reubicacion"])
        self.assertIn("No es una reserva libre", respuesta["respuesta"])
        with mock.patch.object(ia, "consultar_ia", return_value=ia_json("confirmar")):
            creada = chat.procesar(PROFESOR, "sí", "conv-reubicacion")
        self.assertEqual(creada["estado"], "solicitud_creada")
        self.assertEqual(creada["datos"][0]["estado"], "pendiente")
        self.assertEqual(solicitudes.obtener_solicitud(ser["id"])["espacio_id"], "of-azul")

    def test_recarga_no_pierde_requisitos_de_reserva_aprobada(self):
        with db.transaccion() as con:
            con.execute("UPDATE espacios SET elementos = '[\"Proyector\"]' WHERE id = 'E07'")
        ser = self.crear(espacio="E07", elementos=["Proyector"])
        solicitudes.aprobar_solicitud(ser["id"], COORDINADORA)
        resultado = carga_datos.cargar_datos()
        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["error"]["codigo"], "reserva_incompatible")

    def test_prioridad_academica_igual_y_comercial_inferior_sin_suplantar_rol(self):
        comercial = self.crear(comercial=True)
        academicas = [self.crear(a) for a in ("zona_franca", "ser", "ingles")]
        self.assertEqual({a["prioridad"] for a in academicas}, {1})
        self.assertEqual(comercial["prioridad"], 0)
        self.assertEqual(comercial["actividad"], "comercial")
        with self.assertRaises(ErrorSolicitud) as contexto:
            solicitudes.aprobar_solicitud(comercial["id"], COORDINADORA)
        self.assertEqual(contexto.exception.codigo, "prioridad_academica")
        self.assertEqual(solicitudes.obtener_solicitud(comercial["id"])["estado"], "pendiente")
        self.assertEqual(solicitudes.listar_solicitudes(COORDINADORA)[-1]["id"], comercial["id"])
