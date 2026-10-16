"""Permisos por rol. La matriz vive en código; ningún dato de la petición puede cambiarla."""
from fastapi import Depends

from app.identidad import ErrorAcceso, Identidad, identidad_actual

PERMISOS = {
    # Profesores y administrativos "autorizados". Esa condición depende del esquema oficial
    # de usuarios, que aún no existe: por ahora se aproxima solo por rol.
    "solicitar_aula_academica": frozenset({"profesor", "administrativo"}),
    # Solicitudes comerciales sujetas a pago. No hay tarifas ni pasarela en esta etapa.
    "solicitar_alquiler_comercial": frozenset({"estudiante", "empresa"}),
    "autorizar_solicitud": frozenset({"coordinadora"}),
    "recargar_datos": frozenset({"coordinadora"}),
}


def tiene_permiso(rol: str, permiso: str) -> bool:
    """Un permiso desconocido se niega a todos los roles."""
    return rol in PERMISOS.get(permiso, frozenset())


def requerir_permiso(permiso: str):
    """Dependencia de FastAPI: 401 sin identidad, 403 sin permiso."""

    def verificar() -> Identidad:
        identidad = identidad_actual()
        if not tiene_permiso(identidad.rol, permiso):
            raise ErrorAcceso(403, "sin_permiso", "No tiene permiso para realizar esta acción.")
        return identidad

    return Depends(verificar)
