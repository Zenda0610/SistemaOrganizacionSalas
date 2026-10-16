# Sistema Central de Gestión Operativa de Campuslands

> Todos los datos de este repositorio son **ficticios**. Los nombres de personas, grupos, clientes y cohortes fueron inventados para pruebas y no corresponden a registros reales.

## Estado

- **Fase 1:** completa. Base del proyecto, carga validada de datos ficticios, API de lectura, interfaz mínima y conexión de prueba a la IA.
- **Fase 1, corrección de persistencia:** en revisión en la rama `fix/persistencia-carga`.
- **Identidad y permisos (provisional):** en la rama `feat/identidad-permisos`. Identidad de desarrollo y matriz de permisos por rol. No es autenticación.
- **Solicitudes de aulas (provisional):** en la rama `feat/solicitudes-aulas`. Disponibilidad, solicitud pendiente, aprobación validada y calendario de reservas. Sin pagos verificados.
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
- Las horas de las sesiones deben caer en bloques de `MINUTOS_BLOQUE` minutos. No hay horario de apertura: la operación es 24/7.
- **Límite del esquema de sesiones:** cada sesión del CSV tiene hora de inicio y de fin dentro del mismo día. Una sesión que cruza medianoche (22:00–02:00) o que termina a las 24:00 se rechaza como fila inválida. Las reservas con fecha completa sí cruzan medianoche.
- Una importación reemplaza la carga anterior solo si los tres archivos obligatorios existen, se pueden leer y tienen las columnas requeridas. Si algo de eso falla, la base queda como estaba.
- Cada intento de importación queda registrado en la tabla `importaciones`, también cuando falla.
- `espacios.csv` sin filas válidas se rechaza (`catalogo_vacio`) y conserva los datos anteriores. Las sesiones y las cohortes vacías, en cambio, son válidas.
- Los detalles técnicos de un error (rutas, excepciones) solo van al log del servidor. La API responde con un mensaje general y un código.
- La interfaz distingue dos casos. Un código de error confirmado indica que la importación no se aplicó y que se conservaron los datos anteriores. Un fallo de red o una respuesta no interpretable significa que el resultado es desconocido: la interfaz pide consultar la última importación antes de repetirla.
Una respuesta 200 solo se muestra como importación correcta si cumple el contrato: `ok` es `true`, `cargados` es un objeto con conteos enteros no negativos y `conflictos` es un entero no negativo. Cualquier otra forma se trata como resultado desconocido.
- El arranque de la aplicación no importa datos. La importación es explícita.

### Reglas de negocio (fase 2, pendientes)

- Una reserva o préstamo no puede cruzarse con una sesión programada.
- Zona Franca tiene prioridad sobre los alquileres.
- No se alquilan espacios en mantenimiento o inhabilitados.
- Los umbrales se definirán como variables de entorno en `app/config.py`.

## Identidad y permisos

**Estado: provisional.** El esquema oficial de usuarios todavía no existe. Esta etapa no autentica a nadie.

- La identidad sale solo de la configuración del servidor: `USUARIO_DESARROLLO` y `ROL_DESARROLLO` en `.env`. Ningún dato de la petición (cuerpo, cabecera o query) puede cambiar el rol.
- Con las variables vacías no hay identidad: las acciones protegidas responden 401 (`sin_identidad`). Sin permiso, responden 403 (`sin_permiso`) y no se ejecutan.
- Quien tenga acceso al proceso o al `.env` puede cambiar la identidad. Por eso sirve solo para desarrollo local en `127.0.0.1`.
- `GET /api/sesion` muestra la identidad activa. La interfaz la marca como usuario de desarrollo.
- La carga por línea de comandos (`python -m app.carga_datos`) es una operación local y no pasa por la API ni por la verificación de roles.

Matriz de permisos (en `app/permisos.py`):

| Permiso | Roles |
|---|---|
| `solicitar_aula_academica` | profesor, administrativo (autorizado: provisional, por rol) |
| `solicitar_alquiler_comercial` | estudiante, empresa (sujeta a pago; sin tarifas ni pasarela en esta etapa) |
| `autorizar_solicitud` | coordinadora |
| `recargar_datos` | coordinadora |

Pendiente de definir: qué lecturas requieren identidad, y si la coordinadora puede autorizar sus propias solicitudes.

## Solicitudes de aulas

**Estado: provisional.** Usa la identidad de desarrollo de la sección anterior.

- **Disponibilidad:** `GET /api/disponibilidad?inicio=AAAA-MM-DDTHH:MM&fin=AAAA-MM-DDTHH:MM` devuelve los espacios activos libres en ese intervalo. Acepta `personas` para filtrar por aforo.
- **Horario:** 24/7. Un intervalo puede cruzar medianoche. Los intervalos son semiabiertos: 08:00–09:00 y 09:00–10:00 son compatibles. Las horas deben caer en bloques de `MINUTOS_BLOQUE` minutos y van sin zona horaria (hora local del centro).
- **Crear:** `POST /api/solicitudes` con `espacio_id`, `inicio`, `fin`, `personas` y `descripcion`. El tipo lo decide el rol del servidor: profesor o administrativo genera una solicitud **académica**; estudiante o empresa, una **comercial**. Un cuerpo con `tipo`, `rol` o `solicitante_id` se rechaza con 422.
- **Solicitud comercial:** queda con `requiere_pago = true` y `estado_pago = "pendiente"`. El sistema no cobra ni verifica pagos. No hay tarifas definidas.
- **Aprobar:** `POST /api/solicitudes/{id}/aprobar`, solo para la coordinadora. La aprobación vuelve a validar, dentro de una transacción `BEGIN IMMEDIATE`, el estado del espacio, el aforo y los solapamientos con sesiones programadas y con reservas aprobadas. Dos aprobaciones simultáneas se ejecutan en serie. Nadie aprueba su propia solicitud.
- **Listar:** `GET /api/solicitudes`. La coordinadora ve todas; los demás roles, solo las suyas.
- **Calendario (solo lectura):** `GET /api/reservas?fecha=AAAA-MM-DD` devuelve las reservas aprobadas que ocupan ese día, sin datos del solicitante. La grilla dibuja sesiones y reservas en 24 horas. Una reserva que cruza medianoche se recorta a cada día, y una de varios días aparece en todos los días que ocupa. Las sesiones canceladas no ocupan franjas. El selector de fechas incluye todos los días ocupados; un intervalo que termina exactamente a las 00:00 no ocupa el día siguiente. La tabla de reservas del día queda como detalle.
- **Recargar datos:** no borra las reservas aprobadas. La tabla `solicitudes` no tiene llave foránea hacia `espacios` por esa razón.
- **Recarga compatible con reservas:** antes de confirmar, la importación verifica cada reserva aprobada contra los datos entrantes: que el espacio exista y esté activo, que el aforo alcance y que no se cruce con una sesión programada. Si alguna falla, se rechaza toda la importación con `reserva_incompatible` (409) y la base queda como estaba. El sistema no cancela ni mueve reservas; la incompatibilidad se resuelve antes de importar.

**Pendiente de definir:**
- Reubicaciones, chat y flujo comercial completo (pago, tarifas, rechazo de solicitudes).
- Regla de devolución: la devolución se exige cinco minutos antes del final, pero el aula sigue reservada hasta la hora final. Esta etapa aplica solo la reserva hasta la hora final. La devolución no está implementada.

## Chat de solicitudes

**Estado: provisional. La inferencia real no está verificada:** no hay proveedor de IA configurado en el desarrollo actual. Las pruebas simulan la respuesta de la IA en el punto de llamada.

- `POST /api/chat` con `{"mensaje": "...", "conversacion_id": "..."}`. La IA extrae datos y propone una acción de una lista cerrada: `solicitar_aula`, `confirmar`, `cancelar`, `consultar_disponibilidad` o `ver_solicitudes`.
- **Borrador:** cada usuario tiene un borrador por conversación. Guarda fecha, horario, personas, motivo, aula y la propuesta vigente. Nunca se comparte entre usuarios ni entre conversaciones.
- **Aulas por nombre:** el servidor resuelve el nombre contra el catálogo. Un nombre ambiguo o inexistente pide aclarar; la IA nunca envía IDs.
- **Sin aula elegida:** el servidor busca la primera aula libre con el horario y el aforo, y la propone.
- **Datos faltantes:** se pregunta lo que falta, sin inventar personas ni horas.
- **Confirmación:** crear exige confirmación explícita de la propuesta vigente. Antes de crear, el servidor vuelve a validar estado, aforo y solapamientos dentro de una transacción. Si el aula se ocupó, se propone otra y no se crea nada.
- **Concurrencia del borrador:** cada cambio guarda una versión interna en el JSON existente, sin migrar tablas. La confirmación comprueba estado y versión dentro de la misma transacción que crea la solicitud. Si cambió, devuelve `propuesta_modificada` y pide revisar la propuesta vigente; si se canceló, devuelve `cancelada`, sin crear. Los borradores anteriores sin versión siguen siendo compatibles.
- Las respuestas tardías de IA y las reevaluaciones tras un conflicto no pueden sobrescribir cambios posteriores ni reactivar un borrador cancelado. Esto también protege dos peticiones que comenzaron sin borrador.
- **Sin duplicados:** una segunda confirmación devuelve `ya_creada`. Las confirmaciones simultáneas crean una sola solicitud.
- La identidad y el rol salen del servidor. La aprobación no es una acción del chat: sigue siendo solo de la coordinadora, por la API.
- Si la IA no responde, el chat devuelve 503 `ia_no_disponible` y no cambia ningún borrador ni crea nada.
- La prueba de inferencia real (`PruebaInferenciaReal`) se omite mientras no haya proveedor configurado.

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

Abre `http://127.0.0.1:8000`. El host `127.0.0.1` limita el acceso a este equipo, pero no reemplaza la verificación de permisos de la sección «Identidad y permisos».

**Pruebas:**

```bash
python -m unittest discover -s tests -t .
node tests/test_interfaz.js
```

`test_interfaz.js` requiere Node.js y no usa navegador: simula el DOM y las respuestas de `fetch`.

Validación de la corrección de concurrencia del chat (Windows, Python 3.12.14): 92 pruebas Python, 91 satisfactorias y una omitida por falta de proveedor de IA; 36 comprobaciones de interfaz satisfactorias; sintaxis de `static/app.js` y `pyflakes app tests` sin errores. Las pruebas del chat simulan la IA. Los intercalados se controlan con eventos y barreras, sin esperas temporizadas para ordenar las operaciones: cubren confirmaciones antiguas tras cambiar personas u horario, cancelación en curso, confirmaciones simultáneas de la misma versión y respuestas tardías tras modificar o cancelar.

**Variables de entorno:** todas son opcionales. Están documentadas en `.env.example`. Los valores vacíos usan los valores por defecto de `app/config.py`.
</content>
