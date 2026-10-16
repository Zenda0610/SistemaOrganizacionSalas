"""Arranque de FastAPI, rutas de la API y servicio de la interfaz estática."""
import logging
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as ErrorHTTP

from app import carga_datos, db, ia
from app.modelos import TIPOS_SESION, Cohorte

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
    return JSONResponse(status_code=500, content={"mensaje": "Error interno del servidor. Revise el registro de la aplicación."})


# --- API de lectura ------------------------------------------------------------

@app.get("/api/espacios")
def listar_espacios() -> list[dict]:
    return db.consultar(
        "SELECT id, nombre, tipo, aforo, estado, archivo_origen, fila_origen FROM espacios ORDER BY id"
    )


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


@app.get("/api/calidad-datos")
def calidad_datos() -> dict:
    return carga_datos.consultar_calidad()


CODIGOS_HTTP_IMPORTACION = {
    "archivo_ausente": 422,
    "archivo_no_legible": 422,
    "estructura_incompatible": 422,
    "error_escritura": 500,
    "error_interno": 500,
}


@app.post("/api/datos/recargar")
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


# La interfaz se sirve al final para que no tape las rutas /api.
app.mount("/", StaticFiles(directory=RAIZ_STATIC, html=True), name="interfaz")
