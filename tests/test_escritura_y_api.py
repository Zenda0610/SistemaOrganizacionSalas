"""Fallos durante la escritura, códigos de error de la API y registro de importaciones."""
from unittest import mock

from fastapi.testclient import TestClient

from app import carga_datos
from app.main import app
from tests.base_prueba import BasePrueba


class PruebasEscritura(BasePrueba):
    def setUp(self):
        super().setUp()
        self.assertTrue(carga_datos.cargar_datos()["ok"])
        self.cambiar_aforo("E01", 99)

    def test_fallo_al_escribir_revierte_todo_el_reemplazo(self):
        original = carga_datos._insertar_validos
        llamadas = {"n": 0}

        def fallar_en_sesiones(con, tabla, archivo, validos):
            llamadas["n"] += 1
            if tabla == "sesiones":
                raise RuntimeError("fallo simulado de disco")
            return original(con, tabla, archivo, validos)

        with mock.patch.object(carga_datos, "_insertar_validos", side_effect=fallar_en_sesiones):
            resultado = carga_datos.cargar_datos()

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["error"]["codigo"], "error_escritura")
        self.assertEqual(self.aforo("E01"), 99)            # el espacio insertado antes se revirtió
        self.assertEqual(self.contar("espacios"), 10)
        self.assertEqual(self.contar("sesiones"), 37)
        self.assertEqual(self.contar("cohortes"), 9)

    def test_registra_cada_intento_aunque_falle(self):
        (self.carpeta_datos / "cohortes.csv").unlink()

        carga_datos.cargar_datos()

        ultima = carga_datos.consultar_calidad()["ultima_importacion"]
        self.assertFalse(ultima["exito"])
        self.assertEqual(ultima["codigo"], "archivo_ausente")
        self.assertEqual(ultima["archivo"], "cohortes.csv")


class PruebasApi(BasePrueba):
    def setUp(self):
        super().setUp()
        self.assertTrue(carga_datos.cargar_datos()["ok"])
        self.cambiar_aforo("E01", 99)

    def test_recargar_con_archivo_ausente_responde_422_y_conserva_datos(self):
        (self.carpeta_datos / "espacios.csv").unlink()

        with TestClient(app) as cliente:
            respuesta = cliente.post("/api/datos/recargar")
            espacios = cliente.get("/api/espacios").json()

        self.assertEqual(respuesta.status_code, 422)
        self.assertEqual(respuesta.json()["codigo"], "archivo_ausente")
        self.assertIn("espacios.csv", respuesta.json()["mensaje"])
        self.assertEqual(next(e["aforo"] for e in espacios if e["id"] == "E01"), 99)

    def test_recargar_correcto_responde_200(self):
        with TestClient(app) as cliente:
            respuesta = cliente.post("/api/datos/recargar")

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()["ok"])

    def test_calidad_incluye_la_ultima_importacion(self):
        (self.carpeta_datos / "espacios.csv").unlink()
        carga_datos.cargar_datos()

        with TestClient(app) as cliente:
            calidad = cliente.get("/api/calidad-datos").json()

        self.assertFalse(calidad["ultima_importacion"]["exito"])
        self.assertEqual(calidad["ultima_importacion"]["codigo"], "archivo_ausente")


if __name__ == "__main__":
    import unittest
    unittest.main()
