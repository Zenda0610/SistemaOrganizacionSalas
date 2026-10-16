"""Tarifa por hora de cada aula. La edita la coordinadora y sobrevive a la recarga de CSV.

Tarifa efectiva: la de tarifas_aula si existe (NULL = quitada, Por definir); si no, la de espacios.csv.
"""
import math

from app import config, db
from app.solicitudes import ErrorSolicitud, tarifa_efectiva as efectiva


def _validar(cuerpo) -> float | None:
    if not isinstance(cuerpo, dict) or set(cuerpo) != {"tarifa_hora"}:
        raise ErrorSolicitud(422, "tarifa_no_valida", 'Envíe solo {"tarifa_hora": número o null}.')
    valor = cuerpo["tarifa_hora"]
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
        raise ErrorSolicitud(422, "tarifa_no_valida", "La tarifa debe ser un número en pesos colombianos, sin texto ni símbolos.")
    if valor < 0:
        raise ErrorSolicitud(422, "tarifa_no_valida", "La tarifa no puede ser negativa.")
    if valor > config.TARIFA_HORA_MAXIMA:
        raise ErrorSolicitud(422, "tarifa_no_valida",
                             f"La tarifa supera el máximo permitido de {config.TARIFA_HORA_MAXIMA:,.0f} COP por hora.".replace(",", "."))
    return float(valor)


def actualizar(espacio_id: str, cuerpo, identidad) -> dict:
    tarifa = _validar(cuerpo)
    with db.transaccion() as con:
        if con.execute("SELECT 1 FROM espacios WHERE id = ?", (espacio_id,)).fetchone() is None:
            raise ErrorSolicitud(404, "espacio_no_encontrado", "No existe el aula indicada.")
        anterior = efectiva(con, espacio_id)
        con.execute("INSERT INTO tarifas_aula (espacio_id, tarifa_hora, actualizado_por) VALUES (?, ?, ?) "
                    "ON CONFLICT (espacio_id) DO UPDATE SET tarifa_hora = excluded.tarifa_hora, "
                    "actualizado_por = excluded.actualizado_por, actualizado_en = datetime('now', 'localtime')",
                    (espacio_id, tarifa, identidad.usuario_id))
        con.execute("INSERT INTO historial_tarifas (espacio_id, valor_anterior, valor_nuevo, cambiado_por) VALUES (?, ?, ?, ?)",
                    (espacio_id, anterior, tarifa, identidad.usuario_id))
    return {"espacio_id": espacio_id, "tarifa_hora": tarifa, "tarifa_anterior": anterior}
