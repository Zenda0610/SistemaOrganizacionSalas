"""Reubicación explícita de SER en Azul para Zona Franca; nunca mueve al proponer."""
import json
from datetime import datetime
from uuid import uuid4

from app import db, reglas, solicitudes
from app.permisos import tiene_permiso
from app.identidad import ErrorAcceso, Identidad
from app.solicitudes import ErrorSolicitud


def _coordinadora(identidad: Identidad) -> None:
    if not tiene_permiso(identidad.rol, "autorizar_solicitud"):
        raise ErrorAcceso(403, "sin_permiso", "Solo la coordinadora puede autorizar una reubicación.")


def _error(codigo: str, mensaje: str):
    raise ErrorSolicitud(409, codigo, mensaje)


def _fila(con, tabla: str, identificador):
    fila = con.execute(f"SELECT * FROM {tabla} WHERE id = ?", (identificador,)).fetchone()
    return dict(fila) if fila else None


def origen_ser(con, solicitud: dict):
    """Único bloqueo elegible. No autoriza ni mueve; también sirve para proponer desde el chat."""
    aula = _fila(con, "espacios", solicitud["espacio_id"])
    actividad_solicitud = solicitud.get("actividad", "otra")
    if actividad_solicitud == "otra":
        actividad_solicitud = reglas.actividad_desde_texto(solicitud.get("descripcion", ""))
    if solicitud.get("tipo") != "academica" or actividad_solicitud != "zona_franca" or not aula or not reglas.es_azul(aula):
        return None
    cruces = solicitudes.buscar_conflictos(con, aula["id"], solicitud["inicio"], solicitud["fin"])
    if len(cruces) != 1:
        return None
    cruce = cruces[0]
    tabla = "solicitudes" if cruce["tipo"] == "reserva" else "sesiones"
    origen = _fila(con, tabla, cruce["referencia"])
    if tabla == "solicitudes":
        actividad = origen["actividad"] if origen["actividad"] != "otra" else reglas.actividad_desde_texto(origen["descripcion"])
        elegible = origen["tipo"] == "academica" and actividad == "ser" and origen["estado"] == "aprobada"
        inicio, fin = origen["inicio"], origen["fin"]
        personas = origen["personas"]
    else:
        elegible = origen["area"] == "ser" and not origen["es_zona_franca"] and origen["estado"] == "programada"
        inicio, fin = f"{origen['fecha']} {origen['hora_inicio']}", f"{origen['fecha']} {origen['hora_fin']}"
        personas = origen["cantidad_personas"]
    if not elegible:
        return None
    return {"tabla": tabla, "origen": origen, "inicio": inicio, "fin": fin, "personas": personas}


def _preparar(con, solicitud: dict, identidad: Identidad, destino_id=None) -> dict:
    if solicitud["estado"] != "pendiente":
        _error("no_pendiente", "La solicitud ya no está pendiente.")
    if solicitud["solicitante_id"] == identidad.usuario_id:
        raise ErrorSolicitud(403, "autoaprobacion_no_permitida", "No puede aprobar su propia solicitud.")
    fuente = origen_ser(con, solicitud)
    if fuente is None:
        _error("reubicacion_no_aplicable", "Solo se reubica SER desde el aula preferida para una solicitud académica de Zona Franca con un único bloqueo.")
    ahora = datetime.now()
    if datetime.fromisoformat(fuente["inicio"]) <= ahora or datetime.fromisoformat(solicitud["inicio"]) <= ahora:
        _error("actividad_iniciada", "No se desplaza una actividad iniciada ni se reubica para una solicitud ya iniciada.")
    azul = _fila(con, "espacios", solicitud["espacio_id"])
    if azul["estado"] != "activo" or db.aula_bloqueada(con, azul["id"]) or solicitud["personas"] > reglas.aforo_permitido(azul):
        _error("espacio_no_disponible", "El aula preferida no está activa o no tiene aforo suficiente para Zona Franca.")
    if not solicitudes.elementos_compatibles(azul, json.loads(solicitud["elementos_requeridos"])):
        _error("elementos_no_verificados", "No están verificados los elementos que necesita Zona Franca.")
    requeridos = json.loads(fuente["origen"]["elementos_requeridos"])
    candidatas = [dict(a) for a in con.execute("SELECT * FROM espacios WHERE estado = 'activo' AND aforo >= ?", (fuente["personas"],))
                  if a["id"] != azul["id"] and (destino_id is None or a["id"] == destino_id)
                  and not db.aula_bloqueada(con, a["id"])
                  and fuente["personas"] <= reglas.aforo_permitido(a)
                  and solicitudes.elementos_compatibles(dict(a), requeridos)
                  and not solicitudes.buscar_conflictos(con, a["id"], fuente["inicio"], fuente["fin"])]
    candidatas = reglas.ordenar_candidatos(candidatas)
    if not candidatas:
        _error("sin_alternativa", "No hay otra aula verificada, libre y con aforo para todo el intervalo de SER. Se conserva su reserva.")
    return {"solicitud": solicitud, **fuente, "aula_origen": azul, "destino": candidatas[0]}


def _vista(fila: dict) -> dict:
    datos = json.loads(fila["datos"])
    return {"id": fila["id"], "estado": fila["estado"], "solicitud_id": fila["solicitud_id"],
            "origen_tipo": datos["tabla"], "origen_id": datos["origen"]["id"],
            "aula_origen": datos["aula_origen"]["nombre"], "aula_destino": datos["destino"]["nombre"],
            "destino_id": datos["destino"]["id"], "inicio": datos["inicio"], "fin": datos["fin"],
            "personas": datos["personas"], "solicitud_inicio": datos["solicitud"]["inicio"],
            "autorizada_por": fila["autorizada_por"], "autorizada_en": fila["autorizada_en"]}


def proponer(solicitud_id: int, identidad: Identidad) -> dict:
    _coordinadora(identidad)
    with db.transaccion() as con:
        solicitud = _fila(con, "solicitudes", solicitud_id)
        if not solicitud:
            raise ErrorSolicitud(404, "solicitud_no_encontrada", "No existe la solicitud.")
        datos = _preparar(con, solicitud, identidad)
        identificador = uuid4().hex
        con.execute("INSERT INTO reubicaciones (id, solicitud_id, datos, estado, propuesta_por) VALUES (?, ?, ?, 'propuesta', ?)",
                    (identificador, solicitud_id, json.dumps(datos, ensure_ascii=False), identidad.usuario_id))
        return _vista(_fila(con, "reubicaciones", identificador))


def consultar(identificador: str, identidad: Identidad) -> dict:
    _coordinadora(identidad)
    filas = db.consultar("SELECT * FROM reubicaciones WHERE id = ?", (identificador,))
    if not filas:
        raise ErrorSolicitud(404, "reubicacion_no_encontrada", "No existe la propuesta de reubicación.")
    return _vista(filas[0])


def confirmar(identificador: str, identidad: Identidad) -> dict:
    _coordinadora(identidad)
    with db.transaccion() as con:
        fila = _fila(con, "reubicaciones", identificador)
        if not fila:
            raise ErrorSolicitud(404, "reubicacion_no_encontrada", "No existe la propuesta de reubicación.")
        if fila["estado"] == "aplicada":
            return _vista(fila)  # confirmación repetida, sin mover ni aprobar de nuevo
        anterior = json.loads(fila["datos"])
        solicitud = _fila(con, "solicitudes", fila["solicitud_id"])
        origen = _fila(con, anterior["tabla"], anterior["origen"]["id"])
        if solicitud != anterior["solicitud"] or origen != anterior["origen"]:
            _error("propuesta_desactualizada", "La solicitud o la actividad original cambió. Evalúe una nueva propuesta.")
        actual = _preparar(con, solicitud, identidad, anterior["destino"]["id"])
        # Revalidación bajo el mismo bloqueo de escritura: ninguna aprobación puede intercalarse.
        con.execute(f"UPDATE {actual['tabla']} SET espacio_id = ? WHERE id = ?",
                    (actual["destino"]["id"], origen["id"]))
        solicitudes.aprobar_en(con, fila["solicitud_id"], identidad)
        con.execute("UPDATE reubicaciones SET estado = 'aplicada', autorizada_por = ?, "
                    "autorizada_en = datetime('now', 'localtime') WHERE id = ?",
                    (identidad.usuario_id, identificador))
        return _vista(_fila(con, "reubicaciones", identificador))
