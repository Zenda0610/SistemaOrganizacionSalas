"""Una importación fallida no debe modificar la carga anterior."""
from unittest import mock

from app import carga_datos, db
from tests.base_prueba import BasePrueba


class PruebasValidacionAntesDeReemplazar(BasePrueba):
    def setUp(self):
        super().setUp()
        resultado = carga_datos.cargar_datos()
        self.assertTrue(resultado["ok"])
        self.cambiar_aforo("E01", 99)  # cambio guardado que debe sobrevivir a una importación fallida

    def afirmar_datos_intactos(self):
        self.assertEqual(self.aforo("E01"), 99)
        self.assertEqual(self.contar("espacios"), 10)
        self.assertEqual(self.contar("sesiones"), 37)
        self.assertEqual(self.contar("cohortes"), 9)

    def test_archivo_obligatorio_ausente_conserva_datos(self):
        (self.carpeta_datos / "espacios.csv").unlink()

        resultado = carga_datos.cargar_datos()

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["error"]["codigo"], "archivo_ausente")
        self.assertEqual(resultado["error"]["archivo"], "espacios.csv")
        self.afirmar_datos_intactos()

    def test_estructura_incompatible_conserva_datos(self):
        ruta = self.carpeta_datos / "espacios.csv"
        ruta.write_text(ruta.read_text(encoding="utf-8").replace("aforo", "capacidad", 1), encoding="utf-8")

        resultado = carga_datos.cargar_datos()

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["error"]["codigo"], "estructura_incompatible")
        self.assertIn("aforo", resultado["error"]["mensaje"])
        self.afirmar_datos_intactos()

    def test_archivo_no_legible_conserva_datos(self):
        (self.carpeta_datos / "sesiones.csv").write_bytes(b"\xff\xfe\x00\x81 no es utf-8 \x9d")

        resultado = carga_datos.cargar_datos()

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["error"]["codigo"], "archivo_no_legible")
        self.afirmar_datos_intactos()

    def test_fila_invalida_no_impide_cargar_las_validas(self):
        ruta = self.carpeta_datos / "sesiones.csv"
        fila_invalida = "S99,E04,2026-10-19,10:00,09:00,clase,software,no,SW-X,,5,Prueba,programada\n"
        ruta.write_text(ruta.read_text(encoding="utf-8") + fila_invalida, encoding="utf-8")

        resultado = carga_datos.cargar_datos()

        self.assertTrue(resultado["ok"])
        self.assertEqual(self.contar("sesiones"), 37)
        motivos = db.consultar("SELECT motivo FROM registros_rechazados WHERE archivo = 'sesiones.csv' AND fila = 42")
        self.assertEqual(len(motivos), 1)
        self.assertIn("hora fin", motivos[0]["motivo"])

    def test_error_inesperado_de_validacion_no_se_propaga(self):
        with mock.patch.object(carga_datos, "_validar_todo", side_effect=RuntimeError("fallo inesperado")):
            resultado = carga_datos.cargar_datos()

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["error"]["codigo"], "error_interno")
        self.afirmar_datos_intactos()


if __name__ == "__main__":
    import unittest
    unittest.main()
