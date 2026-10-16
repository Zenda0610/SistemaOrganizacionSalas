"""La recarga respeta las reservas aprobadas: rechazo completo ante incompatibilidad, aplicación si es compatible."""
from app import db
from tests.test_solicitudes import BaseSolicitudes


class PruebasRecargaConReservas(BaseSolicitudes):
    def recargar(self):
        return self.api("coordinadora", "post", "/api/datos/recargar")

    def reemplazar_en_csv(self, archivo, viejo, nuevo):
        ruta = self.carpeta_datos / archivo
        texto = ruta.read_text(encoding="utf-8")
        assert texto.count(viejo) == 1, viejo
        ruta.write_text(texto.replace(viejo, nuevo), encoding="utf-8")

    def ultima_importacion(self):
        return db.consultar("SELECT exito, codigo FROM importaciones ORDER BY id DESC LIMIT 1")[0]

    def test_sesion_restaurada_bajo_reserva_aprobada_rechaza_toda_la_importacion(self):
        # El caso reproducido: se cancelan las sesiones de E04, se aprueba una reserva en ese horario
        # y la recarga restaura las sesiones programadas.
        self.cancelar_sesion("S01")
        self.cancelar_sesion("S02")
        self.assertEqual(self.aprobar_nueva("2026-10-19T09:00", "2026-10-19T10:00", espacio="E04", personas=5).status_code, 200)

        respuesta = self.recargar()

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.json()["codigo"], "reserva_incompatible")
        self.assertEqual(respuesta.json()["archivo"], "sesiones.csv")
        self.assertIn("se cruza con la sesión", respuesta.json()["mensaje"])
        # La base queda como estaba: las sesiones siguen canceladas y la reserva sigue aprobada.
        estados = {s["id"]: s["estado"] for s in db.consultar("SELECT id, estado FROM sesiones WHERE id IN ('S01','S02')")}
        self.assertEqual(estados, {"S01": "cancelada", "S02": "cancelada"})
        reserva = db.consultar("SELECT estado, inicio, fin FROM solicitudes")[0]
        self.assertEqual((reserva["estado"], reserva["inicio"], reserva["fin"]),
                         ("aprobada", "2026-10-19 09:00", "2026-10-19 10:00"))
        self.assertFalse(self.ultima_importacion()["exito"])
        self.assertEqual(self.ultima_importacion()["codigo"], "reserva_incompatible")

    def test_el_rechazo_revierte_todo_el_reemplazo(self):
        self.cambiar_aforo("E02", 77)  # cambio guardado: debe seguir tras el rechazo
        self.cancelar_sesion("S01")
        self.cancelar_sesion("S02")
        self.aprobar_nueva("2026-10-19T09:00", "2026-10-19T10:00", espacio="E04", personas=5)

        self.assertEqual(self.recargar().status_code, 409)

        self.assertEqual(self.aforo("E02"), 77)
        self.assertEqual(self.contar("espacios"), 10)
        self.assertEqual(self.contar("sesiones"), 37)

    def test_aforo_menor_en_el_csv_rechaza_la_reserva_existente(self):
        self.assertEqual(self.aprobar_nueva("2026-11-02T08:00", "2026-11-02T09:00", espacio="E02", personas=20).status_code, 200)
        self.reemplazar_en_csv("espacios.csv", "E02,Cosmos,salon,25,activo", "E02,Cosmos,salon,10,activo")

        respuesta = self.recargar()

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.json()["archivo"], "espacios.csv")
        self.assertIn("aforo", respuesta.json()["mensaje"])

    def test_espacio_en_mantenimiento_en_el_csv_rechaza_la_reserva_existente(self):
        self.assertEqual(self.aprobar_nueva("2026-11-02T08:00", "2026-11-02T09:00").status_code, 200)
        self.reemplazar_en_csv("espacios.csv", "E01,Auditorio,auditorio,100,activo", "E01,Auditorio,auditorio,100,mantenimiento")

        respuesta = self.recargar()

        self.assertEqual(respuesta.status_code, 409)
        self.assertIn("no está activo", respuesta.json()["mensaje"])

    def test_recarga_compatible_aplica_el_csv_y_conserva_la_reserva(self):
        self.assertEqual(self.aprobar_nueva("2026-11-02T08:00", "2026-11-02T09:00").status_code, 200)
        self.cambiar_aforo("E01", 99)

        respuesta = self.recargar()

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()["ok"])
        self.assertEqual(self.aforo("E01"), 100)  # el CSV volvió a aplicarse
        reservas = db.consultar("SELECT estado, inicio, fin FROM solicitudes")
        self.assertEqual([(r["estado"], r["inicio"], r["fin"]) for r in reservas],
                         [("aprobada", "2026-11-02 08:00", "2026-11-02 09:00")])
        self.assertTrue(self.ultima_importacion()["exito"])


if __name__ == "__main__":
    import unittest
    unittest.main()
