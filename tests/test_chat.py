"""Chat de solicitudes con borrador. La IA se simula en el punto de llamada: estas pruebas verifican
las reglas del servidor, no la calidad de la interpretación de un modelo.

La prueba de inferencia real está al final y se omite si el proveedor no está configurado.
"""
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from app import chat, config, db, ia
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
        self.assertEqual(datos["datos"][0]["espacio_id"], "E07")  # menor aforo adecuado; el ID de la IA no se usa
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

    def test_alias_confirmados_resuelven_ids_existentes(self):
        catalogo = chat._catalogo()
        for nombre, esperado in {"Spooki": "E04", "Skilab": "E03", "Amarillas verdes": "E09",
                                 "Blanca": "E07", "Azul": "E08"}.items():
            with self.subTest(nombre=nombre):
                estado, espacio = chat.resolver_espacio(nombre, catalogo)
                self.assertEqual(estado, "ok")
                self.assertEqual(espacio["id"], esperado)
                self.assertEqual(chat.resolver_espacio(nombre, []), ("no_existe", None))

    def test_seleccion_por_aforo_y_preferencia_zona_franca(self):
        for parametros, esperado in (({"descripcion": "Clase Zona Franca"}, "E08"),
                                     ({"descripcion": "Clase SER", "es_zona_franca": True}, "E08"),
                                     ({"descripcion": "Clase SER"}, "E07")):
            with self.subTest(parametros=parametros):
                datos = self.solicitar_aula(fecha=FECHA, inicio="08:00", fin="10:00", personas=8,
                                            **parametros).json()
                self.assertEqual(datos["datos"][0]["espacio_id"], esperado)

    def test_zona_franca_en_mensaje_se_conserva_al_completar_borrador(self):
        self.chatear("profesor", ia_json("solicitar_aula", fecha=FECHA, inicio="08:00", fin="10:00",
                                         descripcion="Clase"), mensaje="Un aula para Zona Franca")
        datos = self.solicitar_aula(personas=8).json()
        self.assertEqual(datos["datos"][0]["espacio_id"], "E08")

    def test_preferencia_no_salta_aforo_disponibilidad_ni_aula_explicita(self):
        for parametros, esperado in (({"personas": 11, "descripcion": "Zona Franca"}, "E07"),
                                     ({"personas": 8, "descripcion": "SER", "espacio": "Azul"}, "E08"),
                                     ({"personas": 8, "descripcion": "Zona Franca", "espacio": "Skilab"}, "E03")):
            with self.subTest(parametros=parametros):
                datos = self.solicitar_aula(fecha=FECHA, inicio="08:00", fin="10:00", **parametros).json()
                self.assertEqual(datos["datos"][0]["espacio_id"], esperado)
        self.aprobar_nueva(f"{FECHA}T08:00", f"{FECHA}T10:00", espacio="E08", personas=8)
        datos = self.solicitar_aula(conv="conv-zona-ocupada", fecha=FECHA, inicio="08:00", fin="10:00", personas=8,
                                    descripcion="Zona Franca").json()
        self.assertEqual(datos["datos"][0]["espacio_id"], "E07")

    def test_reevaluacion_conserva_preferencia_y_exige_otra_confirmacion(self):
        self.solicitar_aula(fecha=FECHA, inicio="08:00", fin="10:00", personas=8, descripcion="Zona Franca")
        self.aprobar_nueva(f"{FECHA}T08:00", f"{FECHA}T10:00", espacio="E08", personas=8)
        datos = self.confirmar().json()
        self.assertEqual(datos["estado"], "propuesta")
        self.assertEqual(datos["datos"][0]["espacio_id"], "E07")
        self.assertEqual(self.solicitudes_contadas(), 1)
        self.assertTrue(chat._cargar_borrador("dev-profesor", CONV)["datos"]["es_zona_franca"])

    def test_prompt_indica_usar_actividad_como_descripcion_y_reconoce_alias(self):
        prompt = chat._prompt("Clase de SER en Skilab", {"estado": "vacio", "datos": {}})
        self.assertIn('úsala como "descripcion"', prompt)
        self.assertIn("clase de inglés", prompt)
        self.assertIn("Skilab", prompt)
        self.assertIn("es_zona_franca", prompt)

    def test_recorrido_chat_confirmacion_aprobacion_y_calendario(self):
        propuesta = self.solicitar_aula(espacio="Blanca", fecha=FECHA, inicio="06:00", fin="08:00",
                                        personas=8, descripcion="Clase SER").json()
        self.assertEqual(propuesta["estado"], "propuesta")
        creada = self.confirmar().json()
        self.assertEqual(creada["estado"], "solicitud_creada")
        solicitud_id = creada["datos"][0]["id"]
        listado = self.api("profesor", "get", "/api/solicitudes").json()
        self.assertEqual(listado[0]["estado"], "pendiente")
        self.assertEqual(self.api("profesor", "post", f"/api/solicitudes/{solicitud_id}/aprobar").status_code, 403)
        self.assertEqual(self.aprobar(solicitud_id).json()["estado"], "aprobada")
        reservas = self.api("coordinadora", "get", f"/api/reservas?fecha={FECHA}").json()
        self.assertEqual([r["id"] for r in reservas], [solicitud_id])
        self.assertEqual(self.aprobar(solicitud_id).json()["codigo"], "no_pendiente")
        self.assertEqual(self.solicitudes_contadas(), 1)
        self.assertEqual(len(self.api("coordinadora", "get", f"/api/reservas?fecha={FECHA}").json()), 1)

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
        versiones = []

        def responder(prompt):
            # Ambas peticiones ya leyeron la misma versión antes de confirmar.
            versiones.append(chat._cargar_borrador(identidad.usuario_id, CONV)["version"])
            barrera.wait(timeout=10)
            return ia_json("confirmar")

        with mock.patch.object(ia, "consultar_ia", side_effect=responder):
            with ThreadPoolExecutor(max_workers=2) as ejecutor:
                futuros = [ejecutor.submit(procesar, identidad, "sí", CONV) for _ in range(2)]
                resultados = [f.result(timeout=15)["estado"] for f in futuros]

        self.assertEqual(versiones[0], versiones[1])
        self.assertEqual(sorted(resultados), ["solicitud_creada", "ya_creada"])
        self.assertEqual(self.solicitudes_contadas(), 1)

    def test_confirmacion_antigua_tras_modificar_personas_u_horario(self):
        identidad = Identidad("dev-profesor", "profesor", "desarrollo")
        for cambios in ({"personas": 20}, {"inicio": "11:00", "fin": "12:00"}):
            with self.subTest(cambios=cambios):
                self.solicitar_aula(espacio="Auditorio", fecha=FECHA, inicio="08:00", fin="10:00",
                                    personas=8, descripcion="Clase")
                anterior = chat._cargar_borrador(identidad.usuario_id, CONV)
                self.solicitar_aula(**cambios)
                vigente = chat._cargar_borrador(identidad.usuario_id, CONV)

                resultado = chat._confirmar(identidad, CONV, anterior)

                self.assertEqual(resultado["estado"], "propuesta_modificada")
                self.assertIn("Revise", resultado["respuesta"])
                self.assertEqual(self.solicitudes_contadas(), 0)
                self.assertEqual(chat._cargar_borrador(identidad.usuario_id, CONV), vigente)

    def test_confirmacion_en_curso_tras_cancelar_no_crea_ni_lanza_keyerror(self):
        self.solicitar_aula(fecha=FECHA, inicio="08:00", fin="10:00", personas=8, descripcion="Clase")
        identidad = Identidad("dev-profesor", "profesor", "desarrollo")
        anterior = chat._cargar_borrador(identidad.usuario_id, CONV)
        self.chatear("profesor", ia_json("cancelar"))
        cancelado = chat._cargar_borrador(identidad.usuario_id, CONV)

        resultado = chat._confirmar(identidad, CONV, anterior)

        self.assertEqual(resultado["estado"], "cancelada")
        self.assertEqual(self.solicitudes_contadas(), 0)
        self.assertEqual(chat._cargar_borrador(identidad.usuario_id, CONV), cancelado)

    def test_respuesta_tardia_de_ia_no_sobrescribe_ni_reactiva_borrador(self):
        identidad = Identidad("dev-profesor", "profesor", "desarrollo")
        for accion in ("solicitar_aula", "confirmar", "cancelar"):
            for cancelar in (False, True):
                with self.subTest(accion=accion, cancelar=cancelar):
                    self.solicitar_aula(fecha=FECHA, inicio="08:00", fin="10:00",
                                        personas=8, descripcion="Clase")
                    esperando = threading.Event()
                    continuar = threading.Event()

                    def responder(prompt):
                        esperando.set()
                        if not continuar.wait(timeout=10):
                            raise TimeoutError("No se liberó la respuesta de IA")
                        return ia_json(accion, personas=12)

                    with mock.patch.object(ia, "consultar_ia", side_effect=responder):
                        with ThreadPoolExecutor(max_workers=1) as ejecutor:
                            futuro = ejecutor.submit(procesar, identidad, "mensaje anterior", CONV)
                            try:
                                self.assertTrue(esperando.wait(timeout=10))
                                actual = chat._cargar_borrador(identidad.usuario_id, CONV)
                                if cancelar:
                                    chat._cancelar(identidad, CONV, actual)
                                else:
                                    chat._solicitar(identidad, CONV, actual, {"personas": 20})
                                vigente = chat._cargar_borrador(identidad.usuario_id, CONV)
                            finally:
                                continuar.set()
                            resultado = futuro.result(timeout=15)

                    self.assertEqual(resultado["estado"], "cancelada" if cancelar else "propuesta_modificada")
                    self.assertEqual(chat._cargar_borrador(identidad.usuario_id, CONV), vigente)
                    self.assertEqual(self.solicitudes_contadas(), 0)

    def test_version_no_se_reutiliza_al_volver_a_los_mismos_datos(self):
        self.solicitar_aula(fecha=FECHA, inicio="08:00", fin="10:00", personas=8, descripcion="Clase")
        identidad = Identidad("dev-profesor", "profesor", "desarrollo")
        anterior = chat._cargar_borrador(identidad.usuario_id, CONV)
        self.solicitar_aula(personas=20)
        self.solicitar_aula(personas=8)
        vigente = chat._cargar_borrador(identidad.usuario_id, CONV)
        self.assertEqual(anterior["datos"], vigente["datos"])
        self.assertNotEqual(anterior["version"], vigente["version"])
        self.assertEqual(chat._confirmar(identidad, CONV, anterior)["estado"], "propuesta_modificada")
        self.assertEqual(self.solicitudes_contadas(), 0)

    def test_borrador_existente_sin_version_se_puede_confirmar(self):
        self.solicitar_aula(fecha=FECHA, inicio="08:00", fin="10:00", personas=8, descripcion="Clase")
        identidad = Identidad("dev-profesor", "profesor", "desarrollo")
        datos = chat._cargar_borrador(identidad.usuario_id, CONV)["datos"]
        with db.transaccion() as con:
            con.execute("UPDATE borradores_chat SET datos = ?", (json.dumps(datos, ensure_ascii=False),))

        self.assertEqual(self.confirmar().json()["estado"], "solicitud_creada")
        self.assertEqual(self.confirmar().json()["estado"], "ya_creada")
        self.assertEqual(self.solicitudes_contadas(), 1)

    def test_respuesta_tardia_desde_borrador_vacio_no_sobrescribe_primera_propuesta(self):
        identidad = Identidad("dev-profesor", "profesor", "desarrollo")
        vigente = None

        def responder(prompt):
            nonlocal vigente
            # Intercalado determinista: otra petición termina mientras la primera espera a la IA.
            vacio = chat._cargar_borrador(identidad.usuario_id, CONV)
            chat._solicitar(identidad, CONV, vacio, {"personas": 20})
            vigente = chat._cargar_borrador(identidad.usuario_id, CONV)
            return ia_json("solicitar_aula", personas=8)

        with mock.patch.object(ia, "consultar_ia", side_effect=responder):
            resultado = procesar(identidad, "Necesito un aula para 8", CONV)

        self.assertEqual(resultado["estado"], "propuesta_modificada")
        self.assertEqual(chat._cargar_borrador(identidad.usuario_id, CONV), vigente)
        self.assertEqual(self.solicitudes_contadas(), 0)

    def test_reevaluacion_tras_conflicto_no_sobrescribe_cambio_posterior(self):
        self.solicitar_aula(espacio="Auditorio", fecha=FECHA, inicio="08:00", fin="10:00",
                            personas=8, descripcion="Clase")
        identidad = Identidad("dev-profesor", "profesor", "desarrollo")
        anterior = chat._cargar_borrador(identidad.usuario_id, CONV)
        self.aprobar_nueva(f"{FECHA}T09:00", f"{FECHA}T11:00", espacio="E01", personas=5)
        evaluar = chat._evaluar
        vigente = None

        def evaluar_tras_cancelar(usuario, conversacion, datos, esperado):
            nonlocal vigente
            chat._cancelar(identidad, CONV, anterior)
            vigente = chat._cargar_borrador(identidad.usuario_id, CONV)
            return evaluar(usuario, conversacion, datos, esperado)

        with mock.patch.object(chat, "_evaluar", side_effect=evaluar_tras_cancelar):
            resultado = chat._confirmar(identidad, CONV, anterior)

        self.assertEqual(resultado["estado"], "cancelada")
        self.assertEqual(chat._cargar_borrador(identidad.usuario_id, CONV), vigente)
        self.assertEqual(self.solicitudes_contadas(), 1)  # solo la solicitud previa

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
