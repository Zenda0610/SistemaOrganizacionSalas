"""Identidad de quien hace la petición.

Etapa provisional: la identidad sale solo de la configuración del servidor
(USUARIO_DESARROLLO y ROL_DESARROLLO). NO es autenticación. Cuando exista el
esquema oficial de usuarios, solo debe cambiar identidad_actual().
"""
from dataclasses import dataclass

from app import config

ROLES = ("profesor", "administrativo", "estudiante", "empresa", "coordinadora")
ORIGEN_DESARROLLO = "desarrollo"


class ErrorAcceso(Exception):
    """Error de identidad o permiso. El mensaje es general y nunca incluye detalles internos."""

    def __init__(self, estado: int, codigo: str, mensaje: str):
        super().__init__(mensaje)
        self.estado = estado
        self.codigo = codigo
        self.mensaje = mensaje


@dataclass(frozen=True)
class Identidad:
    usuario_id: str
    rol: str
    origen: str


def identidad_actual() -> Identidad:
    """Devuelve la identidad configurada en el servidor. Nunca lee la petición."""
    usuario = config.USUARIO_DESARROLLO
    rol = config.ROL_DESARROLLO
    if not usuario or rol not in ROLES:
        raise ErrorAcceso(401, "sin_identidad", "No hay una identidad de desarrollo válida configurada en el servidor.")
    return Identidad(usuario_id=usuario, rol=rol, origen=ORIGEN_DESARROLLO)
