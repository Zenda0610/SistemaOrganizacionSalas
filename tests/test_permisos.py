"""Permisos por rol: matriz completa y respuestas de la API ante identidad y permisos.

La identidad sale solo de la configuración del servidor. Estas pruebas confirman que
ningún dato de la petición (cuerpo, cabecera o query) cambia el rol.
"""
import unittest

from fastapi.testclient import TestClient

from app import carga_datos
from app.identidad import ROLES
from app.main import app
from app.permisos import PERMISOS, tiene_permiso
from tests.base_prueba import BasePrueba

ESPERADO = {
    "solicitar_aula_academica": {"profesor", "administrativo"},
    "solicitar_alquiler_comercial": {"estudiante", "empresa"},
    "autorizar_solicitud": {"coordinadora"},
    "recargar_datos": {"coordinadora"},
}


class PruebasMatriz(unittest.TestCase):
    def test_cada_rol_tiene_exactamente_los_permisos_esperados(self):
        for permiso, roles_esperados in ESPERADO.items():
            for rol in ROLES:
                with self.subTest(rol=rol, permiso=permiso):
                    self.assertEqual(tiene_permiso(rol, permiso), rol in roles_esperados)

    def test_la_matriz_no_tiene_permisos_fuera_de_lo_esperado(self):
        self.assertEqual(set(PERMISOS), set(ESPERADO))

    def test_permiso_desconocido_se_niega_a_todos_los_roles(self):
        for rol in ROLES:
            self.assertFalse(tiene_permiso(rol, "permiso_inventado"))

    def test_rol_desconocido_no_tiene_permisos(self):
        self.assertFalse(tiene_permiso("root", "recargar_datos"))


class PruebasAccesoApi(BasePrueba):
    def setUp(self):
        super().setUp()
        self.assertTrue(carga_datos.cargar_datos()["ok"])
        self.cambiar_aforo("E01", 99)

    def _recargar(self, **peticion):
        with TestClient(app) as cliente:
            return cliente.post("/api/datos/recargar", **peticion)

    def test_sin_identidad_responde_401_y_no_importa(self):
        self.usar_identidad(None)
        importaciones_antes = self.contar("importaciones")

        respuesta = self._recargar()

        self.assertEqual(respuesta.status_code, 401)
        self.assertEqual(respuesta.json()["codigo"], "sin_identidad")
        self.assertEqual(self.contar("importaciones"), importaciones_antes)
        self.assertEqual(self.aforo("E01"), 99)

    def test_rol_no_reconocido_responde_401(self):
        self.usar_identidad("root")
        self.assertEqual(self._recargar().json()["codigo"], "sin_identidad")

    def test_roles_sin_permiso_responden_403_y_no_importan(self):
        for rol in ("profesor", "administrativo", "estudiante", "empresa"):
            with self.subTest(rol=rol):
                self.usar_identidad(rol)
                importaciones_antes = self.contar("importaciones")

                respuesta = self._recargar()

                self.assertEqual(respuesta.status_code, 403)
                self.assertEqual(respuesta.json()["codigo"], "sin_permiso")
                self.assertEqual(self.contar("importaciones"), importaciones_antes)
                self.assertEqual(self.aforo("E01"), 99)

    def test_coordinadora_puede_recargar(self):
        self.usar_identidad("coordinadora")
        self.assertEqual(self._recargar().status_code, 200)

    def test_el_cuerpo_no_cambia_el_rol(self):
        self.usar_identidad("profesor")
        respuesta = self._recargar(json={"rol": "coordinadora", "ok": True})
        self.assertEqual(respuesta.status_code, 403)

    def test_la_cabecera_no_cambia_el_rol(self):
        self.usar_identidad("profesor")
        respuesta = self._recargar(headers={"X-Rol": "coordinadora", "X-Usuario": "dev-coordinadora"})
        self.assertEqual(respuesta.status_code, 403)

    def test_la_query_no_cambia_el_rol(self):
        self.usar_identidad("profesor")
        with TestClient(app) as cliente:
            respuesta = cliente.post("/api/datos/recargar?rol=coordinadora")
        self.assertEqual(respuesta.status_code, 403)

    def test_sesion_refleja_solo_la_configuracion_del_servidor(self):
        self.usar_identidad("profesor")
        with TestClient(app) as cliente:
            respuesta = cliente.get("/api/sesion", headers={"X-Rol": "coordinadora"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {"usuario_id": "dev-prueba", "rol": "profesor", "origen": "desarrollo"})

    def test_sesion_sin_identidad_responde_401(self):
        self.usar_identidad(None)
        with TestClient(app) as cliente:
            respuesta = cliente.get("/api/sesion")
        self.assertEqual(respuesta.status_code, 401)
        self.assertEqual(respuesta.json()["codigo"], "sin_identidad")


if __name__ == "__main__":
    unittest.main()
