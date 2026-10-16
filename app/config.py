"""Parámetros de la aplicación. Cada valor puede sobrescribirse con una variable de entorno (.env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ_PROYECTO / ".env")


def _texto(nombre: str, defecto: str = "") -> str:
    """Lee una variable de texto; si está vacía o no existe, usa el valor por defecto."""
    return os.getenv(nombre, "").strip() or defecto


def _entero(nombre: str, defecto: int) -> int:
    """Lee una variable entera; si no es un entero válido, usa el valor por defecto."""
    try:
        return int(os.getenv(nombre, "").strip())
    except ValueError:
        return defecto


# Rutas
RUTA_BASE_DATOS = _texto("RUTA_BASE_DATOS", str(RAIZ_PROYECTO / "gestion_salas.db"))
RUTA_DATOS = _texto("RUTA_DATOS", str(RAIZ_PROYECTO / "data" / "ficticio"))

# Bloques de tiempo: las horas de las sesiones deben caer en múltiplos de estos minutos (operación 24/7)
MINUTOS_BLOQUE = _entero("MINUTOS_BLOQUE", 15)

# Cliente de IA: IA_PROVEEDOR = "ollama" o "openai" (API compatible con OpenAI)
IA_PROVEEDOR = _texto("IA_PROVEEDOR")
IA_URL = _texto("IA_URL")
IA_MODELO = _texto("IA_MODELO")
IA_API_KEY = _texto("IA_API_KEY")
IA_TIMEOUT_SEGUNDOS = _entero("IA_TIMEOUT_SEGUNDOS", 20)

# Identidad de desarrollo: NO es autenticación. Ver app/identidad.py.
USUARIO_DESARROLLO = _texto("USUARIO_DESARROLLO")
ROL_DESARROLLO = _texto("ROL_DESARROLLO")

# Umbrales de reglas de negocio: se definirán en la fase 2, junto con app/reglas.py.
