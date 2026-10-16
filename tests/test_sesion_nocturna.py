"""Sesiones fuera del antiguo horario 06:00–18:00: la importación las acepta cuando la hora es válida.

Límite del esquema: una sesión del CSV no puede cruzar medianoche ni terminar a las 24:00,
porque inicio y fin se guardan dentro del mismo día. Esos casos se rechazan como fila inválida.
"""
from fastapi.testclient import TestClient

from app import carga_datos, db
from app.main import app
from tests.base_prueba import BasePrueba

FILA = "{id},E01,2026-11-02,{inicio},{fin},clase,software,no,NOC-01,basico,20,Coordinacion Nocturna,programada"


class PruebasSesionNocturna(BasePrueba):
    def agregar_sesiones(self, *filas):
        ruta = self.carpeta_datos / "sesiones.csv"
        texto = ruta.read_text(encoding="utf-8")
        if not texto.endswith("\n"):
            texto += "\n"
        ruta.write_text(texto + "\n".join(filas) + "\n", encoding="utf-8")

    def motivo_de_rechazo(self, sesion_id):
        """Motivo con el que se rechazó la fila de esa sesión. Ignora los rechazos del CSV de ejemplo."""
        filas = db.consultar(
            "SELECT motivo FROM registros_rechazados WHERE archivo = 'sesiones.csv' AND contenido LIKE ?",
            (f"%{sesion_id}%",))
        self.assertEqual(len(filas), 1, sesion_id)
        return filas[0]["motivo"]

    def test_sesion_nocturna_valida_se_guarda_y_bloquea_el_aula_en_su_horario(self):
        self.agregar_sesiones(FILA.format(id="S90", inicio="22:00", fin="23:00"))

        resultado = carga_datos.cargar_datos()

        self.assertTrue(resultado["ok"])
        guardada = db.consultar("SELECT hora_inicio, hora_fin, fecha FROM sesiones WHERE id = 'S90'")
        self.assertEqual([(g["fecha"], g["hora_inicio"], g["hora_fin"]) for g in guardada],
                         [("2026-11-02", "22:00", "23:00")])
        with TestClient(app) as cliente:
            durante = [e["id"] for e in cliente.get("/api/disponibilidad", params={
                "inicio": "2026-11-02T22:00", "fin": "2026-11-02T23:00"}).json()]
            despues = [e["id"] for e in cliente.get("/api/disponibilidad", params={
                "inicio": "2026-11-02T23:00", "fin": "2026-11-02T23:30"}).json()]
        self.assertNotIn("E01", durante)
        self.assertIn("E01", despues)

    def test_sesion_de_madrugada_se_guarda(self):
        self.agregar_sesiones(FILA.format(id="S92", inicio="00:00", fin="02:00"))
        self.assertTrue(carga_datos.cargar_datos()["ok"])
        self.assertEqual(db.consultar("SELECT COUNT(*) AS n FROM sesiones WHERE id = 'S92'")[0]["n"], 1)

    def test_sesion_que_cruza_medianoche_se_rechaza_sin_detener_la_carga(self):
        self.agregar_sesiones(FILA.format(id="S91", inicio="22:00", fin="02:00"))

        resultado = carga_datos.cargar_datos()

        self.assertTrue(resultado["ok"])
        self.assertEqual(db.consultar("SELECT COUNT(*) AS n FROM sesiones WHERE id = 'S91'")[0]["n"], 0)
        self.assertIn("posterior", self.motivo_de_rechazo("S91"))

    def test_sesion_que_termina_a_medianoche_se_rechaza(self):
        self.agregar_sesiones(FILA.format(id="S93", inicio="22:00", fin="24:00"))
        self.assertTrue(carga_datos.cargar_datos()["ok"])
        self.assertEqual(db.consultar("SELECT COUNT(*) AS n FROM sesiones WHERE id = 'S93'")[0]["n"], 0)
        self.assertIn("24:00", self.motivo_de_rechazo("S93"))

    def test_los_bloques_de_minutos_siguen_validandose(self):
        self.agregar_sesiones(FILA.format(id="S94", inicio="22:07", fin="23:00"))
        self.assertTrue(carga_datos.cargar_datos()["ok"])
        self.assertEqual(db.consultar("SELECT COUNT(*) AS n FROM sesiones WHERE id = 'S94'")[0]["n"], 0)
        self.assertIn("bloques de 15 minutos", self.motivo_de_rechazo("S94"))


if __name__ == "__main__":
    import unittest
    unittest.main()
