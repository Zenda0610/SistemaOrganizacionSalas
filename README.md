# Gestión Operativa de Campuslands

## Problema

La programación de aulas, el préstamo de equipos y los reportes operativos necesitan
una fuente común que detecte conflictos y permita revisión humana. Este MVP integra
calendario, solicitudes por chat, aprobación, incidencias y préstamos con SQLite.

## Integrantes

- David Leonardo Martinez Perez
- Johan Alejandro Serrano Rivera
- Maria Jose CastroSanjuan
- Maria Gabriela Rincon Leon

[POR COMPLETAR: funciones individuales]. Nombres proporcionados por el equipo.
Se conservan las autorías existentes de Git, incluidas Zenda0610 y Claude.

## Stack

Python 3.11/3.12, FastAPI, Pydantic v2 y SQLite (`sqlite3`); HTML, CSS y JavaScript
sin frameworks. Pruebas: `unittest` y Node.js. Dependencias fijadas en `requirements.txt`.

## Arquitectura

```text
CSV ficticios → carga_datos → validación / rechazos / conflictos → SQLite
Navegador → main (FastAPI) → identidad + permisos del servidor
  Calendario ← sesiones + reservas + catálogo
  Chat → adaptador IA → JSON validado → borrador → confirmación → solicitud pendiente
  Coordinadora → aprobar → reglas + transacción → reserva en calendario
  Incidencia → persistir reporte → IA propone → revisión humana → bloqueo auditado
  Equipos → préstamo / devolución → transacción + historial
Bloqueos → excluyen nuevas asignaciones; conservan operaciones existentes afectadas
```

## Uso de IA en la aplicación

`app/ia.py` reutiliza APIs compatibles con OpenAI. OpenRouter está preparado con
`nvidia/nemotron-3.5-super-vl:free`; comprueba precio cero y no cambia a modelos de
pago. La IA interpreta el chat y propone categoría, prioridad, área y justificación
de incidencias con listas cerradas. **La IA propone y una persona decide**.
Una salida inválida no ejecuta acciones; la incidencia original queda pendiente.

La clave va solo en `IA_API_KEY=` del `.env` local de la raíz (ignorado por Git).
En esta instalación: `C:\Users\david\OneDrive\Desktop\Hackaton\SistemaOrganizacionSalas\.env`.
No se envía al navegador. Falta clave y autorización de organizadores: **inferencia
real no verificada**. Resultados y límites: [docs/validacion.md](docs/validacion.md).

## Uso de IA en el desarrollo

Codex ayudó a implementar backend y frontend, preparar datos ficticios y pruebas,
revisar resultados y comprobar la interfaz en navegador. Los mocks de pruebas no
se presentan como inferencia real. No se atribuyen aportes personales no confirmados.

## Reglas de negocio

| Regla | Archivo y función |
|---|---|
| Alias contra nombres cargados; ambigüedad pide aclaración | `app/chat.py: resolver_espacio` |
| Zona Franca, SER e inglés iguales; comercial después | `app/reglas.py: prioridad`; `app/solicitudes.py: aprobar_en` |
| Aula preferida de Zona Franca configurable (Sala Azul por defecto) | `app/config.py: AULA_PREFERIDA_ZONA_FRANCA`; `app/reglas.py: es_azul, ordenar_candidatos` |
| Aforo efectivo: porcentaje configurable, redondeo hacia abajo, máximo físico | `app/reglas.py: aforo_permitido`; `app/solicitudes.py: crear_en, aprobar_en, espacios_disponibles`; `app/chat.py: _confirmar` |
| Consulta 24/7; bloques de 15 min; reservas [inicio, fin), admiten medianoche | `app/solicitudes.py: validar_intervalo, buscar_conflictos, listar_reservas` |
| Devolución prevista fin-5; sigue bloqueando hasta fin | `app/reglas.py: hora_devolucion` |
| Confirmar crea pendiente; coordinadora aprueba, sin autoaprobación | `app/solicitudes.py: crear_en, aprobar_en`; `app/permisos.py: PERMISOS` |
| Borradores por usuario/conversación, versión y transacción; sin duplicar | `app/chat.py: _comprobar_version, _confirmar` |
| Prioridad de incidencia no implica bloqueo; solo coordinadora confirma | `app/operaciones.py: reportar, revisar`; `app/db.py: aula_bloqueada` |
| Un equipo no disponible no se presta; no hay doble préstamo ni doble devolución | `app/operaciones.py: prestar, devolver`; `app/db.py: índice prestamo_activo_equipo` |
| Hora ambigua se rechaza; solapamiento/aforo CSV se cargan y se señalan | `app/carga_datos.py: _validar_sesion, _detectar_conflictos` |

La identidad es de desarrollo, no autenticación real. No se verifican pagos.
La reubicación completa y la entrega/devolución física de aulas siguen pendientes.

## Instalación y ejecución

Desde la raíz, instalar con Python 3.11/3.12. Si ya existe `.venv`, reutilizarlo.

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

La demo utiliza `demo.sqlite`, separada de la base operativa. Repetir la carga no
duplica equipos, no reactiva los bloqueados y no borra préstamos. Datos ficticios:
9 aulas, 15 sesiones de la semana 12–18/10/2026, 3 cohortes y 8 equipos.
[Casos de calidad](data/ficticio/CASOS_BORDE.md): 1 rechazo y 2 conflictos.

## Demo

Abrir dos terminales **en la misma raíz**, sobre la misma base. Identidades diferentes
configuradas en el servidor; no se eligen roles desde el navegador.

Windows, terminal del profesor:

```powershell
$env:RUTA_BASE_DATOS = Join-Path (Get-Location) 'demo.sqlite'
$env:USUARIO_DESARROLLO = 'dev-profesor'
$env:ROL_DESARROLLO = 'profesor'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Windows, terminal de coordinadora:

```powershell
$env:RUTA_BASE_DATOS = Join-Path (Get-Location) 'demo.sqlite'
$env:USUARIO_DESARROLLO = 'dev-coordinadora'
$env:ROL_DESARROLLO = 'coordinadora'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Linux/macOS, terminal del profesor:

```bash
RUTA_BASE_DATOS="$PWD/demo.sqlite" USUARIO_DESARROLLO=dev-profesor ROL_DESARROLLO=profesor \
  .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Linux/macOS, terminal de coordinadora:

```bash
RUTA_BASE_DATOS="$PWD/demo.sqlite" USUARIO_DESARROLLO=dev-coordinadora ROL_DESARROLLO=coordinadora \
  .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Abrir http://127.0.0.1:8000 y http://127.0.0.1:8001 (no `file:///`). Tras editar
`.env` o `app/config.py`, detener ambos con Ctrl+C y ejecutar sus comandos otra vez.
Para enseñar ocupación, seleccionar 2026-10-16; para nuevas solicitudes, 2026-10-19.
La plantilla contiene el modelo gratuito y `IA_API_KEY=` vacía.

Pruebas: `python -m unittest discover -s tests -t .` y `node tests/test_interfaz.js`.
Con `.venv`, usar su intérprete como arriba. Node simula DOM/HTTP; no es navegador.
