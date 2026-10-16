"""Conexión a SQLite y creación de tablas."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app import config

ESQUEMA = """
CREATE TABLE IF NOT EXISTS espacios (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    tipo TEXT NOT NULL,
    aforo INTEGER NOT NULL CHECK (aforo > 0),
    estado TEXT NOT NULL,
    archivo_origen TEXT NOT NULL,
    fila_origen INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sesiones (
    id TEXT PRIMARY KEY,
    espacio_id TEXT NOT NULL REFERENCES espacios(id),
    fecha TEXT NOT NULL,
    hora_inicio TEXT NOT NULL,
    hora_fin TEXT NOT NULL,
    tipo TEXT NOT NULL,
    area TEXT NOT NULL,
    es_zona_franca INTEGER NOT NULL,
    grupo TEXT NOT NULL,
    nivel TEXT,
    cantidad_personas INTEGER NOT NULL,
    responsable TEXT NOT NULL,
    estado TEXT NOT NULL,
    archivo_origen TEXT NOT NULL,
    fila_origen INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS cohortes (
    codigo TEXT PRIMARY KEY,
    espacio_id TEXT NOT NULL REFERENCES espacios(id),
    jornada TEXT NOT NULL,
    ruta TEXT NOT NULL,
    cantidad_campers INTEGER NOT NULL,
    fecha_fin TEXT NOT NULL,
    trainer TEXT NOT NULL,
    archivo_origen TEXT NOT NULL,
    fila_origen INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS registros_rechazados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    archivo TEXT NOT NULL,
    fila INTEGER NOT NULL,
    contenido TEXT NOT NULL,
    motivo TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS correcciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    archivo TEXT NOT NULL,
    fila INTEGER NOT NULL,
    id_registro TEXT NOT NULL,
    campo TEXT NOT NULL,
    valor_original TEXT,
    valor_corregido TEXT
);
CREATE TABLE IF NOT EXISTS conflictos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,
    archivo TEXT NOT NULL,
    referencia TEXT NOT NULL,
    referencia_relacionada TEXT,
    descripcion TEXT NOT NULL
);
-- espacio_id no tiene llave foránea: la recarga reemplaza la tabla espacios y no debe borrar reservas.
CREATE TABLE IF NOT EXISTS solicitudes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    espacio_id TEXT NOT NULL,
    inicio TEXT NOT NULL,
    fin TEXT NOT NULL,
    personas INTEGER NOT NULL CHECK (personas > 0),
    descripcion TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('academica', 'comercial')),
    solicitante_id TEXT NOT NULL,
    rol_solicitante TEXT NOT NULL,
    estado TEXT NOT NULL CHECK (estado IN ('pendiente', 'aprobada')),
    requiere_pago INTEGER NOT NULL,
    estado_pago TEXT,
    creada_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    decidida_por TEXT,
    decidida_en TEXT,
    CHECK (fin > inicio)
);
-- Borrador del chat: pertenece a un usuario y a una conversación. Nunca se comparte.
CREATE TABLE IF NOT EXISTS borradores_chat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id TEXT NOT NULL,
    conversacion_id TEXT NOT NULL,
    estado TEXT NOT NULL CHECK (estado IN ('en_curso', 'propuesta', 'creada', 'cancelado')),
    datos TEXT NOT NULL,
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (usuario_id, conversacion_id)
);
CREATE TABLE IF NOT EXISTS importaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    exito INTEGER NOT NULL,
    codigo TEXT,
    archivo TEXT,
    mensaje TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reubicaciones (
    id TEXT PRIMARY KEY,
    solicitud_id INTEGER NOT NULL,
    datos TEXT NOT NULL,
    estado TEXT NOT NULL CHECK (estado IN ('propuesta', 'aplicada')),
    propuesta_por TEXT NOT NULL,
    autorizada_por TEXT,
    autorizada_en TEXT
);
"""

# Orden de borrado: primero las tablas hijas, para respetar las llaves foráneas.
# `importaciones` no entra: el historial de intentos sobrevive a cada reemplazo.
TABLAS_CARGA = ("conflictos", "correcciones", "registros_rechazados", "cohortes", "sesiones", "espacios")


def conectar() -> sqlite3.Connection:
    """Abre una conexión con filas accesibles por nombre de columna y llaves foráneas activas."""
    Path(config.RUTA_BASE_DATOS).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.RUTA_BASE_DATOS)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def inicializar_base() -> None:
    """Crea las tablas si no existen."""
    con = conectar()
    try:
        con.executescript(ESQUEMA)
        con.execute("BEGIN IMMEDIATE")
        ampliaciones = {
            "espacios": {"elementos": "TEXT"},
            "sesiones": {"elementos_requeridos": "TEXT NOT NULL DEFAULT '[]'"},
            "solicitudes": {"actividad": "TEXT NOT NULL DEFAULT 'otra'",
                            "elementos_requeridos": "TEXT NOT NULL DEFAULT '[]'"},
        }
        for tabla, columnas in ampliaciones.items():
            existentes = {fila[1] for fila in con.execute(f"PRAGMA table_info({tabla})")}
            for campo, tipo in columnas.items():
                if campo not in existentes:
                    con.execute(f"ALTER TABLE {tabla} ADD COLUMN {campo} {tipo}")
        con.commit()
    finally:
        con.close()


@contextmanager
def transaccion() -> Iterator[sqlite3.Connection]:
    """Entrega una conexión dentro de una transacción: confirma al final o revierte si falla.

    BEGIN IMMEDIATE toma el bloqueo de escritura desde el inicio: dos importaciones
    simultáneas no pueden intercalarse.
    """
    con = conectar()
    try:
        con.execute("BEGIN IMMEDIATE")
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def consultar(sql: str, parametros: tuple = ()) -> list[dict]:
    """Ejecuta una consulta de lectura y devuelve las filas como diccionarios."""
    con = conectar()
    try:
        return [dict(fila) for fila in con.execute(sql, parametros).fetchall()]
    finally:
        con.close()


def vaciar_tablas(con: sqlite3.Connection) -> None:
    """Borra los datos cargados. Se usa al inicio de cada recarga para que no se dupliquen."""
    for tabla in TABLAS_CARGA:
        con.execute(f"DELETE FROM {tabla}")
