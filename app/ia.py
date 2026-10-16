"""Cliente de IA. Sirve para Ollama o para cualquier API compatible con OpenAI, solo cambiando variables de entorno.

Nunca simula respuestas: si la IA no responde, devuelve un error claro.
"""
import logging

import httpx

from app import config

logger = logging.getLogger(__name__)

PROVEEDORES = ("ollama", "openai")


def _problema_configuracion() -> str | None:
    """Devuelve el motivo por el que la IA no está configurada, o None si lo está."""
    if config.IA_PROVEEDOR not in PROVEEDORES:
        return "IA_PROVEEDOR no está configurado o no es válido (use 'ollama' u 'openai')."
    if not config.IA_URL:
        return "IA_URL no está configurada."
    if not config.IA_MODELO:
        return "IA_MODELO no está configurado."
    return None


def _encabezados() -> dict:
    return {"Authorization": f"Bearer {config.IA_API_KEY}"} if config.IA_API_KEY else {}


def _construir_peticion(prompt: str) -> tuple[str, dict]:
    base = config.IA_URL.rstrip("/")
    if config.IA_PROVEEDOR == "ollama":
        return f"{base}/api/generate", {"model": config.IA_MODELO, "prompt": prompt, "stream": False}
    return f"{base}/chat/completions", {
        "model": config.IA_MODELO,
        "messages": [{"role": "user", "content": prompt}],
    }


def _extraer_texto(datos: dict) -> str:
    if config.IA_PROVEEDOR == "ollama":
        return datos["response"]
    return datos["choices"][0]["message"]["content"]


def consultar_ia(prompt: str) -> dict:
    """Envía un prompt y devuelve {'ok': True, 'texto': ...} o {'ok': False, 'error': ...}."""
    problema = _problema_configuracion()
    if problema:
        return {"ok": False, "error": problema}
    url, cuerpo = _construir_peticion(prompt)
    try:
        respuesta = httpx.post(url, json=cuerpo, headers=_encabezados(), timeout=config.IA_TIMEOUT_SEGUNDOS)
        respuesta.raise_for_status()
        texto = _extraer_texto(respuesta.json()).strip()
    except httpx.TimeoutException:
        return {"ok": False, "error": f"La IA no respondió en {config.IA_TIMEOUT_SEGUNDOS} segundos."}
    except httpx.ConnectError:
        return {"ok": False, "error": f"No se pudo conectar con la IA en {config.IA_URL}. Verifique que el servicio esté activo."}
    except httpx.HTTPStatusError as error:
        return {"ok": False, "error": f"La IA respondió con error HTTP {error.response.status_code}."}
    except httpx.HTTPError as error:
        logger.warning("Error de comunicación con la IA: %s", error)
        return {"ok": False, "error": "Error de comunicación con la IA."}
    except (ValueError, KeyError, IndexError, TypeError):
        return {"ok": False, "error": "La IA devolvió una respuesta con formato inesperado."}
    if not texto:
        return {"ok": False, "error": "La IA devolvió una respuesta vacía."}
    return {"ok": True, "texto": texto}


def verificar_salud() -> dict:
    """Prueba la conexión con el proveedor configurado sin enviar datos del usuario."""
    base_respuesta = {"proveedor": config.IA_PROVEEDOR or None, "modelo": config.IA_MODELO or None}
    problema = _problema_configuracion()
    if problema:
        return {**base_respuesta, "estado": "no_disponible", "mensaje": problema}
    ruta = "/api/tags" if config.IA_PROVEEDOR == "ollama" else "/models"
    try:
        respuesta = httpx.get(config.IA_URL.rstrip("/") + ruta, headers=_encabezados(),
                              timeout=config.IA_TIMEOUT_SEGUNDOS)
        respuesta.raise_for_status()
    except httpx.HTTPError as error:
        logger.warning("IA no disponible: %s", error)
        return {**base_respuesta, "estado": "no_disponible",
                "mensaje": f"No se pudo conectar con la IA en {config.IA_URL}."}
    return {**base_respuesta, "estado": "conectada", "mensaje": "La IA respondió correctamente."}
