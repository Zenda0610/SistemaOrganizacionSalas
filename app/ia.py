"""Cliente de IA. Sirve para Ollama o para cualquier API compatible con OpenAI, solo cambiando variables de entorno.

Nunca simula respuestas: si la IA no responde, devuelve un error claro.
"""
import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import httpx

from app import config

logger = logging.getLogger(__name__)

PROVEEDORES = ("ollama", "openai")


def _openrouter() -> bool:
    return urlsplit(config.IA_URL).hostname == "openrouter.ai"


def _problema_configuracion() -> str | None:
    """Devuelve el motivo por el que la IA no está configurada, o None si lo está."""
    if config.IA_PROVEEDOR not in PROVEEDORES:
        return "IA_PROVEEDOR no está configurado o no es válido (use 'ollama' u 'openai')."
    if not config.IA_URL:
        return "IA_URL no está configurada."
    if not config.IA_MODELO:
        return "IA_MODELO no está configurado."
    if _openrouter():
        if not config.IA_MODELO.endswith(":free"):
            return "OpenRouter requiere un modelo :free explícito. No se usarán modelos de pago."
        if not config.IA_API_KEY or config.IA_API_KEY == 'PEGA_AQUI_TU_CLAVE':
            return "Falta IA_API_KEY en el .env del servidor."
    return None


def _encabezados() -> dict:
    return {"Authorization": f"Bearer {config.IA_API_KEY}"} if config.IA_API_KEY else {}


def _construir_peticion(prompt: str) -> tuple[str, dict]:
    base = config.IA_URL.rstrip("/")
    if config.IA_PROVEEDOR == "ollama":
        return f"{base}/api/generate", {"model": config.IA_MODELO, "prompt": prompt, "stream": False}
    cuerpo = {
        "model": config.IA_MODELO,
        "messages": [{"role": "user", "content": prompt}],
    }
    if _openrouter():
        cuerpo["provider"] = {"allow_fallbacks": False, "max_price": {"prompt": 0, "completion": 0}}
    return f"{base}/chat/completions", cuerpo


def _verificar_modelo_gratuito(datos: dict) -> None:
    modelo = next((m for m in datos["data"] if m["id"] == config.IA_MODELO), None)
    if modelo is None:
        raise ValueError("Modelo gratuito no disponible en el catálogo actual.")
    precios = modelo["pricing"]
    if any(Decimal(str(precios[campo])) != 0 for campo in ("prompt", "completion")):
        raise ValueError("El modelo ya no es gratuito.")


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
        if _openrouter():
            catalogo = httpx.get(config.IA_URL.rstrip("/") + "/models", timeout=config.IA_TIMEOUT_SEGUNDOS)
            catalogo.raise_for_status()
            _verificar_modelo_gratuito(catalogo.json())
        respuesta = httpx.post(url, json=cuerpo, headers=_encabezados(), timeout=config.IA_TIMEOUT_SEGUNDOS)
        respuesta.raise_for_status()
        texto = _extraer_texto(respuesta.json()).strip()
    except httpx.TimeoutException:
        return {"ok": False, "error": f"La IA no respondió en {config.IA_TIMEOUT_SEGUNDOS} segundos."}
    except httpx.ConnectError:
        return {"ok": False, "error": f"No se pudo conectar con la IA en {config.IA_URL}. Verifique que el servicio esté activo."}
    except httpx.HTTPStatusError as error:
        return {"ok": False, "error": f"La IA respondió con error HTTP {error.response.status_code}."}
    except httpx.HTTPError:
        logger.warning("Error de comunicación con la IA (sin detalle de credenciales).")
        return {"ok": False, "error": "Error de comunicación con la IA."}
    except (ValueError, KeyError, IndexError, TypeError, AttributeError, InvalidOperation):
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
        if _openrouter():
            _verificar_modelo_gratuito(respuesta.json())
    except (httpx.HTTPError, ValueError, KeyError, TypeError, InvalidOperation):
        logger.warning("IA no disponible (sin detalle de credenciales).")
        return {**base_respuesta, "estado": "no_disponible",
                "mensaje": f"No se pudo conectar con la IA en {config.IA_URL}."}
    return {**base_respuesta, "estado": "conectada",
            "mensaje": "Catálogo accesible; la inferencia y la autorización de la clave no se verifican con esta consulta."}
