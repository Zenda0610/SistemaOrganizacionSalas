"""Catálogo de demostración limpio y contrato OpenRouter (HTTP simulado)."""
import csv
import unittest
import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

import httpx

from app import carga_datos, chat, config, db, ia, reglas
from tests.base_prueba import BasePrueba


class PruebasCatalogo(BasePrueba):
    def test_catalogo_demo_confirmado_sin_ocupaciones_inventadas(self):
        config.RUTA_DATOS = str(Path(__file__).resolve().parent.parent / "data" / "ficticio")
        resultado = carga_datos.cargar_datos()
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["rechazados"], {"espacios.csv": 0, "sesiones.csv": 0, "cohortes.csv": 0})
        self.assertEqual(self.contar("espacios"), 9)
        self.assertEqual(self.contar("sesiones"), 0)
        self.assertEqual(self.contar("cohortes"), 0)
        with (Path(config.RUTA_DATOS) / "espacios.csv").open(encoding="utf-8") as archivo:
            datos = {r["nombre"]: int(r["aforo"]) for r in csv.DictReader(archivo)}
        self.assertEqual(datos, {"Auditorio": 100, "Cosmos": 25, "Skilab": 20, "Spooki": 38,
                                "Apolo": 34, "Blanca": 12, "Azul": 10, "Amarillas verdes": 6, "Artemis": 32})

    def test_id_exacto_precede_alias_y_no_se_inventa_equivalencia(self):
        catalogo = [{"id": "E08", "nombre": "Auditorio", "aforo": 100},
                    {"id": "OF-A", "nombre": "Azul", "aforo": 10}]
        self.assertEqual(chat.resolver_espacio("E08", catalogo)[1]["nombre"], "Auditorio")
        self.assertEqual(chat.resolver_espacio("Sala Azul", catalogo)[1]["id"], "OF-A")
        self.assertEqual(reglas.ordenar_candidatos(catalogo, True)[0]["id"], "OF-A")
        self.assertEqual(chat.resolver_espacio("Amarillas verdes", [{"id": "E09", "nombre": "Cubiculo Amarillo"}]),
                         ("no_existe", None))

    def test_alias_ambiguo_no_elige_primera_aula(self):
        catalogo = [{"id": "X", "nombre": "Azul"}, {"id": "Y", "nombre": "Azul"}]
        self.assertEqual(chat.resolver_espacio("Sala Azul", catalogo)[0], "ambiguo")
        self.assertEqual(chat.resolver_espacio("Azul", catalogo)[0], "ambiguo")


class PruebasOpenRouter(unittest.TestCase):
    def setUp(self):
        for campo, valor in {"IA_PROVEEDOR": "openai", "IA_URL": "https://openrouter.ai/api/v1",
                             "IA_MODELO": "nvidia/nemotron-3.5-super-vl:free", "IA_API_KEY": "clave-ficticia-test"}.items():
            parche = mock.patch.object(config, campo, valor)
            parche.start()
            self.addCleanup(parche.stop)

    def test_sin_clave_no_envia_peticion(self):
        with mock.patch.object(config, "IA_API_KEY", ""), mock.patch.object(httpx, "post") as post:
            self.assertFalse(ia.consultar_ia("prueba")["ok"])
            post.assert_not_called()

    def test_modelo_de_pago_no_envia_peticion(self):
        with mock.patch.object(config, "IA_MODELO", "nvidia/modelo"), mock.patch.object(httpx, "post") as post:
            self.assertFalse(ia.consultar_ia("prueba")["ok"])
            post.assert_not_called()

    def test_catalogo_retirado_o_con_precio_no_envia_inferencia(self):
        for datos in ({"data": []}, {"data": [{"id": config.IA_MODELO, "pricing": {"prompt": "1", "completion": "0"}}]}):
            with self.subTest(datos=datos), mock.patch.object(httpx, "get", return_value=httpx.Response(200, json=datos,
                         request=httpx.Request("GET", config.IA_URL + "/models"))), mock.patch.object(httpx, "post") as post:
                self.assertFalse(ia.consultar_ia("prueba")["ok"])
                post.assert_not_called()

    def test_cliente_envia_modelo_explicito_sin_fallback_de_pago(self):
        catalogo = {"data": [{"id": config.IA_MODELO, "pricing": {"prompt": "0", "completion": "0"}}]}
        with mock.patch.object(httpx, "get", return_value=httpx.Response(200, json=catalogo,
                     request=httpx.Request("GET", config.IA_URL + "/models"))), mock.patch.object(httpx, "post", return_value=httpx.Response(200,
                     json={"choices": [{"message": {"content": "ok"}}]}, request=httpx.Request("POST", config.IA_URL))) as post:
            self.assertTrue(ia.consultar_ia("prueba")["ok"])
            self.assertEqual(post.call_args.args[0], config.IA_URL + "/chat/completions")
            cuerpo = post.call_args.kwargs["json"]
            self.assertEqual(cuerpo["model"], config.IA_MODELO)
            self.assertEqual(cuerpo["provider"], {"allow_fallbacks": False, "max_price": {"prompt": 0, "completion": 0}})
            self.assertNotIn("models", cuerpo)


class PruebasMigracion(unittest.TestCase):
    def test_base_anterior_y_borrador_se_conservan_al_iniciar_dos_veces(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = str(Path(carpeta) / "anterior.db")
            with sqlite3.connect(ruta) as con:
                con.executescript(db.ESQUEMA)  # tablas originales sin las columnas añadidas por la migración
                con.execute("INSERT INTO borradores_chat (usuario_id,conversacion_id,estado,datos) VALUES ('usuario','conv-anterior','en_curso','{}')")
                con.execute("INSERT INTO espacios (id,nombre,tipo,aforo,estado,archivo_origen,fila_origen) VALUES ('oficial','Azul','sala',10,'activo','anterior',1)")
            con.close()
            with mock.patch.object(config, "RUTA_BASE_DATOS", ruta):
                db.inicializar_base()
                db.inicializar_base()
                self.assertEqual(chat._cargar_borrador("usuario", "conv-anterior")["estado"], "en_curso")
                self.assertEqual(db.consultar("SELECT nombre,elementos FROM espacios")[0], {"nombre": "Azul", "elementos": None})
