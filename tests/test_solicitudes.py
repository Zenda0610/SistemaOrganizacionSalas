"""Solicitudes de aulas: disponibilidad 24/7, permisos, aprobación validada y concurrencia.

La identidad de cada prueba sale de la configuración del servidor (identidad de desarrollo).
"""
import threading
import unittest
from datetime import datetime

from fastapi.testclient import TestClient

from app import carga_datos, db, solicitudes
from app.identidad import Identidad
from app.main import app
from app.solicitudes import ErrorSolicitud, NuevaSolicitud
from tests.base_prueba import BasePrueba


class BaseSolicitudes(BasePrueba):
    def setUp(self):
        super().setUp()
        self.assertTrue(carga_datos.cargar_datos()["ok"])

    def api(self, rol, metodo, ruta, **peticion):
        self.usar_identidad(rol, usuario=f"dev-{rol}" if rol else "dev-prueba")
        with TestClient(app) as cliente:
            return getattr(cliente, metodo)(ruta, **peticion)

    def solicitar(self, rol, espacio="E01", inicio="2026-11-02T08:00", fin="2026-11-02T09:00", personas=10):
        return self.api(rol, "post", "/api/solicitudes", json={
            "espacio_id": espacio, "inicio": inicio, "fin": fin, "personas": personas,
            "descripcion": "Clase de prueba",
        })

    def aprobar(self, solicitud_id):
        return self.api("coordinadora", "post", f"/api/solicitudes/{solicitud_id}/aprobar")

    def aprobar_nueva(self, inicio, fin, espacio="E01", personas=10):
        """Crea una solicitud de profesor y la aprueba como coordinadora. Devuelve la respuesta de la aprobación."""
        creada = self.solicitar("profesor", espacio=espacio, inicio=inicio, fin=fin, personas=personas)
        self.assertEqual(creada.status_code, 201, creada.text)
        return self.aprobar(creada.json()["id"])

    def estado_de_la_base(self, sql, parametros=()):
        return db.consultar(sql, parametros)

    def cambiar_estado_espacio(self, espacio_id, estado):
        con = db.conectar()
        try:
            con.execute("UPDATE espacios SET estado = ? WHERE id = ?", (estado, espacio_id))
            con.commit()
        finally:
            con.close()

    def cancelar_sesion(self, sesion_id):
        con = db.conectar()
        try:
            con.execute("UPDATE sesiones SET estado = 'cancelada' WHERE id = ?", (sesion_id,))
            con.commit()
        finally:
            con.close()


class PruebasIntervalos(BaseSolicitudes):
    def test_horas_consecutivas_son_compatibles(self):
        self.assertEqual(self.aprobar_nueva("2026-11-02T08:00", "2026-11-02T09:00").status_code, 200)
        self.assertEqual(self.aprobar_nueva("2026-11-02T09:00", "2026-11-02T10:00").status_code, 200)

    def test_solapamiento_parcial_se_rechaza_al_aprobar(self):
        self.assertEqual(self.aprobar_nueva("2026-11-02T08:00", "2026-11-02T09:00").status_code, 200)
        respuesta = self.aprobar_nueva("2026-11-02T08:30", "2026-11-02T09:30")
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.json()["codigo"], "solapamiento")

    def test_una_sesion_programada_bloquea_el_aula(self):
        # E04 el 2026-10-19: S01 08:00–10:00 y S02 09:00–10:30, ambas programadas.
        respuesta = self.aprobar_nueva("2026-10-19T10:00", "2026-10-19T11:00", espacio="E04", personas=5)
        self.assertEqual(respuesta.json()["codigo"], "solapamiento")
        self.assertEqual(self.aprobar_nueva("2026-10-19T10:30", "2026-10-19T11:00", espacio="E04", personas=5).status_code, 200)

    def test_una_sesion_cancelada_no_bloquea(self):
        self.cancelar_sesion("S01")
        self.cancelar_sesion("S02")
        self.assertEqual(self.aprobar_nueva("2026-10-19T08:00", "2026-10-19T11:00", espacio="E04", personas=5).status_code, 200)

    def test_reserva_que_cruza_medianoche_bloquea_la_madrugada(self):
        self.assertEqual(self.aprobar_nueva("2026-11-02T22:00", "2026-11-03T02:00").status_code, 200)
        self.assertEqual(self.aprobar_nueva("2026-11-03T01:00", "2026-11-03T03:00").json()["codigo"], "solapamiento")
        self.assertEqual(self.aprobar_nueva("2026-11-03T02:00", "2026-11-03T03:00").status_code, 200)

    def test_disponibilidad_excluye_el_aula_ocupada_en_medianoche(self):
        self.aprobar_nueva("2026-11-02T22:00", "2026-11-03T02:00")
        with TestClient(app) as cliente:
            libres = cliente.get("/api/disponibilidad", params={
                "inicio": "2026-11-03T01:00", "fin": "2026-11-03T01:30"}).json()
        ids = [espacio["id"] for espacio in libres]
        self.assertNotIn("E01", ids)
        self.assertIn("E02", ids)

    def test_intervalo_invalido_se_rechaza(self):
        with TestClient(app) as cliente:
            fin_antes = cliente.get("/api/disponibilidad", params={"inicio": "2026-11-02T10:00", "fin": "2026-11-02T09:00"})
            con_zona = cliente.get("/api/disponibilidad", params={"inicio": "2026-11-02T10:00Z", "fin": "2026-11-02T11:00Z"})
        self.assertEqual(fin_antes.status_code, 422)
        self.assertEqual(con_zona.status_code, 422)

    def test_minutos_fuera_del_bloque_se_rechazan(self):
        respuesta = self.solicitar("profesor", inicio="2026-11-02T08:07", fin="2026-11-02T09:00")
        self.assertEqual(respuesta.status_code, 422)


class PruebasPermisos(BaseSolicitudes):
    def test_profesor_crea_solicitud_academica(self):
        datos = self.solicitar("profesor").json()
        self.assertEqual(datos["tipo"], "academica")
        self.assertEqual(datos["estado"], "pendiente")
        self.assertFalse(datos["requiere_pago"])
        self.assertIsNone(datos["estado_pago"])
        self.assertEqual(datos["solicitante_id"], "dev-profesor")

    def test_estudiante_crea_solicitud_comercial_con_pago_pendiente(self):
        datos = self.solicitar("estudiante").json()
        self.assertEqual(datos["tipo"], "comercial")
        self.assertTrue(datos["requiere_pago"])
        self.assertEqual(datos["estado_pago"], "pendiente")

    def test_coordinadora_no_puede_crear_solicitudes(self):
        respuesta = self.solicitar("coordinadora")
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(respuesta.json()["codigo"], "sin_permiso")

    def test_sin_identidad_no_crea(self):
        respuesta = self.solicitar(None)
        self.assertEqual(respuesta.status_code, 401)
        self.assertEqual(self.contar("solicitudes"), 0)

    def test_el_cuerpo_no_puede_fijar_tipo_rol_ni_solicitante(self):
        for campo, valor in (("tipo", "academica"), ("rol", "coordinadora"), ("solicitante_id", "otro")):
            with self.subTest(campo=campo):
                respuesta = self.api("estudiante", "post", "/api/solicitudes", json={
                    "espacio_id": "E01", "inicio": "2026-11-02T08:00", "fin": "2026-11-02T09:00",
                    "personas": 5, "descripcion": "Prueba", campo: valor,
                })
                self.assertEqual(respuesta.status_code, 422)
        self.assertEqual(self.contar("solicitudes"), 0)

    def test_solo_la_coordinadora_aprueba(self):
        solicitud = self.solicitar("profesor").json()["id"]
        for rol in ("profesor", "administrativo", "estudiante", "empresa"):
            with self.subTest(rol=rol):
                respuesta = self.api(rol, "post", f"/api/solicitudes/{solicitud}/aprobar")
                self.assertEqual(respuesta.status_code, 403)
        estado = self.estado_de_la_base("SELECT estado FROM solicitudes WHERE id = ?", (solicitud,))[0]["estado"]
        self.assertEqual(estado, "pendiente")

    def test_coordinadora_aprueba_y_no_se_aprueba_dos_veces(self):
        solicitud = self.solicitar("profesor").json()["id"]
        aprobada = self.aprobar(solicitud)
        self.assertEqual(aprobada.status_code, 200)
        self.assertEqual(aprobada.json()["estado"], "aprobada")
        self.assertEqual(aprobada.json()["decidida_por"], "dev-coordinadora")
        segunda = self.aprobar(solicitud)
        self.assertEqual(segunda.status_code, 409)
        self.assertEqual(segunda.json()["codigo"], "no_pendiente")

    def test_coordinadora_no_puede_autoaprobar_su_solicitud(self):
        # Caso protegido en el servicio: la coordinadora no crea solicitudes por la API,
        # así que se prueba directamente con una solicitud del mismo usuario.
        mismo_usuario = Identidad("dev-coordinadora", "profesor", "desarrollo")
        creada = solicitudes.crear_solicitud(mismo_usuario, NuevaSolicitud(
            espacio_id="E01", inicio=datetime(2026, 11, 2, 8), fin=datetime(2026, 11, 2, 9),
            personas=5, descripcion="Prueba de autoaprobación"))
        with self.assertRaises(ErrorSolicitud) as contexto:
            solicitudes.aprobar_solicitud(creada["id"], Identidad("dev-coordinadora", "coordinadora", "desarrollo"))
        self.assertEqual(contexto.exception.codigo, "autoaprobacion_no_permitida")

    def test_cada_usuario_ve_solo_sus_solicitudes_salvo_la_coordinadora(self):
        self.solicitar("estudiante", inicio="2026-11-02T08:00", fin="2026-11-02T09:00")
        self.solicitar("profesor", inicio="2026-11-02T10:00", fin="2026-11-02T11:00")
        estudiante = self.api("estudiante", "get", "/api/solicitudes").json()
        coordinadora = self.api("coordinadora", "get", "/api/solicitudes").json()
        self.assertEqual([s["solicitante_id"] for s in estudiante], ["dev-estudiante"])
        self.assertEqual(len(coordinadora), 2)


class PruebasAprobacion(BaseSolicitudes):
    def test_aforo_se_revalida_al_aprobar(self):
        # E02 tiene aforo 25. La solicitud se crea con 20 personas y el aforo baja antes de aprobar.
        creada = self.solicitar("profesor", espacio="E02", personas=20).json()
        con = db.conectar()
        try:
            con.execute("UPDATE espacios SET aforo = 10 WHERE id = 'E02'")
            con.commit()
        finally:
            con.close()
        respuesta = self.aprobar(creada["id"])
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.json()["codigo"], "aforo_excedido")

    def test_espacio_en_mantenimiento_no_se_aprueba(self):
        creada = self.solicitar("profesor").json()
        self.cambiar_estado_espacio("E01", "mantenimiento")
        respuesta = self.aprobar(creada["id"])
        self.assertEqual(respuesta.json()["codigo"], "espacio_no_disponible")

    def test_espacio_en_mantenimiento_no_admite_nuevas_solicitudes(self):
        self.cambiar_estado_espacio("E01", "mantenimiento")
        self.assertEqual(self.solicitar("profesor").json()["codigo"], "espacio_no_disponible")

    def test_aprobaciones_simultaneas_no_ocupan_el_aula_dos_veces(self):
        # Dos solicitudes pendientes y solapadas. Cada hilo aprueba una con su propia conexión.
        ids = [
            self.solicitar("profesor", inicio="2026-11-05T08:00", fin="2026-11-05T10:00").json()["id"],
            self.solicitar("administrativo", inicio="2026-11-05T09:00", fin="2026-11-05T11:00").json()["id"],
        ]
        coordinadora = Identidad("dev-coordinadora", "coordinadora", "desarrollo")
        barrera = threading.Barrier(2)
        resultados = []
        cerrojo = threading.Lock()

        def aprobar(solicitud_id):
            barrera.wait()
            try:
                solicitudes.aprobar_solicitud(solicitud_id, coordinadora)
                resultado = "aprobada"
            except ErrorSolicitud as error:
                resultado = error.codigo
            with cerrojo:
                resultados.append(resultado)

        hilos = [threading.Thread(target=aprobar, args=(i,)) for i in ids]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(sorted(resultados), ["aprobada", "solapamiento"])
        aprobadas = self.estado_de_la_base(
            "SELECT COUNT(*) AS total FROM solicitudes WHERE espacio_id = 'E01' AND estado = 'aprobada' "
            "AND inicio < '2026-11-05 11:00' AND '2026-11-05 08:00' < fin")
        self.assertEqual(aprobadas[0]["total"], 1)


class PruebasCalendario(BaseSolicitudes):
    def test_la_reserva_aprobada_aparece_en_los_dos_dias_que_ocupa(self):
        self.aprobar_nueva("2026-11-02T22:00", "2026-11-03T02:00")
        with TestClient(app) as cliente:
            dia_1 = cliente.get("/api/reservas", params={"fecha": "2026-11-02"}).json()
            dia_2 = cliente.get("/api/reservas", params={"fecha": "2026-11-03"}).json()
            dia_3 = cliente.get("/api/reservas", params={"fecha": "2026-11-04"}).json()
        self.assertEqual(len(dia_1), 1)
        self.assertEqual(len(dia_2), 1)
        self.assertEqual(dia_3, [])

    def test_el_calendario_no_expone_datos_del_solicitante(self):
        self.aprobar_nueva("2026-11-02T08:00", "2026-11-02T09:00")
        with TestClient(app) as cliente:
            reserva = cliente.get("/api/reservas").json()[0]
        self.assertEqual(set(reserva), {"id", "espacio_id", "inicio", "fin", "tipo", "estado_pago"})

    def test_reserva_de_varios_dias_aparece_en_cada_dia_que_ocupa(self):
        self.aprobar_nueva("2026-11-02T20:00", "2026-11-05T06:00")
        with TestClient(app) as cliente:
            por_dia = {dia: len(cliente.get("/api/reservas", params={"fecha": dia}).json())
                       for dia in ("2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06")}
        self.assertEqual(por_dia, {"2026-11-01": 0, "2026-11-02": 1, "2026-11-03": 1,
                                   "2026-11-04": 1, "2026-11-05": 1, "2026-11-06": 0})

    def test_una_solicitud_pendiente_no_aparece_en_el_calendario(self):
        self.solicitar("profesor")
        with TestClient(app) as cliente:
            self.assertEqual(cliente.get("/api/reservas").json(), [])

    def test_recargar_datos_no_borra_reservas_aprobadas(self):
        self.aprobar_nueva("2026-11-02T08:00", "2026-11-02T09:00")
        self.assertTrue(carga_datos.cargar_datos()["ok"])
        self.assertEqual(len(solicitudes.listar_reservas(None)), 1)


if __name__ == "__main__":
    unittest.main()
