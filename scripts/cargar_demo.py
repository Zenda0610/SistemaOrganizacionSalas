"""Carga explícita de datos ficticios en demo.sqlite sin sustituir la base operativa."""
import csv
import json
from pathlib import Path

from app import carga_datos, config, db
from app.operaciones import EquipoNuevo


def cargar_demo():
    raiz = Path(__file__).resolve().parent.parent
    config.RUTA_BASE_DATOS = str(raiz / 'demo.sqlite')
    config.RUTA_DATOS = str(raiz / 'data' / 'ficticio')
    with (Path(config.RUTA_DATOS) / 'equipos.csv').open(encoding='utf-8', newline='') as archivo:
        equipos = [EquipoNuevo(**fila) for fila in csv.DictReader(archivo)]
    if len({e.id for e in equipos}) != len(equipos) or any(not e.ficticio for e in equipos):
        raise ValueError('La demo requiere identificadores únicos y equipos explícitamente ficticios.')
    db.inicializar_base()
    with db.transaccion() as con:
        for equipo in equipos:
            anterior = con.execute('SELECT nombre,ficticio FROM equipos WHERE id=?', (equipo.id,)).fetchone()
            if anterior and (not anterior['ficticio'] or anterior['nombre'] != equipo.nombre):
                raise ValueError('Colisión de inventario: no se reemplazan equipos existentes.')
    resultado = carga_datos.cargar_datos()
    if not resultado['ok']:
        return resultado
    with db.transaccion() as con:
        for equipo in equipos:
            con.execute('INSERT OR IGNORE INTO equipos(id,nombre,estado,ficticio) VALUES (?,?,?,1)',
                        (equipo.id, equipo.nombre, equipo.estado))
    return {**resultado, 'base_demo': config.RUTA_BASE_DATOS,
            'equipos_ficticios': db.consultar('SELECT COUNT(*) AS total FROM equipos WHERE ficticio=1')[0]['total']}


if __name__ == '__main__':
    resultado_demo = cargar_demo()
    print(json.dumps(resultado_demo, ensure_ascii=False, indent=2))
    raise SystemExit(0 if resultado_demo['ok'] else 1)
