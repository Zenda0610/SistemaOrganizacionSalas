"""El arranque de la aplicación no debe reemplazar datos existentes."""
from fastapi.testclient import TestClient

from app import carga_datos
from app.main import app
from tests.base_prueba import BasePrueba


class PruebasArranque(BasePrueba):
    def test_arrancar_conserva_un_cambio_guardado(self):
        carga_datos.cargar_datos()
        self.cambiar_aforo("E01", 99)

        with TestClient(app) as cliente:  # ejecuta el arranque de la aplicación
            respuesta = cliente.get("/api/espacios")

        self.assertEqual(respuesta.status_code, 200)
        aforo_auditorio = next(e["aforo"] for e in respuesta.json() if e["id"] == "E01")
        self.assertEqual(aforo_auditorio, 99)

    def test_importar_dos_veces_no_duplica_registros(self):
        carga_datos.cargar_datos()
        carga_datos.cargar_datos()

        self.assertEqual(self.contar("espacios"), 10)
        self.assertEqual(self.contar("sesiones"), 37)
        self.assertEqual(self.contar("cohortes"), 9)


if __name__ == "__main__":
    import unittest
    unittest.main()
