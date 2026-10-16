"""Modelos Pydantic: espacio, sesión, cohorte, recurso, incidencia y registro rechazado."""
import re
import json
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

PATRON_HORA = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
TIPOS_SESION = ("clase", "reunion", "alquiler")


def lista_elementos(valor):
    lista = json.loads(valor) if isinstance(valor, str) else valor
    if lista is not None and (not isinstance(lista, list) or len(lista) > 30 or
                              any(not isinstance(e, str) or not e.strip() or len(e) > 100 for e in lista)):
        raise ValueError("Los elementos deben ser una lista de nombres no vacíos (máximo 30).")
    return lista


class Espacio(BaseModel):
    """Aula, salón, sala o cubículo. El aforo debe ser mayor que cero."""

    id: str = Field(min_length=1)
    nombre: str = Field(min_length=1)
    tipo: Literal["auditorio", "sala", "salon", "cubiculo"]
    aforo: int = Field(gt=0)
    estado: Literal["activo", "mantenimiento", "inhabilitado"]
    elementos: list[str] | None = None  # None: inventario no suministrado, no equivale a vacío verificado

    @field_validator("elementos", mode="before")
    @classmethod
    def leer_elementos(cls, valor):
        return lista_elementos(valor)


class Sesion(BaseModel):
    """Un bloque de la grilla. Los alquileres usan tipo 'alquiler' en la misma tabla."""

    id: str = Field(min_length=1)
    espacio_id: str = Field(min_length=1)
    fecha: date
    hora_inicio: str
    hora_fin: str
    tipo: Literal["clase", "reunion", "alquiler"]
    area: Literal["software", "ingles", "ser", "otra"]
    es_zona_franca: bool
    grupo: str = Field(min_length=1)
    nivel: Optional[str] = None
    cantidad_personas: int = Field(ge=0)
    responsable: str = Field(min_length=1)
    estado: Literal["programada", "cancelada"]
    elementos_requeridos: list[str] = Field(default_factory=list)

    @field_validator("elementos_requeridos", mode="before")
    @classmethod
    def leer_elementos(cls, valor):
        return lista_elementos(valor)

    @field_validator("hora_inicio", "hora_fin")
    @classmethod
    def validar_formato_hora(cls, valor: str) -> str:
        if not PATRON_HORA.match(valor):
            raise ValueError(
                f"la hora '{valor}' no está en formato 24 h HH:MM; "
                "sin AM/PM no se puede determinar con certeza"
            )
        return valor

    @model_validator(mode="after")
    def validar_orden_horas(self) -> "Sesion":
        if self.hora_fin <= self.hora_inicio:
            raise ValueError("la hora fin debe ser posterior a la hora inicio")
        return self


class Cohorte(BaseModel):
    """Grupo de campers de una jornada en un espacio."""

    codigo: str = Field(min_length=1)
    espacio_id: str = Field(min_length=1)
    jornada: Literal["manana", "mediodia", "tarde"]
    ruta: Literal["java", "ia"]
    cantidad_campers: int = Field(ge=0)
    fecha_fin: date
    trainer: str = Field(min_length=1)

    def dias_restantes(self, hoy: Optional[date] = None) -> int:
        """Días entre hoy y la fecha de fin. Es negativo si la cohorte ya venció."""
        return (self.fecha_fin - (hoy or date.today())).days


class Recurso(BaseModel):
    """Recurso tecnológico. Modelo reservado para la fase 2; aún no se carga."""

    id: str = Field(min_length=1)
    nombre: str = Field(min_length=1)
    tipo: str = Field(min_length=1)
    estado: Literal["disponible", "prestado", "mantenimiento", "baja"]


class Incidencia(BaseModel):
    """Incidencia operativa. Modelo reservado para la fase 2; aún no se carga."""

    id: str = Field(min_length=1)
    espacio_id: Optional[str] = None
    descripcion: str = Field(min_length=1)
    estado: Literal["abierta", "en_proceso", "cerrada"]
    fecha: date


class RegistroRechazado(BaseModel):
    """Fila que no pasó la validación, con su origen y el motivo legible."""

    archivo: str
    fila: int
    contenido: dict[str, str]
    motivo: str
