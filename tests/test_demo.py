"""La carga de demo es repetible y no sustituye inventario existente."""
import shutil
from pathlib import Path
from unittest import mock

from app import db, operaciones
from app.identidad import Identidad
from scripts import cargar_demo
from tests.base_prueba import BasePrueba


class PruebasDemo(BasePrueba):
    def setUp(self):
        super().setUp()
        raiz = Path(self._carpeta.name)
        origen = Path(__file__).resolve().parent.parent / 'data' / 'ficticio'
        shutil.copytree(origen, raiz / 'data' / 'ficticio')
        parche = mock.patch.object(cargar_demo, '__file__', str(raiz / 'scripts' / 'cargar_demo.py'))
        parche.start()
        self.addCleanup(parche.stop)

    def test_carga_repetida_conserva_prestamo_y_estado_de_equipos(self):
        resultado = cargar_demo.cargar_demo()
        self.assertEqual(resultado['equipos_ficticios'], 8)
        self.assertEqual(resultado['cargados']['sesiones.csv'], 15)
        self.assertEqual(resultado['rechazados']['sesiones.csv'], 1)
        self.assertEqual(resultado['conflictos'], 2)
        profesor = Identidad('profesor-ficticio', 'profesor', 'desarrollo')
        operaciones.prestar(operaciones.PrestamoNuevo(equipo_id='DEMO-EQ-01', responsable=profesor.usuario_id), profesor)
        with db.transaccion() as con:
            con.execute("UPDATE equipos SET estado='mantenimiento' WHERE id='DEMO-EQ-02'")
        self.assertTrue(cargar_demo.cargar_demo()['ok'])
        self.assertEqual(self.contar('equipos'), 8)
        self.assertEqual(self.contar('prestamos'), 1)
        self.assertEqual(db.consultar("SELECT estado FROM equipos WHERE id='DEMO-EQ-02'")[0]['estado'], 'mantenimiento')

    def test_colision_no_sustituye_inventario(self):
        cargar_demo.cargar_demo()
        with db.transaccion() as con:
            con.execute("UPDATE equipos SET ficticio=0 WHERE id='DEMO-EQ-01'")
        with self.assertRaises(ValueError):
            cargar_demo.cargar_demo()
        self.assertEqual(db.consultar("SELECT ficticio FROM equipos WHERE id='DEMO-EQ-01'")[0]['ficticio'], 0)
