"""Reglas de devolución y preferencia entre aulas disponibles con aforo suficiente."""
from datetime import datetime, timedelta

from app import config

FORMATO = "%Y-%m-%d %H:%M"


def hora_devolucion(fin_texto: str) -> str:
    """La devolución es informativa: no cambia el final del intervalo reservado."""
    fin = datetime.strptime(fin_texto, FORMATO)
    return (fin - timedelta(minutes=config.MINUTOS_DEVOLUCION_ANTICIPADA)).strftime(FORMATO)


def ordenar_candidatos(candidatos: list[dict], es_zona_franca: bool = False) -> list[dict]:
    """Recibe aulas ya filtradas por disponibilidad y aforo. No modifica la lista original."""
    return sorted(candidatos, key=lambda aula: (
        aula["id"] != "E08" if es_zona_franca else aula["id"] == "E08",
        aula["aforo"], aula["id"],
    ))
