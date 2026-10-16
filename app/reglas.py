"""Reglas de devolución y preferencia entre aulas disponibles con aforo suficiente."""
from datetime import datetime, timedelta
import unicodedata
import re

from app import config

FORMATO = "%Y-%m-%d %H:%M"

# Equivalencias de nombre, nunca identificadores del dataset.
ALIAS_AULAS = ({"skilab", "skylab"}, {"spooki", "sputnik"},
               {"blanca", "sala blanca"}, {"azul", "sala azul"})


def normalizar(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto)
    return " ".join("".join(c for c in base if not unicodedata.combining(c)).lower().split())


def es_azul(aula: dict) -> bool:
    objetivo = normalizar(config.AULA_PREFERIDA_ZONA_FRANCA)
    equivalentes = next((grupo for grupo in ALIAS_AULAS if objetivo in grupo), {objetivo})
    return normalizar(aula.get("nombre", "")) in equivalentes


def aforo_permitido(aula: dict) -> int:
    """Redondea hacia abajo y nunca supera la capacidad física del catálogo."""
    porcentaje = max(0, min(100, config.PORCENTAJE_AFORO_MAXIMO))
    return aula['aforo'] * porcentaje // 100


def actividad_desde_texto(texto: str) -> str:
    texto = normalizar(texto)
    if "zona franca" in texto:
        return "zona_franca"
    if re.search(r"\bser\b", texto):
        return "ser"
    if re.search(r"\bingles\b", texto):
        return "ingles"
    return "otra"


def prioridad(solicitud: dict) -> int:
    # Igual prioridad académica; una actividad declarada no cambia el tipo impuesto por el rol.
    return 0 if solicitud["tipo"] == "comercial" else 1


def hora_devolucion(fin_texto: str) -> str:
    """La devolución es informativa: no cambia el final del intervalo reservado."""
    fin = datetime.strptime(fin_texto, FORMATO)
    return (fin - timedelta(minutes=config.MINUTOS_DEVOLUCION_ANTICIPADA)).strftime(FORMATO)


def ordenar_candidatos(candidatos: list[dict], es_zona_franca: bool = False) -> list[dict]:
    """Recibe aulas ya filtradas por disponibilidad y aforo. No modifica la lista original."""
    return sorted(candidatos, key=lambda aula: (
        not es_azul(aula) if es_zona_franca else es_azul(aula),
        aula["aforo"], aula["id"],
    ))
