# Gestión Operativa de Campuslands

> Un espacio para cada actividad: aulas, equipos e incidencias en una sola fuente, con reglas que ejecuta el servidor y una IA que propone pero no decide.

## Problema

La programación de aulas, el préstamo de equipos y los reportes operativos viven en
planillas y mensajes sueltos: se cruzan reservas, se presta un equipo dañado y la
coordinadora no ve de un vistazo qué requiere acción. Este MVP integra calendario,
solicitudes por chat, aprobación, incidencias con triaje por IA, préstamos y un
asistente de coordinación sobre una base SQLite común.

## Integrantes

- David Leonardo Martinez Perez
- Johan Alejandro Serrano Rivera
- Maria Jose CastroSanjuan
- Maria Gabriela Rincon Leon

[POR COMPLETAR: funciones individuales]. Se conservan las autorías existentes de Git.

## Stack

- Backend: Python 3.11/3.12, FastAPI, Pydantic v2, SQLite (`sqlite3`), httpx, python-dotenv.
- Frontend: HTML, CSS y JavaScript sin frameworks (tipografía Lexend desde Google Fonts).
- IA: cualquier API compatible con OpenAI u Ollama; configurada con OpenRouter y un modelo `:free`.
- Pruebas: `unittest` (Python) y Node.js (DOM y HTTP simulados).
- Dependencias fijadas en `requirements.txt`.

## Arquitectura

```text
Navegador (static/*.html, *.js, *.css)
   │  fetch /api/...
   ▼
FastAPI  app/main.py ── identidad.py + permisos.py (rol decidido en el servidor)
   │
   ├── solicitudes.py, reglas.py, reubicaciones.py ── aulas, reservas, aprobación
   ├── chat.py ─────────────── interpreta el chat ─┐
   ├── operaciones.py ──────── incidencias/equipos ├──► ia.py ──► proveedor IA (OpenRouter / Ollama)
   ├── coordinacion.py ─────── asistente ──────────┘
   ├── carga_datos.py ──────── CSV ficticios → validación → rechazos / conflictos
   ▼
SQLite  (db.py: esquema, transacciones BEGIN IMMEDIATE)
```

| Archivo | Responsabilidad |
|---|---|
| `app/main.py` | Rutas de la API, manejo uniforme de errores en JSON y servicio de la interfaz estática |
| `app/config.py` | Parámetros leídos de variables de entorno / `.env` |
| `app/db.py` | Esquema SQLite, migraciones suaves, transacciones y consultas |
| `app/identidad.py` | Identidad de desarrollo configurada en el servidor (no es autenticación) |
| `app/permisos.py` | Matriz de permisos por rol y dependencia `requerir_permiso` |
| `app/modelos.py` | Modelos Pydantic de sesiones y cohortes |
| `app/carga_datos.py` | Importación de CSV, validación, rechazos, correcciones y conflictos |
| `app/reglas.py` | Prioridades, aforo efectivo, aula preferida, hora de devolución |
| `app/solicitudes.py` | Disponibilidad, creación, listado por rol y aprobación de solicitudes |
| `app/reubicaciones.py` | Propuesta y confirmación de reubicación de sesiones SER |
| `app/chat.py` | Chat de solicitudes: borradores, propuesta y confirmación |
| `app/operaciones.py` | Equipos, préstamos, devoluciones, incidencias, revisión y bloqueos |
| `app/coordinacion.py` | Resumen de notificaciones y asistente de IA para la coordinadora |
| `app/ia.py` | Cliente de IA (OpenAI-compatible u Ollama) sin respuestas simuladas |
| `scripts/cargar_demo.py` | Carga repetible de datos ficticios en `demo.sqlite` |

## Módulos

1. **Espacios y solicitudes**: calendario 24/7 en bloques de 15 min, chat que propone
   una solicitud, confirmación que crea una solicitud *pendiente* y aprobación por la coordinadora.
2. **Préstamos de equipos**: inventario (equipos ficticios marcados), préstamo a nombre
   propio y devolución, sin doble préstamo ni doble devolución.
3. **Incidencias con triaje por IA**: el reporte se guarda primero; la IA propone
   categoría, prioridad, área y justificación; la coordinadora revisa y decide si bloquea.
4. **Asistente de coordinación**: lista de notificaciones calculada desde la base
   (importantes primero) y resumen redactado por la IA, sin ejecutar acciones.

**Regla central:** un bloqueo confirmado por incidencia saca el aula o el equipo de
la disponibilidad para nuevas asignaciones, pero conserva y muestra las reservas,
sesiones y préstamos afectados (no los cancela automáticamente).

## Reglas de negocio

| Regla | Archivo y función | Demostración (válido / inválido) |
|---|---|---|
| Alias contra nombres cargados; ambigüedad pide aclaración | `app/chat.py: resolver_espacio` | «Blanca» resuelve el aula / un nombre ambiguo pide aclaración |
| Zona Franca, SER e inglés iguales; comercial después | `app/reglas.py: prioridad`; `app/solicitudes.py: aprobar_en` | Académica se ordena primero / comercial queda detrás |
| Aula preferida de Zona Franca configurable | `app/config.py: AULA_PREFERIDA_ZONA_FRANCA`; `app/reglas.py: es_azul, ordenar_candidatos` | Sala Azul se propone primero / otra solo si está ocupada |
| Aforo efectivo con porcentaje y máximo físico | `app/reglas.py: aforo_permitido`; `app/solicitudes.py: crear_en, aprobar_en` | 8 personas en Blanca (12) / 13 personas → 409 `aforo_excedido` |
| Reservas [inicio, fin) sin solapamiento, admiten medianoche | `app/solicitudes.py: validar_intervalo, buscar_conflictos` | 14:00–15:00 libre / aprobar una segunda solicitud cruzada → rechazo |
| Devolución prevista fin − 5 min; bloquea hasta fin | `app/reglas.py: hora_devolucion` | Reserva hasta 15:00 muestra 14:55 |
| Confirmar crea pendiente; solo coordinadora aprueba, sin autoaprobación | `app/solicitudes.py: crear_en, aprobar_en`; `app/permisos.py` | Coordinadora aprueba / profesor → 403 |
| Borradores por usuario y conversación, versionados | `app/chat.py: _comprobar_version, _confirmar` | «Confirmo» crea una vez / repetir no duplica |
| Prioridad de incidencia no implica bloqueo; solo coordinadora bloquea | `app/operaciones.py: reportar, revisar` | Revisar sin bloquear / profesor revisando → 403 |
| Aula bloqueada no admite nuevas asignaciones | `app/db.py: aula_bloqueada`; `app/solicitudes.py` | Otra aula libre se propone / el aula bloqueada se rechaza |
| Equipo no disponible no se presta; sin doble préstamo ni doble devolución | `app/operaciones.py: prestar, devolver`; índice `prestamo_activo_equipo` | Préstamo de equipo libre / segundo préstamo → 409 `equipo_prestado` |
| Hora ambigua se rechaza; solapamiento y aforo del CSV se cargan y se señalan | `app/carga_datos.py: _validar_sesion, _detectar_conflictos` | 15 sesiones cargadas / 1 rechazo y 2 conflictos |
| Cada solicitante ve solo sus solicitudes e incidencias; coordinadora ve todas | `app/solicitudes.py: listar_solicitudes`; `app/operaciones.py: listar_incidencias` | Profesor ve las suyas / coordinadora ve todas |
| Notificación importante: pendiente que empieza en < 24 h o ya vencida, incidencia alta/crítica, bloqueo con afectados | `app/coordinacion.py: resumen` | Pendiente de mañana → importante / pendiente en 5 días → necesaria |

## Uso de IA en la aplicación

`app/ia.py` habla con APIs compatibles con OpenAI u Ollama. Con OpenRouter exige un
modelo `:free`, comprueba en el catálogo que su precio sea cero y no cambia a modelos de pago.

- **Chat de solicitudes** (`app/chat.py`): la IA traduce el mensaje a una acción JSON;
  el servidor la valida, consulta disponibilidad y arma la propuesta.
- **Clasificación de incidencias** (`app/operaciones.py: reportar`): la IA propone
  categoría, prioridad, área y justificación de listas cerradas; se valida con Pydantic.
- **Asistente de coordinación** (`app/coordinacion.py`): la IA resume la lista
  calculada por el servidor, sin inventar y sin ejecutar acciones.

**La IA propone; el servidor y la coordinadora deciden.** Los datos se envían como
JSON con la instrucción de ignorar órdenes contenidas en ellos. Una salida inválida no
ejecuta nada. Nunca hay respuestas simuladas: si el proveedor falla, la API responde
`503 ia_no_disponible` (en el asistente, junto con la lista calculada). La clave solo
vive en el `.env` del servidor y no llega al navegador. Detalle de validaciones:
[docs/validacion.md](docs/validacion.md).

## Uso de IA en el desarrollo

- Codex: implementación de backend y frontend, datos ficticios, pruebas y revisión en navegador.
- Claude Code: asistente de coordinación, vistas por rol, rediseño visual responsive y este README.
- Gemini: revisión del repositorio a partir de una instantánea (`auditoria_gemini.txt`). [POR CONFIRMAR]

Las pruebas usan IA simulada solo dentro de los tests; no se presentan como inferencia real.

## Roles y permisos

| Permiso | profesor | administrativo | estudiante | empresa | coordinadora |
|---|:-:|:-:|:-:|:-:|:-:|
| `solicitar_aula_academica` | ✔ | ✔ | | | |
| `solicitar_alquiler_comercial` | | | ✔ | ✔ | |
| `prestar_equipo` | ✔ | ✔ | | | ✔ |
| `autorizar_solicitud` | | | | | ✔ |
| `recargar_datos` | | | | | ✔ |
| `gestionar_recursos` | | | | | ✔ |
| `ver_notificaciones` (asistente) | | | | | ✔ |
| `ver_datos` (cohortes y calidad) | | | | | ✔ |

Sin identidad la API responde 401; sin permiso, 403. La identidad sale **solo** de
`USUARIO_DESARROLLO` y `ROL_DESARROLLO` en el servidor: el cuerpo, las cabeceras o la
query no pueden cambiarla. Es una identidad de desarrollo provisional, **no autenticación**.
La interfaz oculta lo que el rol no puede usar, pero la verificación real ocurre en el servidor.

## Datos

Todos los datos son **ficticios** (`data/ficticio/`): 9 aulas, 15 sesiones de la
semana 12–18/10/2026, 3 cohortes y 8 equipos. La carga (`app/carga_datos.py`) valida
cada fila, guarda rechazos y correcciones con archivo y fila de origen, señala
conflictos (solapamientos, aforo excedido) sin descartarlos y registra cada intento
en la tabla `importaciones`. Casos borde documentados en
[data/ficticio/CASOS_BORDE.md](data/ficticio/CASOS_BORDE.md): 1 rechazo y 2 conflictos.
La recarga es transaccional: si falla, conserva los datos anteriores.

## Instalación y ejecución

Requisitos: Python 3.11 o 3.12 y, para las pruebas de interfaz, Node.js.

Windows (PowerShell):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m scripts.cargar_demo
```

Linux/macOS:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
.venv/bin/python -m scripts.cargar_demo
```

Variables del `.env` (plantilla en `.env.example`; **`.env` nunca se sube**):

| Variable | Uso |
|---|---|
| `IA_PROVEEDOR` | `openai` (API compatible) u `ollama` |
| `IA_URL` | p. ej. `https://openrouter.ai/api/v1` |
| `IA_MODELO` | con OpenRouter debe terminar en `:free` |
| `IA_API_KEY` | clave del proveedor, sin comillas ni espacios (solo en `.env`) |
| `IA_TIMEOUT_SEGUNDOS` | tiempo máximo de respuesta de la IA |
| `USUARIO_DESARROLLO`, `ROL_DESARROLLO` | identidad de desarrollo del servidor |
| `RUTA_BASE_DATOS`, `RUTA_DATOS` | vacías = `gestion_salas.db` y datos por defecto |
| `MINUTOS_DEVOLUCION_ANTICIPADA`, `PORCENTAJE_AFORO_MAXIMO`, `AULA_PREFERIDA_ZONA_FRANCA` | reglas configurables |

`scripts.cargar_demo` crea `demo.sqlite`, separada de la base operativa. Repetirla no
duplica equipos, no reactiva los bloqueados y no borra préstamos. Para recargar los CSV
en la base configurada: `python -m app.carga_datos` o `POST /api/datos/recargar` (coordinadora).
Comprobar la IA: `GET /api/ia/salud` (verifica el catálogo, no la inferencia).

## Demo con dos servidores

Dos terminales en la raíz, sobre la misma base. Cada servidor tiene su identidad;
el navegador no elige el rol. Las variables de entorno tienen prioridad sobre `.env`.

Windows (PowerShell), profesor y coordinadora:

```powershell
$env:RUTA_BASE_DATOS = Join-Path (Get-Location) 'demo.sqlite'
$env:USUARIO_DESARROLLO = 'dev-profesor'; $env:ROL_DESARROLLO = 'profesor'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
$env:RUTA_BASE_DATOS = Join-Path (Get-Location) 'demo.sqlite'
$env:USUARIO_DESARROLLO = 'dev-coordinadora'; $env:ROL_DESARROLLO = 'coordinadora'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Linux/macOS:

```bash
RUTA_BASE_DATOS="$PWD/demo.sqlite" USUARIO_DESARROLLO=dev-profesor ROL_DESARROLLO=profesor \
  .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
RUTA_BASE_DATOS="$PWD/demo.sqlite" USUARIO_DESARROLLO=dev-coordinadora ROL_DESARROLLO=coordinadora \
  .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Abrir http://127.0.0.1:8000 (profesor) y http://127.0.0.1:8001 (coordinadora), no `file:///`.
Swagger en `/docs`. Tras editar `.env`, detener con Ctrl+C y volver a iniciar.
Para ver ocupación, seleccionar 2026-10-16; para nuevas solicitudes, 2026-10-19.
Guion de la presentación: [docs/sustentacion.md](docs/sustentacion.md).

## Pruebas

```bash
python -m unittest discover -s tests -t .   # 160 pruebas
node tests/test_interfaz.js                  # interfaz con DOM/HTTP simulados
```

Con `.venv`, usar su intérprete (`.\.venv\Scripts\python.exe` o `.venv/bin/python`).
Las pruebas usan una SQLite temporal y copias de los CSV; nunca tocan la base real.
La IA se simula solo en las pruebas unitarias.

## Limitaciones conocidas

- La identidad es de desarrollo y se fija por servidor; no hay inicio de sesión real.
- No hay pagos: una solicitud comercial queda con pago pendiente no verificado.
- Datos e inventario ficticios; el inventario oficial de equipos está pendiente.
- La reubicación completa y la entrega/devolución física de aulas siguen pendientes.
- El modelo gratuito puede tardar o fallar; en ese caso la API responde 503 sin simular texto.
