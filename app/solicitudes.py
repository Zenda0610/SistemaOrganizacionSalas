"""Solicitudes de aulas: disponibilidad, creación pendiente y aprobación validada en transacción.

Reglas:
- Los intervalos son semiabiertos [inicio, fin): 08:00–09:00 y 09:00–10:00 son compatibles.
- El servicio opera 24/7 y un intervalo puede cruzar medianoche. No hay horario de apertura.
- Una solicitud se crea en estado pendiente. Solo la coordinadora la aprueba, y la aprobación
  vuelve a validar estado del espacio, aforo y solapamientos dentro de una transacción.
- Una solicitud comercial queda con estado_pago "pendiente". El sistema no verifica pagos.
"""
from datetime import date, datetime, timedelta
from typing import Optional
from typing import Literal
import json

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

from app import config, db, reglas
from app.identidad import Identidad
from app.permisos import tipo_solicitud_para

FORMATO = "%Y-%m-%d %H:%M"
CAMPOS_SOLICITUD = (
    "id, espacio_id, inicio, fin, personas, descripcion, tipo, solicitante_id, rol_solicitante, "
    "estado, requiere_pago, estado_pago, creada_en, decidida_por, decidida_en, actividad, elementos_requeridos"
)


class ErrorSolicitud(Exception):
    """Error de negocio. El mensaje es general y seguro para la API."""

    def __init__(self, estado: int, codigo: str, mensaje: str):
        super().__init__(mensaje)
        self.estado = estado
        self.codigo = codigo
        self.mensaje = mensaje


def validar_intervalo(inicio: datetime, fin: datetime) -> None:
    """Lanza ValueError con un mensaje seguro si el intervalo no es válido."""
    paso = max(config.MINUTOS_BLOQUE, 1)
    for momento in (inicio, fin):
        if momento.tzinfo is not None:
            raise ValueError("Las fechas deben indicarse sin zona horaria (hora local del centro).")
        if momento.second or momento.microsecond or momento.minute % paso:
            raise ValueError(f"Las horas deben caer en bloques de {paso} minutos.")
    if fin <= inicio:
        raise ValueError("La hora final debe ser posterior a la inicial.")


def comprobar_intervalo(inicio: datetime, fin: datetime) -> None:
    try:
        validar_intervalo(inicio, fin)
    except ValueError as error:
        raise ErrorSolicitud(422, "intervalo_no_valido", str(error))


class NuevaSolicitud(BaseModel):
    # extra="forbid": un cuerpo con rol, tipo o usuario se rechaza. Esos datos salen del servidor.
    model_config = ConfigDict(extra="forbid")

    espacio_id: str = Field(min_length=1, max_length=20)
    inicio: datetime
    fin: datetime
    personas: int = Field(ge=1, le=100000)
    descripcion: str = Field(min_length=3, max_length=300)
    actividad: Literal["zona_franca", "ser", "ingles", "otra"] = "otra"
    elementos_requeridos: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("elementos_requeridos")
    @classmethod
    def validar_elementos(cls, lista):
        if any(not e.strip() or len(e) > 100 for e in lista):
            raise ValueError("Indique nombres de elementos no vacíos, de hasta 100 caracteres.")
        return lista

    @model_validator(mode="after")
    def _validar_intervalo(self):
        validar_intervalo(self.inicio, self.fin)
        return self


def _texto(momento: datetime) -> str:
    return momento.strftime(FORMATO)


def buscar_conflictos(con, espacio_id: str, inicio: str, fin: str, excluir_id: Optional[int] = None) -> list[dict]:
    """Sesiones programadas y reservas aprobadas que se cruzan con [inicio, fin)."""
    conflictos = []
    # Las sesiones duran dentro de un mismo día: basta revisar los días que toca el intervalo.
    sesiones = con.execute(
        "SELECT id, fecha, hora_inicio, hora_fin FROM sesiones "
        "WHERE espacio_id = ? AND estado = 'programada' AND fecha BETWEEN ? AND ?",
        (espacio_id, inicio[:10], fin[:10]),
    ).fetchall()
    for sesion in sesiones:
        sesion_inicio = f"{sesion['fecha']} {sesion['hora_inicio']}"
        sesion_fin = f"{sesion['fecha']} {sesion['hora_fin']}"
        if sesion_inicio < fin and inicio < sesion_fin:
            conflictos.append({"tipo": "sesion", "referencia": sesion["id"], "inicio": sesion_inicio, "fin": sesion_fin})
    reservas = con.execute(
        "SELECT id, inicio, fin FROM solicitudes "
        "WHERE espacio_id = ? AND estado = 'aprobada' AND id IS NOT ? AND inicio < ? AND ? < fin",
        (espacio_id, excluir_id, fin, inicio),
    ).fetchall()
    for reserva in reservas:
        conflictos.append({"tipo": "reserva", "referencia": reserva["id"], "inicio": reserva["inicio"], "fin": reserva["fin"]})
    return conflictos


def _solicitud(solicitud_id: int) -> dict:
    filas = db.consultar(f"SELECT {CAMPOS_SOLICITUD} FROM solicitudes WHERE id = ?", (solicitud_id,))
    fila = filas[0]
    fila["requiere_pago"] = bool(fila["requiere_pago"])
    fila["hora_devolucion"] = reglas.hora_devolucion(fila["fin"])
    fila["elementos_requeridos"] = json.loads(fila["elementos_requeridos"])
    if fila["tipo"] == "academica" and fila["actividad"] == "otra":
        fila["actividad"] = reglas.actividad_desde_texto(fila["descripcion"])
    fila["prioridad"] = reglas.prioridad(fila)
    return fila


def crear_solicitud(identidad: Identidad, datos: NuevaSolicitud) -> dict:
    with db.transaccion() as con:
        nuevo_id = crear_en(con, identidad, datos)
    return _solicitud(nuevo_id)


def obtener_solicitud(solicitud_id: int) -> dict:
    return _solicitud(solicitud_id)


def crear_en(con, identidad: Identidad, datos: NuevaSolicitud) -> int:
    """Inserta una solicitud pendiente dentro de la transacción recibida. Devuelve su ID."""
    tipo = tipo_solicitud_para(identidad.rol)  # 403 si el rol no puede solicitar aulas
    comercial = tipo == "comercial"
    espacio = con.execute("SELECT * FROM espacios WHERE id = ?", (datos.espacio_id,)).fetchone()
    if espacio is None:
        raise ErrorSolicitud(404, "espacio_no_encontrado", "No existe el espacio indicado.")
    if espacio["estado"] != "activo" or db.aula_bloqueada(con, datos.espacio_id):
        raise ErrorSolicitud(409, "espacio_no_disponible", "El espacio no está activo.")
    if datos.personas > espacio["aforo"]:
        raise ErrorSolicitud(409, "aforo_excedido", "Las personas superan el aforo del espacio.")
    if not elementos_compatibles(dict(espacio), datos.elementos_requeridos):
        raise ErrorSolicitud(409, "elementos_no_verificados", "No están verificados los elementos requeridos en el catálogo.")
    actividad = datos.actividad if datos.actividad != "otra" else reglas.actividad_desde_texto(datos.descripcion)
    cursor = con.execute(
        "INSERT INTO solicitudes (espacio_id, inicio, fin, personas, descripcion, tipo, solicitante_id, "
        "rol_solicitante, estado, requiere_pago, estado_pago, actividad, elementos_requeridos) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pendiente', ?, ?, ?, ?)",
        (datos.espacio_id, _texto(datos.inicio), _texto(datos.fin), datos.personas, datos.descripcion, tipo,
         identidad.usuario_id, identidad.rol, int(comercial), "pendiente" if comercial else None,
         "comercial" if comercial else actividad, json.dumps(datos.elementos_requeridos, ensure_ascii=False)),
    )
    return cursor.lastrowid


def aprobar_solicitud(solicitud_id: int, identidad: Identidad) -> dict:
    """Aprueba dentro de BEGIN IMMEDIATE: dos aprobaciones se ejecutan en serie."""
    with db.transaccion() as con:
        aprobar_en(con, solicitud_id, identidad)
    return _solicitud(solicitud_id)


def aprobar_en(con, solicitud_id: int, identidad: Identidad) -> None:
    """Se usa también dentro de la transacción de reubicación y aprobación."""
    fila = con.execute("SELECT * FROM solicitudes WHERE id = ?", (solicitud_id,)).fetchone()
    if fila is None:
        raise ErrorSolicitud(404, "solicitud_no_encontrada", "No existe la solicitud indicada.")
    if fila["estado"] != "pendiente":
        raise ErrorSolicitud(409, "no_pendiente", "La solicitud ya no está pendiente.")
    if fila["solicitante_id"] == identidad.usuario_id:
        raise ErrorSolicitud(403, "autoaprobacion_no_permitida", "No puede aprobar su propia solicitud.")
    espacio = con.execute("SELECT * FROM espacios WHERE id = ?", (fila["espacio_id"],)).fetchone()
    if espacio is None or espacio["estado"] != "activo" or db.aula_bloqueada(con, fila["espacio_id"]):
        raise ErrorSolicitud(409, "espacio_no_disponible", "El espacio no está activo.")
    if fila["personas"] > espacio["aforo"]:
        raise ErrorSolicitud(409, "aforo_excedido", "Las personas superan el aforo del espacio.")
    if not elementos_compatibles(dict(espacio), json.loads(fila["elementos_requeridos"])):
        raise ErrorSolicitud(409, "elementos_no_verificados", "Los elementos requeridos ya no están verificados.")
    if fila["tipo"] == "comercial" and con.execute(
        "SELECT id FROM solicitudes WHERE estado = 'pendiente' AND tipo = 'academica' "
        "AND espacio_id = ? AND inicio < ? AND ? < fin",
        (fila["espacio_id"], fila["fin"], fila["inicio"])).fetchone():
        raise ErrorSolicitud(409, "prioridad_academica", "Hay una solicitud académica pendiente de igual aula y horario con prioridad superior.")
    if buscar_conflictos(con, fila["espacio_id"], fila["inicio"], fila["fin"], excluir_id=solicitud_id):
        raise ErrorSolicitud(409, "solapamiento", "El espacio ya está ocupado en ese horario.")
    cursor = con.execute(
        "UPDATE solicitudes SET estado = 'aprobada', decidida_por = ?, decidida_en = datetime('now', 'localtime') "
        "WHERE id = ? AND estado = 'pendiente'",
        (identidad.usuario_id, solicitud_id),
    )
    if cursor.rowcount != 1:
        raise ErrorSolicitud(409, "no_pendiente", "La solicitud ya no está pendiente.")


def listar_solicitudes(identidad: Identidad) -> list[dict]:
    """La coordinadora ve todas. Los demás roles ven solo las suyas."""
    if identidad.rol == "coordinadora":
        filas = db.consultar(f"SELECT {CAMPOS_SOLICITUD} FROM solicitudes ORDER BY id")
    else:
        filas = db.consultar(
            f"SELECT {CAMPOS_SOLICITUD} FROM solicitudes WHERE solicitante_id = ? ORDER BY id",
            (identidad.usuario_id,),
        )
    for fila in filas:
        fila["requiere_pago"] = bool(fila["requiere_pago"])
        fila["hora_devolucion"] = reglas.hora_devolucion(fila["fin"])
        fila["elementos_requeridos"] = json.loads(fila["elementos_requeridos"])
        if fila["tipo"] == "academica" and fila["actividad"] == "otra":
            fila["actividad"] = reglas.actividad_desde_texto(fila["descripcion"])
        fila["prioridad"] = reglas.prioridad(fila)
    return sorted(filas, key=lambda fila: (-fila["prioridad"], fila["id"]))


def elementos_compatibles(espacio: dict, requeridos: list[str]) -> bool:
    if not requeridos:
        return True
    existentes = espacio.get("elementos")
    if isinstance(existentes, str):
        existentes = json.loads(existentes)
    if existentes is None:
        return False
    return {reglas.normalizar(e) for e in requeridos} <= {reglas.normalizar(e) for e in existentes}


def espacios_disponibles(inicio: datetime, fin: datetime, personas: Optional[int], elementos_requeridos=None) -> list[dict]:
    inicio_txt, fin_txt = _texto(inicio), _texto(fin)
    con = db.conectar()
    try:
        candidatos = con.execute(
            "SELECT * FROM espacios WHERE estado = 'activo' AND (? IS NULL OR aforo >= ?) ORDER BY id",
            (personas, personas),
        ).fetchall()
        return [dict(espacio) for espacio in candidatos
                if not db.aula_bloqueada(con, espacio["id"]) and not buscar_conflictos(con, espacio["id"], inicio_txt, fin_txt)
                and elementos_compatibles(dict(espacio), elementos_requeridos or [])]
    finally:
        con.close()


def listar_reservas(fecha: Optional[date]) -> list[dict]:
    """Reservas aprobadas. Sin datos del solicitante ni descripción. Un intervalo que cruza medianoche aparece en ambos días."""
    if fecha is None:
        filas = db.consultar(
            "SELECT id, espacio_id, inicio, fin, tipo, estado_pago FROM solicitudes "
            "WHERE estado = 'aprobada' ORDER BY inicio, espacio_id"
        )
    else:
        dia = datetime(fecha.year, fecha.month, fecha.day)
        siguiente = dia + timedelta(days=1)
        filas = db.consultar(
            "SELECT id, espacio_id, inicio, fin, tipo, estado_pago FROM solicitudes "
            "WHERE estado = 'aprobada' AND inicio < ? AND ? < fin ORDER BY inicio, espacio_id",
            (_texto(siguiente), _texto(dia)),
        )
    for fila in filas:
        fila["hora_devolucion"] = reglas.hora_devolucion(fila["fin"])
    return filas
