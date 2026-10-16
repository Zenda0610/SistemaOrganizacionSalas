"""Chat de solicitudes con borrador. La IA se simula en el punto de llamada: estas pruebas verifican
las reglas del servidor, no la calidad de la interpretación de un modelo.

La prueba de inferencia real está al final y se omite si el proveedor no está configurado.
"""
import json
import threading
import unittest
from unittest import mock

from app import config, db, ia
from app.chat import procesar
from app.identidad import Identidad
from tests.test_solicitudes import BaseSolicitudes

CONV = "conv-prueba-1"
FECHA = "2026-11-02"


def ia_json(accion, **parametros):
    return {"ok": True, "texto": json.dumps({"accion": accion, "parametros": parametros}, ensure_ascii=False)}


def ia_caida():
    return {"ok": False, "error": "No se pudo conectar con la IA en http://secreto.local"}


class PruebasChat(BaseSolicitudes):
    def chatear(self, rol, ia_devuelve, conv=CONV, usuario=None, mensaje="(mensaje)"):
        self.usar_identidad(rol, usuario=usuario or f"dev-{rol}")
        with mock.patch.object(ia, "consultar_ia", return_value=ia_devuelve):
            from fastapi.testclient import TestClient
            from app.main import app
            with TestClient(app) as cliente:
                return cliente.post("/api/chat", json={"mensaje": mensaje, "conversacion_id": conv})

    def solicitar_aula(self, rol="profesor", conv=CONV, **parametros):
        return self.chatear(rol, ia_json("solicitar_aula", **parametros), conv=conv)

    def confirmar(self, rol="profesor", conv=CONV):
        return self.chatear(rol, ia_json("confirmar"), conv=conv)

    def solicitudes_contadas(self):
        return self.contar("solicitudes")

    # --- Casos de aceptación -------------------------------------------------------

    def test_nombre_de_aula_resuelve_el_id_del_catalogo(self):
        datos = self.solicitar_aula(espacio="Auditorio", fecha=FECHA, inicio="08:00", fin="10:00",
                                    personas=20, descripcion="Clase de software").json()
        self.assertEqual(datos["estado"], "propuesta")
        self.assertEqual(datos["datos"][0]["espacio_id"], "E01")
        self.assertEqual(self.solicitudes_contadas(), 0)

    def test_pedir_aula_sin_indicar_cual_produce_propuesta_disponible(self):
        datos = self.solicitar_aula(fecha=FECHA, inicio="08:00", fin="10:00", personas=8,
                                    descripcion="Taller").json()
        self.assertEqual(datos["estado"], "propuesta")
        ids = {e["id"] for e in db.consultar("SELECT id FROM espacios WHERE estado = 'activo'")}
        self.assertIn(datos["datos"][0]["espacio_id"], ids)
        self.assertEqual(self.solicitudes_contadas(), 0)

    def test_nombre_ambiguo_pide_aclarar_sin_elegir_aula(self):
        datos = self.solicitar_aula(espacio="Sala", fecha=FECHA, inicio="08:00", fin="10:00",
                                    personas=5, descripcion="Reunión").json()
        self.assertEqual(datos["estado"], "aclarar_espacio")
        self.assertIn("Sala Blanca", datos["respuesta"])
        self.assertEqual(self.solicitudes_contadas(), 0)

    def test_nombre_inexistente_informa_sin_inventar_aula(self):
        datos = self.solicitar_aula(espacio="Laboratorio Zeta", fecha=FECHA, inicio="08:00", fin="10:00",
                                    personas=5, descripcion="Práctica").json()
        self.assertEqual(datos["estado"], "aclarar_espacio")
        self.assertIn("No encuentro", datos["respuesta"])
        self.assertEqual(self.solicitudes_contadas(), 0)

    def test_omitir_personas_pregunta_concretamente_sin_inventar_aforo(self):
        datos = self.solicitar_aula(espacio="Auditorio", fecha=FECHA, inicio="08:00", fin="10:00",
                                    descripcion="Charla").json()
        self.assertEqual(datos["estado"], "faltan_datos")
        self.assertIn("cuántas personas", datos["respuesta"])
        self.assertEqual(self.solicitudes_contadas(), 0)

    def test_continuar_la_conversacion_conserva_los_datos_anteriores(self):
        primera = self.solicitar_aula(espacio="Auditorio", fecha=FECHA, inicio="08:00", fin="10:00").json()
        self.assertIn("cuántas personas", primera["respuesta"])
        self.assertNotIn("la fecha", primera["respuesta"])

        segunda = self.solicitar_aula(personas=8).json()
        self.assertIn("motivo", segunda["respuesta"])
        self.assertNotIn("cuántas personas", segunda["respuesta"])
        self.assertNotIn("la fecha", segunda["respuesta"])

        tercera = self.solicitar_aula(descripcion="Clase de software").json()
        self.assertEqual(tercera["estado"], "propuesta")
        self.assertEqual(tercera["datos"][0]["espacio_id"], "E01")
        self.assertEqual(tercera["datos"][0]["personas"], 8)
        self.assertEqual(self.solicitudes_contadas(), 0)

    def test_aula_ocupada_antes_de_confirmar_obliga_a_revisar_la_propuesta(self):
        self.assertEqual(self.solicitar_aula(espacio="Auditorio", fecha=FECHA, inicio="08:00", fin="10:00",
                                             personas=8, descripcion="Clase").json()["estado"], "propuesta")
        # Otra solicitud aprobada ocupa el Auditorio en parte del horario.
        self.assertEqual(self.aprobar_nueva(f"{FECHA}T09:00", f"{FECHA}T11:00", espacio="E01", personas=5).status_code, 200)

        datos = self.confirmar().json()

        self.assertEqual(datos["estado"], "propuesta")
        self.assertIn("ya no es válida", datos["respuesta"])
        self.assertNotEqual(datos["datos"][0]["espacio_id"], "E01")
        self.assertEqual(self.solicitudes_contadas(), 1)  # solo la aprobada previamente

    def test_confirmar_crea_una_sola_solicitud_y_repetir_no_duplica(self):
        self.solicitar_aula(espacio="Auditorio", fecha=FECHA, inicio="08:00", fin="10:00",
                            personas=8, descripcion="Clase de software")
        primera = self.confirmar().json()
        self.assertEqual(primera["estado"], "solicitud_creada")
        self.assertEqual(primera["datos"][0]["estado"], "pendiente")
        self.assertEqual(primera["datos"][0]["solicitante_id"], "dev-profesor")
        self.assertEqual(self.solicitudes_contadas(), 1)

        repetida = self.confirmar().json()
        self.assertEqual(repetida["estado"], "ya_creada")
        self.assertEqual(self.solicitudes_contadas(), 1)

    def test_confirmar_sin_propuesta_no_crea_nada(self):
        datos = self.confirmar().json()
        self.assertEqual(datos["estado"], "sin_propuesta")
        self.assertEqual(self.solicitudes_contadas(), 0)

    def test_fallo_de_ia_al_confirmar_no_crea_ni_cambia_el_borrador(self):
        self.solicitar_aula(espacio="Auditorio", fecha=FECHA, inicio="08:00", fin="10:00",
                            personas=8, descripcion="Clase")
        respuesta = self.chatear("profesor", ia_caida())
        self.assertEqual(respuesta.status_code, 503)
        self.assertNotIn("secreto", respuesta.text)
        self.assertEqual(self.solicitudes_contadas(), 0)
        self.assertEqual(db.consultar("SELECT estado FROM borradores_chat")[0]["estado"], "propuesta")

    def test_la_ia_no_puede_aprobar_desde_el_chat(self):
        solicitud = self.solicitar("profesor").json()["id"]
        datos = self.chatear("coordinadora", ia_json("aprobar_solicitud", id=solicitud)).json()
        self.assertEqual(datos["estado"], "no_entendido")
        self.assertEqual(db.consultar("SELECT estado FROM solicitudes WHERE id = ?", (solicitud,))[0]["estado"], "pendiente")

    def test_la_coordinadora_no_puede_solicitar_aulas(self):
        respuesta = self.solicitar_aula(rol="coordinadora", espacio="Auditorio", fecha=FECHA,
                                        inicio="08:00", fin="10:00", personas=5, descripcion="Prueba")
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(respuesta.json()["codigo"], "sin_permiso")

    def test_campos_de_identidad_e_id_de_la_ia_se_ignoran(self):
        # La IA intenta fijar otro solicitante, otro rol y otro aula por ID.
        self.solicitar_aula(fecha=FECHA, inicio="08:00", fin="10:00", personas=8, descripcion="Taller",
                            solicitante_id="otro", rol="coordinadora", espacio_id="E02")
        datos = self.solicitar_aula(fecha=FECHA, inicio="08:00", fin="10:00", personas=8, descripcion="Taller").json()
        self.assertEqual(datos["datos"][0]["espacio_id"], "E01")  # no E02: el ID de la IA no se usa
        creada = self.confirmar().json()
        self.assertEqual(creada["datos"][0]["solicitante_id"], "dev-profesor")

    def test_estudiante_confirma_solicitud_comercial_con_pago_pendiente_declarado(self):
        self.solicitar_aula(rol="estudiante", espacio="Cosmos", fecha=FECHA, inicio="18:00", fin="20:00",
                            personas=10, descripcion="Evento")
        datos = self.confirmar(rol="estudiante").json()
        self.assertEqual(datos["estado"], "solicitud_creada")
        self.assertTrue(datos["datos"][0]["requiere_pago"])
        self.assertIn("Pago pendiente", datos["respuesta"])

    def test_tras_crear_una_nueva_solicitud_empieza_desde_cero(self):
        self.solicitar_aula(espacio="Auditorio", fecha=FECHA, inicio="08:00", fin="10:00",
                            personas=8, descripcion="Clase")
        self.confirmar()
        nueva = self.solicitar_aula(personas=4).json()
        self.assertIn("la fecha", nueva["respuesta"])

    # --- Aislamiento y concurrencia --------------------------------------------------

    def test_un_borrador_no_se_comparte_entre_usuarios(self):
        self.solicitar_aula(espacio="Auditorio", fecha=FECHA, inicio="08:00", fin="10:00",
                            personas=8, descripcion="Clase")
        datos = self.chatear("profesor", ia_json("confirmar"), usuario="dev-otro-profesor").json()
        self.assertEqual(datos["estado"], "sin_propuesta")
        self.assertEqual(self.solicitudes_contadas(), 0)

    def test_un_borrador_no_se_comparte_entre_conversaciones(self):
        self.solicitar_aula(espacio="Auditorio", fecha=FECHA, inicio="08:00", fin="10:00",
                            personas=8, descripcion="Clase")
        datos = self.confirmar(conv="conv-prueba-2").json()
        self.assertEqual(datos["estado"], "sin_propuesta")
        self.assertEqual(self.solicitudes_contadas(), 0)

    def test_confirmaciones_simultaneas_crean_una_sola_solicitud(self):
        self.solicitar_aula(espacio="Auditorio", fecha=FECHA, inicio="08:00", fin="10:00",
                            personas=8, descripcion="Clase")
        identidad = Identidad("dev-profesor", "profesor", "desarrollo")
        barrera = threading.Barrier(2)
        resultados = []
        cerrojo = threading.Lock()

        def confirmar():
            barrera.wait()
            with mock.patch.object(ia, "consultar_ia", return_value=ia_json("confirmar")):
                datos = procesar(identidad, "sí", CONV)
            with cerrojo:
                resultados.append(datos["estado"])

        hilos = [threading.Thread(target=confirmar) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(sorted(resultados), ["solicitud_creada", "ya_creada"])
        self.assertEqual(self.solicitudes_contadas(), 1)

    def test_mensaje_o_conversacion_no_validos_se_rechazan(self):
        self.usar_identidad("profesor")
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as cliente:
            vacio = cliente.post("/api/chat", json={"mensaje": "   ", "conversacion_id": CONV})
            corto = cliente.post("/api/chat", json={"mensaje": "hola", "conversacion_id": "x"})
        self.assertEqual(vacio.status_code, 422)
        self.assertEqual(corto.status_code, 422)


@unittest.skipUnless(config.IA_PROVEEDOR and config.IA_URL and config.IA_MODELO,
                     "Proveedor de IA no configurado: la inferencia real no se ejecutó")
class PruebaInferenciaReal(unittest.TestCase):
    def test_el_proveedor_responde(self):
        resultado = ia.consultar_ia("Responde solo con la palabra ok.")
        self.assertTrue(resultado["ok"], resultado.get("error"))


if __name__ == "__main__":
    unittest.main()
