# Sistema Central de Gestión Operativa de Campuslands

> Todos los datos de este repositorio son **ficticios**. Los nombres de personas, grupos, clientes y cohortes fueron inventados para pruebas y no corresponden a registros reales.

## Estado

- **Fase 1:** completa. Base del proyecto, carga validada de datos ficticios, API de lectura, interfaz mínima y conexión de prueba a la IA.
- **Fase 1, corrección de persistencia:** en revisión en la rama `fix/persistencia-carga`.
- **Fase 2:** pendiente. Reglas de negocio, reservas, préstamos, incidencias y triaje con IA.

## Problema

La programación de salas vive en una hoja de cálculo que llevan dos personas. Una programa clases y reuniones, con prioridad para Zona Franca. La otra alquila las franjas que quedan libres. La hoja no detecta solapamientos ni excesos de aforo, y no deja trazabilidad de los cambios.

El sistema centraliza espacios, sesiones (clases, reuniones y alquileres), cohortes y, en la fase 2, préstamos de recursos e incidencias.

## Integrantes

[POR DEFINIR]

## Stack

- Python 3.11 o superior, FastAPI, SQLite (módulo `sqlite3`) y Pydantic v2.
- Frontend en HTML, CSS y JavaScript sin frameworks, servido por FastAPI.
- Pruebas con `unittest` de la biblioteca estándar. No requiere dependencias adicionales.

## Uso de IA

- **En la aplicación:** `app/ia.py` es un cliente que funciona con Ollama o con cualquier API compatible con OpenAI, según variables de entorno. Si la IA no responde, devuelve un error claro. Nunca simula respuestas. El triaje de incidencias llegará en la fase 2.
- **En el desarrollo:** [POR CONFIRMAR POR EL EQUIPO: herramientas de IA usadas y en qué tareas].

## Reglas de negocio

### Reglas de carga (fase 1, vigentes)

- Los CSV se validan fila por fila. Una fila inválida se rechaza con su motivo, su archivo y su número de línea, y no impide cargar las demás.
- Se corrige solo lo inequívoco, por ejemplo `CANCELADO` a `cancelada`. Cada corrección queda registrada.
- Una hora sin AM/PM se rechaza. No se adivina.
- Los solapamientos, los aforos excedidos y las cohortes vencidas se cargan y se marcan como conflictos. No se rechazan.
- Una importación reemplaza la carga anterior solo si los tres archivos obligatorios existen, se pueden leer y tienen las columnas requeridas. Si algo de eso falla, la base queda como estaba.
- Cada intento de importación queda registrado en la tabla `importaciones`, también cuando falla.
- El arranque de la aplicación no importa datos. La importación es explícita.

### Reglas de negocio (fase 2, pendientes)

- Una reserva o préstamo no puede cruzarse con una sesión programada.
- Zona Franca tiene prioridad sobre los alquileres.
- No se alquilan espacios en mantenimiento o inhabilitados.
- Los umbrales se definirán como variables de entorno en `app/config.py`.

## Instalación

Requisitos: Python 3.11 o superior.

**Windows (PowerShell):**

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m app.carga_datos
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Linux o Mac:**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.carga_datos
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abre `http://127.0.0.1:8000`. El host `127.0.0.1` evita que otros equipos de la red usen el endpoint de recarga, que todavía no tiene autenticación.

**Pruebas:**

```bash
python -m unittest discover -s tests -t .
```

**Variables de entorno:** todas son opcionales. Están documentadas en `.env.example`. Los valores vacíos usan los valores por defecto de `app/config.py`.
</content>
