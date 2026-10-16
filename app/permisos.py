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
    "gestionar_recursos": frozenset({"coordinadora"}),
    "prestar_equipo": frozenset({"profesor", "administrativo", "coordinadora"}),
}


def tiene_permiso(rol: str, permiso: str) -> bool:
    """Un permiso desconocido se niega a todos los roles."""
    return rol in PERMISOS.get(permiso, frozenset())


def tipo_solicitud_para(rol: str) -> str:
    """Tipo de solicitud según el rol, decidido en el servidor. Sin permiso de ninguno: 403."""
    if tiene_permiso(rol, "solicitar_aula_academica"):
        return "academica"
    if tiene_permiso(rol, "solicitar_alquiler_comercial"):
        return "comercial"
    raise ErrorAcceso(403, "sin_permiso", "No tiene permiso para solicitar aulas.")


def requerir_permiso(permiso: str):
    """Dependencia de FastAPI: 401 sin identidad, 403 sin permiso."""

    def verificar() -> Identidad:
        identidad = identidad_actual()
        if not tiene_permiso(identidad.rol, permiso):
            raise ErrorAcceso(403, "sin_permiso", "No tiene permiso para realizar esta acción.")
        return identidad

    return Depends(verificar)
