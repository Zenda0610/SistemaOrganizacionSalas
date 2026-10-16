"""Arranque de FastAPI, rutas de la API y servicio de la interfaz estática."""
import logging
import json
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as ErrorHTTP

from app import carga_datos, db, ia, reubicaciones, operaciones
from app.identidad import ErrorAcceso, identidad_actual
from app.modelos import TIPOS_SESION, Cohorte
from app import chat as chat_solicitudes, solicitudes
from app.permisos import requerir_permiso
from app.identidad import Identidad
from app.solicitudes import ErrorSolicitud, NuevaSolicitud

logger = logging.getLogger(__name__)
RAIZ_STATIC = Path(__file__).resolve().parent.parent / "static"
CAMPOS_COHORTE = ("codigo", "espacio_id", "jornada", "ruta", "cantidad_campers", "fecha_fin", "trainer")


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    # El arranque solo crea las tablas que falten. La importación de CSV es explícita:
    # POST /api/datos/recargar o `python -m app.carga_datos`.
    db.inicializar_base()
    yield


app = FastAPI(title="Sistema Central de Gestión Operativa de Campuslands", version="0.1.0", lifespan=ciclo_de_vida)


# --- Errores siempre en JSON con mensaje en español ----------------------------

@app.exception_handler(ErrorHTTP)
async def manejar_error_http(_request, error: ErrorHTTP):
    mensaje = "La ruta solicitada no existe." if error.status_code == 404 else str(error.detail)
    return JSONResponse(status_code=error.status_code, content={"mensaje": mensaje})


@app.exception_handler(RequestValidationError)
async def manejar_error_validacion(_request, _error: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"mensaje": "Parámetros no válidos. Revise el formato de la fecha (AAAA-MM-DD) y los valores del filtro."},
    )


@app.exception_handler(Exception)
async def manejar_error_general(_request, error: Exception):
    logger.exception("Error no controlado: %s", error)
    return JSONResponse(status_code=500, content={"mensaje": "Error interno del servidor.", "codigo": "error_interno_servidor"})


@app.exception_handler(ErrorAcceso)
async def manejar_error_acceso(_request, error: ErrorAcceso):
    return JSONResponse(status_code=error.estado, content={"mensaje": error.mensaje, "codigo": error.codigo})


@app.exception_handler(chat_solicitudes.ErrorChat)
async def manejar_error_chat(_request, error: chat_solicitudes.ErrorChat):
    return JSONResponse(status_code=error.estado, content={"mensaje": error.mensaje, "codigo": error.codigo})


@app.exception_handler(ErrorSolicitud)
async def manejar_error_solicitud(_request, error: ErrorSolicitud):
    return JSONResponse(status_code=error.estado, content={"mensaje": error.mensaje, "codigo": error.codigo})


# --- Sesión ----------------------------------------------------------------------

@app.get("/api/sesion")
def sesion_actual() -> dict:
    identidad = identidad_actual()
    return {"usuario_id": identidad.usuario_id, "rol": identidad.rol, "origen": identidad.origen}


# --- API de lectura ------------------------------------------------------------

@app.get("/api/espacios")
def listar_espacios() -> list[dict]:
    filas = db.consultar(
        "SELECT id, nombre, tipo, aforo, estado, elementos, archivo_origen, fila_origen, "
        "EXISTS(SELECT 1 FROM bloqueos b WHERE b.recurso_tipo='aula' AND b.recurso_id=espacios.id) AS bloqueada "
        "FROM espacios ORDER BY id"
    )
    for fila in filas:
        fila["elementos"] = json.loads(fila["elementos"]) if fila["elementos"] is not None else None
        fila["bloqueada"] = bool(fila["bloqueada"])
        if fila["bloqueada"]:
            fila["estado"] = "inhabilitado"
    return filas


@app.get("/api/sesiones")
def listar_sesiones(
    fecha: Optional[date] = None,
    espacio_id: Optional[str] = None,
    tipo: Optional[str] = None,
) -> list[dict]:
    if tipo is not None and tipo not in TIPOS_SESION:
        raise HTTPException(status_code=400, detail=f"El tipo '{tipo}' no es válido. Use: {', '.join(TIPOS_SESION)}.")
    condiciones, parametros = [], []
    if fecha:
        condiciones.append("fecha = ?")
        parametros.append(fecha.isoformat())
    if espacio_id:
        condiciones.append("espacio_id = ?")
        parametros.append(espacio_id)
    if tipo:
        condiciones.append("tipo = ?")
        parametros.append(tipo)
    donde = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    filas = db.consultar(
        f"SELECT * FROM sesiones {donde} ORDER BY fecha, hora_inicio, espacio_id", tuple(parametros)
    )
    for fila in filas:
        fila["es_zona_franca"] = bool(fila["es_zona_franca"])
    return filas


@app.get("/api/cohortes")
def listar_cohortes() -> list[dict]:
    resultado = []
    for fila in db.consultar("SELECT * FROM cohortes ORDER BY fecha_fin, codigo"):
        cohorte = Cohorte(**{campo: fila[campo] for campo in CAMPOS_COHORTE})
        resultado.append({**cohorte.model_dump(mode="json"), "dias_restantes": cohorte.dias_restantes()})
    return resultado


class MensajeChat(BaseModel):
    # extra="forbid": el cliente no puede enviar identidad ni rol.
    model_config = ConfigDict(extra="forbid")

    mensaje: str = Field(max_length=2000)
    conversacion_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")


@app.post("/api/chat")
def chat(cuerpo: MensajeChat, identidad: Identidad = Depends(identidad_actual)) -> dict:
    return chat_solicitudes.procesar(identidad, cuerpo.mensaje, cuerpo.conversacion_id)


# --- Solicitudes y disponibilidad ----------------------------------------------

@app.get("/api/disponibilidad")
def consultar_disponibilidad(
    inicio: datetime, fin: datetime, personas: Optional[int] = Query(default=None, ge=1)
) -> list[dict]:
    solicitudes.comprobar_intervalo(inicio, fin)
    return solicitudes.espacios_disponibles(inicio, fin, personas)


@app.get("/api/reservas")
def listar_reservas(fecha: Optional[date] = None) -> list[dict]:
    return solicitudes.listar_reservas(fecha)


@app.get("/api/solicitudes")
def listar_solicitudes(identidad: Identidad = Depends(identidad_actual)) -> list[dict]:
    return solicitudes.listar_solicitudes(identidad)


@app.post("/api/solicitudes", status_code=201)
def crear_solicitud(datos: NuevaSolicitud, identidad: Identidad = Depends(identidad_actual)) -> dict:
    return solicitudes.crear_solicitud(identidad, datos)


@app.post("/api/solicitudes/{solicitud_id}/aprobar", dependencies=[requerir_permiso("autorizar_solicitud")])
def aprobar_solicitud(solicitud_id: int, identidad: Identidad = Depends(identidad_actual)) -> dict:
    return solicitudes.aprobar_solicitud(solicitud_id, identidad)


@app.post("/api/solicitudes/{solicitud_id}/reubicacion/proponer", dependencies=[requerir_permiso("autorizar_solicitud")])
def proponer_reubicacion(solicitud_id: int, identidad: Identidad = Depends(identidad_actual)) -> dict:
    return reubicaciones.proponer(solicitud_id, identidad)


@app.get("/api/reubicaciones/{identificador}", dependencies=[requerir_permiso("autorizar_solicitud")])
def consultar_reubicacion(identificador: str, identidad: Identidad = Depends(identidad_actual)) -> dict:
    return reubicaciones.consultar(identificador, identidad)


@app.post("/api/reubicaciones/{identificador}/confirmar", dependencies=[requerir_permiso("autorizar_solicitud")])
def confirmar_reubicacion(identificador: str, identidad: Identidad = Depends(identidad_actual)) -> dict:
    return reubicaciones.confirmar(identificador, identidad)


@app.get("/api/calidad-datos")
def calidad_datos() -> dict:
    return carga_datos.consultar_calidad()


CODIGOS_HTTP_IMPORTACION = {
    "archivo_ausente": 422,
    "archivo_no_legible": 422,
    "estructura_incompatible": 422,
    "error_escritura": 500,
    "error_interno": 500,
    "catalogo_vacio": 422,
    "reserva_incompatible": 409,
}


@app.post("/api/datos/recargar", dependencies=[requerir_permiso("recargar_datos")])
def recargar_datos():
    resultado = carga_datos.cargar_datos()
    if resultado["ok"]:
        return resultado
    error = resultado["error"]
    return JSONResponse(
        status_code=CODIGOS_HTTP_IMPORTACION[error["codigo"]],
        content={"mensaje": error["mensaje"], "codigo": error["codigo"], "archivo": error["archivo"]},
    )


@app.get("/api/ia/salud")
def salud_ia() -> dict:
    return ia.verificar_salud()


@app.get("/api/equipos")
def equipos(_identidad: Identidad = Depends(identidad_actual)):
    return operaciones.listar_equipos()


@app.post("/api/equipos", status_code=201)
def nuevo_equipo(datos: operaciones.EquipoNuevo, identidad: Identidad = Depends(identidad_actual)):
    return operaciones.crear_equipo(datos, identidad)


@app.get("/api/prestamos")
def prestamos(identidad: Identidad = Depends(identidad_actual)):
    return operaciones.listar_prestamos(identidad)


@app.post("/api/prestamos", status_code=201)
def prestar(datos: operaciones.PrestamoNuevo, identidad: Identidad = Depends(identidad_actual)):
    return operaciones.prestar(datos, identidad)


@app.post("/api/prestamos/{identificador}/devolver")
def devolver(identificador: int, identidad: Identidad = Depends(identidad_actual)):
    return operaciones.devolver(identificador, identidad)


@app.get("/api/incidencias")
def incidencias(identidad: Identidad = Depends(identidad_actual)):
    return operaciones.listar_incidencias(identidad)


@app.post("/api/incidencias", status_code=201)
def reportar(datos: operaciones.Reporte, identidad: Identidad = Depends(identidad_actual)):
    return operaciones.reportar(datos, identidad)


@app.post("/api/incidencias/{identificador}/revisar")
def revisar(identificador: int, datos: operaciones.Revision, identidad: Identidad = Depends(identidad_actual)):
    return operaciones.revisar(identificador, datos, identidad)


# La interfaz se sirve al final para que no tape las rutas /api.
app.mount("/", StaticFiles(directory=RAIZ_STATIC, html=True), name="interfaz")
