"""Carga y validación de los datos ficticios.

Valida fila por fila: las válidas se guardan, las inválidas van a registros_rechazados
y los conflictos (solapamientos, aforo excedido, cohortes vencidas) se marcan sin rechazar.
Es idempotente (cada carga reemplaza los datos) y no lanza excepciones sin controlar.
"""
import csv
import json
import logging
import unicodedata
from datetime import date
from pathlib import Path
from typing import Callable, Optional

from pydantic import ValidationError

from app import config, db
from app.modelos import Cohorte, Espacio, Sesion

logger = logging.getLogger(__name__)

ARCHIVO_ESPACIOS = "espacios.csv"
ARCHIVO_SESIONES = "sesiones.csv"
ARCHIVO_COHORTES = "cohortes.csv"

CAMPOS_OPCIONALES = {"nivel"}
ALIAS_VALORES = {"cancelado": "cancelada", "programado": "programada"}
CATALOGOS = {
    ARCHIVO_ESPACIOS: {
        "tipo": ("auditorio", "sala", "salon", "cubiculo"),
        "estado": ("activo", "mantenimiento", "inhabilitado"),
    },
    ARCHIVO_SESIONES: {
        "tipo": ("clase", "reunion", "alquiler"),
        "area": ("software", "ingles", "ser", "otra"),
        "estado": ("programada", "cancelada"),
    },
    ARCHIVO_COHORTES: {
        "jornada": ("manana", "mediodia", "tarde"),
        "ruta": ("java", "ia"),
    },
}
TRADUCCIONES = {
    "int_parsing": "debe ser un número entero",
    "int_type": "debe ser un número entero",
    "greater_than": "debe ser mayor que cero",
    "greater_than_equal": "no puede ser negativo",
    "bool_parsing": "debe ser 'si' o 'no'",
    "date_parsing": "fecha inválida; use el formato AAAA-MM-DD",
    "date_from_datetime_parsing": "fecha inválida; use el formato AAAA-MM-DD",
    "string_too_short": "no puede estar vacío",
    "missing": "campo obligatorio ausente",
}


class ErrorFila(Exception):
    """Motivo legible por el que una fila no es válida."""


class ErrorImportacion(Exception):
    """Problema con un archivo obligatorio. Detiene la importación antes de tocar la base."""

    def __init__(self, codigo: str, archivo: Optional[str], mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.archivo = archivo
        self.mensaje = mensaje

    def a_dict(self) -> dict:
        return {"codigo": self.codigo, "archivo": self.archivo, "mensaje": self.mensaje}


# Columnas que deben existir en cada CSV. Si falta una, la importación se detiene.
COLUMNAS_REQUERIDAS = {
    ARCHIVO_ESPACIOS: ("id", "nombre", "tipo", "aforo", "estado"),
    ARCHIVO_SESIONES: ("id", "espacio_id", "fecha", "hora_inicio", "hora_fin", "tipo", "area",
                       "es_zona_franca", "grupo", "cantidad_personas", "responsable", "estado"),
    ARCHIVO_COHORTES: ("codigo", "espacio_id", "jornada", "ruta", "cantidad_campers", "fecha_fin", "trainer"),
}


# --- Normalización de valores ---------------------------------------------------

def _sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def _valor_canonico(valor: str, opciones: tuple) -> str:
    """Devuelve la forma canónica solo si es inequívoca; si no, devuelve el valor original."""
    if valor in opciones:
        return valor
    clave = _sin_tildes(valor).lower()
    canonico = ALIAS_VALORES.get(clave, clave)
    return canonico if canonico in opciones else valor


def _si_no_a_booleano(valor: str):
    return {"si": True, "no": False}.get(_sin_tildes(valor).lower(), valor)


def _preparar_fila(datos: dict, catalogos: dict, correcciones: list) -> dict:
    """Normaliza lo que se puede corregir con certeza y registra cada corrección."""
    fila = dict(datos)
    for campo, opciones in catalogos.items():
        original = fila.get(campo, "")
        canonico = _valor_canonico(original, opciones)
        if canonico != original:
            fila[campo] = canonico
            correcciones.append((campo, original, canonico))
    if "es_zona_franca" in fila:
        fila["es_zona_franca"] = _si_no_a_booleano(fila["es_zona_franca"])
    if fila.get("nivel") == "":
        fila["nivel"] = None
    return fila


# --- Validación -----------------------------------------------------------------

def _motivo_validacion(error: ValidationError) -> str:
    """Traduce los errores de Pydantic a un texto legible en español."""
    partes = []
    for detalle in error.errors():
        campo = str(detalle["loc"][0]) if detalle["loc"] else "registro"
        tipo = detalle["type"]
        if tipo == "value_error":
            texto = detalle["msg"].removeprefix("Value error, ")
        elif tipo == "literal_error":
            valores = str(detalle["ctx"]["expected"]).replace(" or ", " o ")
            texto = f"valor no permitido; valores válidos: {valores}"
        else:
            texto = TRADUCCIONES.get(tipo, detalle["msg"])
        partes.append(f"{campo}: {texto}")
    return "; ".join(partes)


def _verificar_vacios(datos: dict) -> None:
    vacios = [c for c, v in datos.items() if c not in CAMPOS_OPCIONALES and not str(v).strip()]
    if "aforo" in vacios:
        raise ErrorFila("aforo vacío: el espacio no tiene capacidad definida y no puede programarse")
    if vacios:
        raise ErrorFila("campo(s) obligatorio(s) vacío(s): " + ", ".join(vacios))


def _a_minutos(hora: str) -> int:
    horas, minutos = hora.split(":")
    return int(horas) * 60 + int(minutos)


def _verificar_grilla(hora_inicio: str, hora_fin: str) -> None:
    """Revisa que el bloque caiga en la grilla operativa y en bloques completos."""
    for hora in (hora_inicio, hora_fin):
        if _a_minutos(hora) % config.MINUTOS_BLOQUE:
            raise ErrorFila(f"la hora {hora} no cae en bloques de {config.MINUTOS_BLOQUE} minutos")
    apertura = config.GRILLA_APERTURA_HORA * 60
    cierre = config.GRILLA_CIERRE_HORA * 60
    if _a_minutos(hora_inicio) < apertura or _a_minutos(hora_fin) > cierre:
        raise ErrorFila(
            f"el horario {hora_inicio}-{hora_fin} está fuera de la grilla "
            f"({config.GRILLA_APERTURA_HORA:02d}:00 a {config.GRILLA_CIERRE_HORA:02d}:00)"
        )


def _validar_espacio(datos: dict) -> Espacio:
    return Espacio(**datos)


def _validar_sesion(datos: dict, ids_espacios: set) -> Sesion:
    sesion = Sesion(**datos)
    if sesion.espacio_id not in ids_espacios:
        raise ErrorFila(f"el espacio '{sesion.espacio_id}' no existe en {ARCHIVO_ESPACIOS}")
    _verificar_grilla(sesion.hora_inicio, sesion.hora_fin)
    return sesion


def _validar_cohorte(datos: dict, ids_espacios: set) -> Cohorte:
    cohorte = Cohorte(**datos)
    if cohorte.espacio_id not in ids_espacios:
        raise ErrorFila(f"el espacio '{cohorte.espacio_id}' no existe en {ARCHIVO_ESPACIOS}")
    return cohorte


# --- Lectura y procesamiento de archivos ----------------------------------------

def _leer_filas(archivo: str) -> list:
    """Devuelve (número_de_línea, datos) de cada fila. Lanza ErrorImportacion si el archivo no sirve."""
    ruta = Path(config.RUTA_DATOS) / archivo
    if not ruta.exists():
        raise ErrorImportacion("archivo_ausente", archivo, f"no se encontró {archivo} en {config.RUTA_DATOS}")
    try:
        with open(ruta, newline="", encoding="utf-8-sig") as archivo_abierto:
            lector = csv.DictReader(archivo_abierto)
            columnas = [c.strip() for c in (lector.fieldnames or [])]
            faltantes = [c for c in COLUMNAS_REQUERIDAS[archivo] if c not in columnas]
            if faltantes:
                raise ErrorImportacion("estructura_incompatible", archivo,
                                       f"faltan columnas en {archivo}: {', '.join(faltantes)}")
            return [
                (numero + 2, {k.strip(): (v or "").strip() for k, v in fila.items() if k})
                for numero, fila in enumerate(lector)
            ]
    except (OSError, csv.Error, UnicodeDecodeError) as error:
        raise ErrorImportacion("archivo_no_legible", archivo, f"no se pudo leer {archivo}: {error}") from error


def _rechazo(archivo: str, fila: int, datos: dict, motivo: str) -> dict:
    return {"archivo": archivo, "fila": fila, "contenido": datos, "motivo": motivo}


def _procesar(archivo, filas, validar: Callable, clave: Callable, catalogos: dict):
    """Valida cada fila por separado. Devuelve (válidos, rechazados)."""
    validos, rechazos, vistos = [], [], {}
    for numero, datos in filas:
        if not any(datos.values()):
            continue
        correcciones = []
        try:
            preparada = _preparar_fila(datos, catalogos, correcciones)
            _verificar_vacios(preparada)
            modelo = validar(preparada)
            identificador = clave(modelo)
            if identificador in vistos:
                raise ErrorFila(f"id duplicado: '{identificador}' ya aparece en la fila {vistos[identificador]}")
        except ErrorFila as error:
            rechazos.append(_rechazo(archivo, numero, datos, str(error)))
            continue
        except ValidationError as error:
            rechazos.append(_rechazo(archivo, numero, datos, _motivo_validacion(error)))
            continue
        vistos[identificador] = numero
        validos.append({"fila": numero, "modelo": modelo, "clave": identificador, "correcciones": correcciones})
    return validos, rechazos


def _insertar_validos(con, tabla: str, archivo: str, validos: list) -> None:
    for item in validos:
        datos = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in item["modelo"].model_dump().items()}
        datos["archivo_origen"] = archivo
        datos["fila_origen"] = item["fila"]
        columnas = ", ".join(datos)
        marcas = ", ".join("?" for _ in datos)
        con.execute(f"INSERT INTO {tabla} ({columnas}) VALUES ({marcas})", tuple(datos.values()))


def _guardar_auxiliares(con, archivo: str, rechazos: list, validos: list) -> None:
    for rechazo in rechazos:
        con.execute(
            "INSERT INTO registros_rechazados (archivo, fila, contenido, motivo) VALUES (?, ?, ?, ?)",
            (archivo, rechazo["fila"], json.dumps(rechazo["contenido"], ensure_ascii=False), rechazo["motivo"]),
        )
    for item in validos:
        for campo, original, corregido in item["correcciones"]:
            con.execute(
                "INSERT INTO correcciones (archivo, fila, id_registro, campo, valor_original, valor_corregido) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (archivo, item["fila"], item["clave"], campo, original, corregido),
            )


def _validar_archivo(archivo: str, validar: Callable, clave: Callable) -> dict:
    """Lee y valida un archivo en memoria. No escribe nada en la base."""
    validos, rechazos = _procesar(archivo, _leer_filas(archivo), validar, clave, CATALOGOS[archivo])
    return {"validos": validos, "rechazos": rechazos}


# --- Conflictos -----------------------------------------------------------------

def _insertar_conflicto(con, tipo, archivo, referencia, relacionada, descripcion) -> None:
    con.execute(
        "INSERT INTO conflictos (tipo, archivo, referencia, referencia_relacionada, descripcion) "
        "VALUES (?, ?, ?, ?, ?)",
        (tipo, archivo, referencia, relacionada, descripcion),
    )


def _detectar_solapamientos(con) -> int:
    filas = con.execute(
        "SELECT id, espacio_id, fecha, hora_inicio, hora_fin, tipo, es_zona_franca "
        "FROM sesiones WHERE estado = 'programada' ORDER BY espacio_id, fecha, hora_inicio"
    ).fetchall()
    grupos = {}
    for fila in filas:
        grupos.setdefault((fila["espacio_id"], fila["fecha"]), []).append(fila)
    total = 0
    for (espacio, fecha), sesiones in grupos.items():
        for i, a in enumerate(sesiones):
            for b in sesiones[i + 1:]:
                if not (a["hora_inicio"] < b["hora_fin"] and b["hora_inicio"] < a["hora_fin"]):
                    continue
                descripcion = (f"Se solapan en {espacio} el {fecha}: "
                               f"{a['hora_inicio']}-{a['hora_fin']} y {b['hora_inicio']}-{b['hora_fin']}")
                _insertar_conflicto(con, "solapamiento", ARCHIVO_SESIONES, a["id"], b["id"], descripcion)
                total += 1
                total += _detectar_alquiler_sobre_zona_franca(con, a, b)
    return total


def _detectar_alquiler_sobre_zona_franca(con, a, b) -> int:
    for alquiler, clase in ((a, b), (b, a)):
        if alquiler["tipo"] == "alquiler" and clase["tipo"] == "clase" and clase["es_zona_franca"]:
            descripcion = f"El alquiler {alquiler['id']} se cruza con la clase de Zona Franca {clase['id']}"
            _insertar_conflicto(con, "alquiler_sobre_zona_franca", ARCHIVO_SESIONES,
                                alquiler["id"], clase["id"], descripcion)
            return 1
    return 0


def _detectar_aforo_excedido(con) -> int:
    filas = con.execute(
        "SELECT s.id, s.cantidad_personas, e.id AS espacio, e.aforo FROM sesiones s "
        "JOIN espacios e ON e.id = s.espacio_id "
        "WHERE s.estado = 'programada' AND s.cantidad_personas > e.aforo"
    ).fetchall()
    for fila in filas:
        descripcion = f"{fila['cantidad_personas']} personas superan el aforo de {fila['espacio']} ({fila['aforo']})"
        _insertar_conflicto(con, "aforo_excedido", ARCHIVO_SESIONES, fila["id"], fila["espacio"], descripcion)
    return len(filas)


def _detectar_cohortes_vencidas(con) -> int:
    hoy = date.today()
    filas = con.execute("SELECT codigo, espacio_id, fecha_fin FROM cohortes").fetchall()
    vencidas = [f for f in filas if date.fromisoformat(f["fecha_fin"]) < hoy]
    for fila in vencidas:
        descripcion = f"La cohorte {fila['codigo']} venció el {fila['fecha_fin']}"
        _insertar_conflicto(con, "cohorte_vencida", ARCHIVO_COHORTES, fila["codigo"], fila["espacio_id"], descripcion)
    return len(vencidas)


def _detectar_conflictos(con) -> int:
    return (_detectar_solapamientos(con)
            + _detectar_aforo_excedido(con)
            + _detectar_cohortes_vencidas(con))


# --- Punto de entrada -----------------------------------------------------------

TABLAS_POR_ARCHIVO = ((ARCHIVO_ESPACIOS, "espacios"), (ARCHIVO_SESIONES, "sesiones"), (ARCHIVO_COHORTES, "cohortes"))


def _validar_todo() -> dict:
    """Valida los tres archivos antes de tocar la base. Un archivo obligatorio roto detiene todo."""
    espacios = _validar_archivo(ARCHIVO_ESPACIOS, _validar_espacio, lambda m: m.id)
    ids_espacios = {item["modelo"].id for item in espacios["validos"]}
    return {
        ARCHIVO_ESPACIOS: espacios,
        ARCHIVO_SESIONES: _validar_archivo(ARCHIVO_SESIONES,
                                           lambda d: _validar_sesion(d, ids_espacios), lambda m: m.id),
        ARCHIVO_COHORTES: _validar_archivo(ARCHIVO_COHORTES,
                                           lambda d: _validar_cohorte(d, ids_espacios), lambda m: m.codigo),
    }


def _escribir(con, validados: dict) -> int:
    """Reemplaza los datos dentro de la transacción recibida. Devuelve el número de conflictos."""
    db.vaciar_tablas(con)
    for archivo, tabla in TABLAS_POR_ARCHIVO:
        _insertar_validos(con, tabla, archivo, validados[archivo]["validos"])
        _guardar_auxiliares(con, archivo, validados[archivo]["rechazos"], validados[archivo]["validos"])
    return _detectar_conflictos(con)


def _resumen(validados: dict, conflictos: int) -> dict:
    return {
        "ok": True,
        "error": None,
        "cargados": {a: len(v["validos"]) for a, v in validados.items()},
        "rechazados": {a: len(v["rechazos"]) for a, v in validados.items()},
        "corregidos": {a: sum(len(i["correcciones"]) for i in v["validos"]) for a, v in validados.items()},
        "conflictos": conflictos,
    }


def cargar_datos() -> dict:
    """Importa los CSV reemplazando la carga anterior, solo si todos los archivos obligatorios sirven.

    Si algo falla, la base queda exactamente como estaba. Nunca lanza excepciones.
    """
    try:
        validados = _validar_todo()
    except ErrorImportacion as error:
        return {"ok": False, "error": error.a_dict()}
    try:
        with db.transaccion() as con:
            conflictos = _escribir(con, validados)
    except Exception as error:  # la transacción ya revirtió el reemplazo
        logger.exception("Error al escribir la importación")
        return {"ok": False, "error": ErrorImportacion("error_escritura", None,
                                                    f"No se pudo guardar la importación: {error}").a_dict()}
    return _resumen(validados, conflictos)


def consultar_calidad() -> dict:
    """Resumen de calidad de datos leído desde la base."""
    archivos = [ARCHIVO_ESPACIOS, ARCHIVO_SESIONES, ARCHIVO_COHORTES]

    def contar(sql: str) -> dict:
        return {f["archivo"]: f["total"] for f in db.consultar(sql)}

    cargados = contar(" UNION ALL ".join(
        f"SELECT archivo_origen AS archivo, COUNT(*) AS total FROM {t} GROUP BY archivo_origen"
        for t in ("espacios", "sesiones", "cohortes")))
    rechazados = contar("SELECT archivo, COUNT(*) AS total FROM registros_rechazados GROUP BY archivo")
    corregidos = contar("SELECT archivo, COUNT(*) AS total FROM correcciones GROUP BY archivo")
    conflictos = contar("SELECT archivo, COUNT(*) AS total FROM conflictos GROUP BY archivo")
    resumen = [{
        "archivo": a,
        "cargados": cargados.get(a, 0),
        "corregidos": corregidos.get(a, 0),
        "rechazados": rechazados.get(a, 0),
        "conflictos": conflictos.get(a, 0),
    } for a in archivos]
    rechazos = db.consultar("SELECT archivo, fila, contenido, motivo FROM registros_rechazados ORDER BY archivo, fila")
    for rechazo in rechazos:
        rechazo["contenido"] = json.loads(rechazo["contenido"])
    return {
        "resumen": resumen,
        "errores_carga": db.consultar("SELECT archivo, mensaje FROM errores_carga ORDER BY id"),
        "rechazados": rechazos,
        "correcciones": db.consultar(
            "SELECT archivo, fila, id_registro, campo, valor_original, valor_corregido "
            "FROM correcciones ORDER BY archivo, fila"),
        "conflictos": db.consultar(
            "SELECT tipo, archivo, referencia, referencia_relacionada, descripcion FROM conflictos ORDER BY archivo, id"),
    }
