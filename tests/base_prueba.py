"""Base común para las pruebas: cada prueba usa una base SQLite y una copia de los CSV en una carpeta temporal.

Nunca toca la base de datos real ni los archivos originales de data/.
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from app import config, db

ORIGEN_DATOS = Path(__file__).resolve().parent.parent / "data" / "ficticio"


class BasePrueba(unittest.TestCase):
    def setUp(self):
        self._carpeta = tempfile.TemporaryDirectory()
        raiz = Path(self._carpeta.name)
        self.carpeta_datos = raiz / "datos"
        shutil.copytree(ORIGEN_DATOS, self.carpeta_datos)
        self._configuracion_previa = (config.RUTA_BASE_DATOS, config.RUTA_DATOS)
        config.RUTA_BASE_DATOS = str(raiz / "prueba.db")
        config.RUTA_DATOS = str(self.carpeta_datos)
        db.inicializar_base()
        self.usar_identidad(None)

    def usar_identidad(self, rol):
        """Fija la identidad de desarrollo del servidor para la prueba. None = sin identidad."""
        previa = (config.USUARIO_DESARROLLO, config.ROL_DESARROLLO)
        config.USUARIO_DESARROLLO = "dev-prueba" if rol else ""
        config.ROL_DESARROLLO = rol or ""
        self.addCleanup(self._restaurar_identidad, previa)

    @staticmethod
    def _restaurar_identidad(previa):
        config.USUARIO_DESARROLLO, config.ROL_DESARROLLO = previa

    def tearDown(self):
        config.RUTA_BASE_DATOS, config.RUTA_DATOS = self._configuracion_previa
        self._carpeta.cleanup()

    def contar(self, tabla: str) -> int:
        return db.consultar(f"SELECT COUNT(*) AS total FROM {tabla}")[0]["total"]

    def cambiar_aforo(self, espacio_id: str, aforo: int) -> None:
        """Simula un cambio guardado en la base, como lo haría una edición futura."""
        con = db.conectar()
        try:
            con.execute("UPDATE espacios SET aforo = ? WHERE id = ?", (aforo, espacio_id))
            con.commit()
        finally:
            con.close()

    def aforo(self, espacio_id: str) -> int:
        return db.consultar("SELECT aforo FROM espacios WHERE id = ?", (espacio_id,))[0]["aforo"]
