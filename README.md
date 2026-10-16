# Sistema Central de Gestión Operativa de Campuslands

> El catálogo de demostración usa los **nombres y capacidades confirmados por operación**. Sus IDs y estados son de demostración; no representan una base oficial. No se inventan equipamiento ni ocupaciones. Las personas, grupos, clientes, cohortes y reservas usados en pruebas son ficticios y se aíslan de la demostración.

## Estado

- **Fase 1:** completa. Base del proyecto, carga validada de datos ficticios, API de lectura, interfaz mínima y conexión de prueba a la IA.
- **Fase 1, corrección de persistencia:** en revisión en la rama `fix/persistencia-carga`.
- **Identidad y permisos (provisional):** en la rama `feat/identidad-permisos`. Identidad de desarrollo y matriz de permisos por rol. No es autenticación.
- **Solicitudes de aulas (provisional):** en la rama `feat/solicitudes-aulas`. Disponibilidad, solicitud pendiente, aprobación validada y calendario de reservas. Sin pagos verificados.
- **Interfaz de solicitudes:** pestaña propia para consultar solicitudes y aprobar como coordinadora. Actualiza el calendario y las fechas disponibles, manteniendo la identidad de desarrollo configurada en el servidor.
- **Frontend de consulta:** Calendario y asistente juntos en escritorio, apilados en móvil; navegación Calendario · Solicitudes · Aulas · Datos. Consulta de cualquier fecha, historial de conversación y tarjetas de propuesta.
- **Prioridades y reubicación:** prioridad académica igual para Zona Franca, SER e inglés; comercial inferior. Reubicación específica de SER desde Azul para Zona Franca, propuesta y confirmada por coordinadora, con transacción y auditoría.
- **Incidencias y equipos mínimos:** reporte persistente, clasificación propuesta por IA o pendiente si falla, revisión humana y bloqueo de nuevas asignaciones; inventario, préstamo y devolución transaccionales. Interfaz en «Incidencias y equipos».
- **Pendiente:** usuarios oficiales, estructura y programación oficiales, inventario oficial, validación de inferencia real con clave, reubicación completa y registro de entrega/devolución física de aulas.

## Problema

La programación de salas vive en una hoja de cálculo que llevan dos personas. Una programa clases y reuniones, con prioridad para Zona Franca. La otra alquila las franjas que quedan libres. La hoja no detecta solapamientos ni excesos de aforo, y no deja trazabilidad de los cambios.

El sistema centraliza espacios, sesiones (clases, reuniones y alquileres), cohortes, préstamos mínimos de equipos e incidencias.

## Integrantes

- David Leonardo Martinez Perez
- Johan Alejandro Serrano Rivera
- Maria Jose CastroSanjuan
- Maria Gabriela Rincon Leon

Nombres proporcionados por el equipo para esta entrega. No se han confirmado funciones individuales. Se conserva la autoría histórica de Git (`Zenda0610`, `Claude`); esta lista no reasigna la autoría de los commits anteriores.

## Stack

- Python 3.11 o superior, FastAPI, SQLite (módulo `sqlite3`) y Pydantic v2.
- Frontend en HTML, CSS y JavaScript sin frameworks, servido por FastAPI.
- Pruebas con `unittest` de la biblioteca estándar. No requiere dependencias adicionales.

## Uso de IA

- **En la aplicación:** `app/ia.py` funciona con Ollama o una API compatible con OpenAI. El chat interpreta solicitudes; incidencias pide categoría, prioridad, área y justificación mediante JSON validado por el servidor. La IA no confirma bloqueos. Un fallo conserva la incidencia pendiente. OpenRouter está preparado con un modelo gratuito explícito; falta la clave para acreditar inferencia real.
- **En el desarrollo de esta entrega:** Codex se utilizó para implementar Python/JavaScript, preparar pruebas, revisar resultados y comprobar la interfaz en navegador. Los tests unitarios simulan inferencia y HTTP donde lo indican. No se atribuyen herramientas ni tareas personales a integrantes sin confirmación. El historial conserva también commits con autoría `Claude`; no se altera esa atribución.

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

### Reglas de prioridad vigentes

- Una reserva de aula no puede cruzarse con una sesión programada en esa aula. Los préstamos mínimos de equipos no tienen agenda futura: hay como máximo uno activo por equipo.
- Zona Franca, SER e inglés tienen igual prioridad general. Las solicitudes académicas se listan antes que las comerciales; no se aprueba una comercial si hay una académica pendiente que se solape en la misma aula. No se cancelan ni desplazan alquileres ya aprobados automáticamente.
- No se alquilan espacios en mantenimiento o inhabilitados.
- La preferencia de Azul para Zona Franca es específica y se reconoce por el nombre verificado del catálogo, nunca por un ID ficticio.

### Catálogo y fixtures

`data/ficticio/` es ahora la demostración limpia: nueve aulas (Auditorio 100, Cosmos 25, Skilab 20, Spooki 38, Apolo 34, Blanca 12, Azul 10, Amarillas verdes 6 y Artemis 32). **Amarillas verdes es una sola sala.** Sesiones y cohortes contienen solo encabezados; no hay horarios ni equipos inventados. Los IDs `DEMO-*` y el estado activo sirven exclusivamente para la demostración.

Los CSV antiguos con duplicados, aforo vacío, conflictos, personas y fechas ficticias se conservan íntegros en `tests/fixtures/defectuosos/`. Las pruebas históricas cargan ese directorio, no el catálogo de demostración. Una base existente no se borra ni se reasignan sus IDs al iniciar; la recarga incompatible con reservas se rechaza y conserva los datos anteriores.

Los inventarios son opcionales: la columna CSV `elementos` admite una lista JSON de nombres verificados y puede faltar (`null`: desconocido). Sesiones admiten `elementos_requeridos` como lista JSON. Las solicitudes aceptan esa misma lista por API/chat. Requerir un elemento con inventario desconocido se rechaza; no se presupone su existencia. Los nuevos campos se añaden al iniciar con una migración aditiva que conserva solicitudes y borradores anteriores.

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
| `gestionar_recursos` | coordinadora (inventario y revisión/bloqueo de incidencias) |
| `prestar_equipo` | profesor, administrativo, coordinadora (devolución sujeta a titularidad) |
| `recargar_datos` | coordinadora |

Pendiente de definir: qué lecturas requieren identidad y el esquema oficial de usuarios. La coordinadora no puede aprobar sus propias solicitudes.

## Solicitudes de aulas

**Estado: provisional.** Usa la identidad de desarrollo de la sección anterior.

- **Disponibilidad:** `GET /api/disponibilidad?inicio=AAAA-MM-DDTHH:MM&fin=AAAA-MM-DDTHH:MM` devuelve los espacios activos libres en ese intervalo. Acepta `personas` para filtrar por aforo.
- **Horario:** 24/7. Un intervalo puede cruzar medianoche. Los intervalos son semiabiertos: 08:00–09:00 y 09:00–10:00 son compatibles. Las horas deben caer en bloques de `MINUTOS_BLOQUE` minutos y van sin zona horaria (hora local del centro).
- **Crear:** `POST /api/solicitudes` con `espacio_id`, `inicio`, `fin`, `personas` y `descripcion`. El tipo lo decide el rol del servidor: profesor o administrativo genera una solicitud **académica**; estudiante o empresa, una **comercial**. Un cuerpo con `tipo`, `rol` o `solicitante_id` se rechaza con 422.
- **Solicitud comercial:** queda con `requiere_pago = true` y `estado_pago = "pendiente"`. El sistema no cobra ni verifica pagos. No hay tarifas definidas.
- **Aprobar:** `POST /api/solicitudes/{id}/aprobar`, solo para la coordinadora. La aprobación vuelve a validar, dentro de una transacción `BEGIN IMMEDIATE`, el estado del espacio, el aforo y los solapamientos con sesiones programadas y con reservas aprobadas. Dos aprobaciones simultáneas se ejecutan en serie. Nadie aprueba su propia solicitud.
- **Listar:** `GET /api/solicitudes`. La coordinadora ve todas; los demás roles, solo las suyas.
- **Interfaz:** la pestaña Solicitudes consulta ese listado y resuelve nombres desde el catálogo. Muestra horario, devolución, personas, motivo, estado y condición comercial; los pagos siguen sin verificarse. Solo la coordinadora ve Aprobar en solicitudes pendientes ajenas. El servidor mantiene la autorización y revalida aforo, estado y solapamientos.
- **Resultado de aprobación:** el botón se desactiva durante la petición. Solo una respuesta válida con el ID y estado aprobados confirma éxito. Ante un fallo de red o una respuesta no concluyente se informa resultado desconocido y se pide Actualizar solicitudes antes de repetir. Un error al refrescar después de una aprobación confirmada no se presenta como fallo de la aprobación.
- **Actualización:** el listado se actualiza al abrir la pestaña y después de enviar mensajes al chat. Aprobar refresca listado, calendario y selector de fechas, incorporando días nuevos aunque la grilla ya estuviera abierta. El calendario sigue siendo solo de lectura.
- **Devolución anticipada:** `hora_devolucion` se calcula desde `fin` restando `MINUTOS_DEVOLUCION_ANTICIPADA` (variable opcional, 5 por defecto). Se incluye en solicitudes y reservas, y se muestra en las tablas y el detalle del bloque. No es un registro de devolución física: la ocupación sigue siendo `[inicio, fin)`. Una reserva 06:00–08:00 informa devolución 07:55, bloquea hasta 08:00 y admite otra que empiece a 08:00.
- **Calendario (solo lectura):** `GET /api/reservas?fecha=AAAA-MM-DD` devuelve las reservas aprobadas que ocupan ese día, sin datos del solicitante. La grilla dibuja sesiones y reservas en 24 horas. Una reserva que cruza medianoche se recorta a cada día, y una de varios días aparece en todos los días que ocupa. Las sesiones canceladas no ocupan franjas. El campo de fecha admite también días sin ocupación, con Anterior, Hoy y Siguiente; un intervalo que termina exactamente a las 00:00 no ocupa el día siguiente. La tabla de reservas del día queda como detalle.
- **Recargar datos:** no borra las reservas aprobadas. La tabla `solicitudes` no tiene llave foránea hacia `espacios` por esa razón.
- **Recarga compatible con reservas:** antes de confirmar, la importación verifica cada reserva aprobada contra los datos entrantes: que el espacio exista y esté activo, que el aforo alcance y que no se cruce con una sesión programada. Si alguna falla, se rechaza toda la importación con `reserva_incompatible` (409) y la base queda como estaba. El sistema no cancela ni mueve reservas; la incompatibilidad se resuelve antes de importar.

**Pendiente de definir:**
- Flujo comercial completo (pago, tarifas, rechazo de solicitudes) y reubicaciones fuera del caso específico SER/Azul/Zona Franca.
- Registro de entrega o devolución física del aula; por ahora solo se calcula y muestra la hora prevista.

## Chat de solicitudes

**Estado: provisional. La inferencia real no está verificada:** no hay proveedor de IA configurado en el desarrollo actual. Las pruebas simulan la respuesta de la IA en el punto de llamada.

- `POST /api/chat` con `{"mensaje": "...", "conversacion_id": "..."}`. La IA extrae datos y propone una acción de una lista cerrada: `solicitar_aula`, `confirmar`, `cancelar`, `consultar_disponibilidad` o `ver_solicitudes`.
- **Borrador:** cada usuario tiene un borrador por conversación. Guarda fecha, horario, personas, motivo, aula y la propuesta vigente. Nunca se comparte entre usuarios ni entre conversaciones.
- **Aulas por nombre:** primero se comparan nombres e IDs exactos del catálogo cargado. Después se admiten equivalencias Skilab/Skylab, Spooki/Sputnik, Blanca/Sala Blanca y Azul/Sala Azul, únicamente si existe una entrada verificable por ese nombre. Amarillas verdes solo se resuelve contra su entrada real, nunca se asume que es un antiguo cubículo. Una coincidencia ambigua pide aclaración. La IA no elige IDs.
- **Sin aula elegida:** las candidatas se filtran por disponibilidad, aforo y elementos requeridos. Se ordenan por menor aforo e ID, dejando Azul al final salvo para Zona Franca. Se respeta un aula explícita válida. Si Azul está ocupada solo por SER futuro, el chat puede proponerla **condicionada a reubicación**; informa que no está libre y confirmar solo crea una solicitud pendiente. No mueve SER ni aprueba nada.
- **Actividad:** el prompt indica usar actividades como clase de SER, clase de inglés o reunión como motivo si no hay otro más específico. Zona Franca se reconoce por el parámetro booleano de la IA o por su mención en mensaje o descripción; se conserva en el borrador para las reevaluaciones. Esto solo orienta la selección y no cambia permisos.
- **Datos faltantes:** se pregunta lo que falta, sin inventar personas ni horas.
- **Confirmación:** crear exige confirmación explícita de la propuesta vigente. Antes de crear, el servidor vuelve a validar estado, aforo y solapamientos dentro de una transacción. Si el aula se ocupó, se propone otra y no se crea nada.
- **Concurrencia del borrador:** cada cambio guarda una versión interna en el JSON existente, sin migrar tablas. La confirmación comprueba estado y versión dentro de la misma transacción que crea la solicitud. Si cambió, devuelve `propuesta_modificada` y pide revisar la propuesta vigente; si se canceló, devuelve `cancelada`, sin crear. Los borradores anteriores sin versión siguen siendo compatibles.
- Las respuestas tardías de IA y las reevaluaciones tras un conflicto no pueden sobrescribir cambios posteriores ni reactivar un borrador cancelado. Esto también protege dos peticiones que comenzaron sin borrador.
- **Sin duplicados:** una segunda confirmación devuelve `ya_creada`. Las confirmaciones simultáneas crean una sola solicitud.
- La identidad y el rol salen del servidor. La aprobación no es una acción del chat: sigue siendo solo de la coordinadora, por la API.
- Si la IA no responde, el chat devuelve 503 `ia_no_disponible` y no cambia ningún borrador ni crea nada.
- La prueba de inferencia real (`PruebaInferenciaReal`) se omite mientras no haya proveedor configurado.

### Recorrido de desarrollo desde el navegador

1. Configurar un proveedor de IA autorizado y una identidad solicitante en el servidor (`USUARIO_DESARROLLO`, `ROL_DESARROLLO`). En Calendario, consultar la fecha y preguntar disponibilidad al asistente; después pedir un aula, revisar la propuesta y confirmarla explícitamente.
2. Consultar la solicitud pendiente en la pestaña Solicitudes.
3. Para probar el otro rol, detener el servidor y volver a iniciarlo con una identidad **distinta** de coordinadora, conservando la misma base. No hay selector de roles ni usuarios reales por sesión en esta etapa.
4. Abrir Solicitudes, aprobar y consultar la fecha de la reserva en Calendario. La devolución anticipada se muestra sin reducir el bloque reservado.

La identidad es global al proceso. Este recorrido aún requiere configurar y reiniciar el servidor para cambiar de persona; la autenticación oficial y los datos oficiales siguen pendientes. Sin proveedor configurado, el chat informa IA no disponible y no crea solicitudes.

### Uso del frontend

- **Calendario y asistente:** en escritorio se muestran lado a lado; hasta 950 px se apilan. El calendario tiene desplazamiento interno con encabezados y horas fijos, conserva 96 franjas de 15 minutos y no permite arrastrar ni crear desde las celdas.
- **Fechas libres:** se parte del día local del navegador y se puede elegir cualquier fecha. Con catálogo cargado y sin ocupaciones se muestra Día libre y todas las aulas. Sin catálogo se muestra Datos sin cargar. Un fallo de consulta se muestra como error y no como disponibilidad. Las respuestas atrasadas se descartan, incluso si son errores; una aprobación tardía conserva una fecha elegida después de iniciarla.
- **Conversación:** historial visible durante la vida de la pestaña, entrada multilínea y envío bloqueado mientras responde. Las propuestas muestran aula, fecha, horario, asistentes y actividad. Confirmar crea una **solicitud pendiente de aprobación**; solamente la aprobación de coordinadora genera una reserva. No se cambió el contrato del chat ni el control transaccional de versiones.
- **Respuesta incierta:** un fallo de red o de contrato puede ocurrir después de crear una solicitud. Se conserva el texto y se consulta `GET /api/solicitudes` antes de permitir otro envío. Si no se puede consultar, permanece bloqueado y aparece Consultar solicitudes antes de repetir. No se reenvía automáticamente. El listado muestra el estado real de las solicitudes autorizadas, pero no permite atribuir una solicitud a una conversación: el resultado del mensaje sigue indicado como desconocido. Cualquier reintento explícito usa el mismo `conversacion_id` de esa pestaña.
- **Navegación accesible:** las pestañas tienen nombre, panel asociado y selección ARIA; flechas izquierda/derecha y Home/End cambian sección y foco. Los controles tienen foco visible y los estados se anuncian. Cohortes y Calidad de datos se agrupan bajo Datos.
- El historial y la conversación no se recuperan al recargar la página. Siguen pendientes la identidad oficial, los datos oficiales y la validación con un proveedor de IA real autorizado.

### Reubicación autorizada por coordinadora

1. Una solicitud académica pendiente de Zona Franca pide Azul. Si SER es el único bloqueo, la coordinadora pulsa **Evaluar reubicación de SER** en Solicitudes. Se busca una alternativa para **todo el intervalo** de SER y se guarda la propuesta sin cambiar la ocupación.
2. Se muestran aula original y destino, horario y asistentes. Solo **Confirmar reubicación y aprobar Zona Franca** modifica los datos. Se admiten tanto una reserva de SER aprobada como una sesión SER programada.
3. Dentro de `BEGIN IMMEDIATE` se comprueban la solicitud y actividad originales contra la instantánea, horario futuro, disponibilidad, estado activo, aforo e inventario requerido de ambas actividades. Se mueve SER y se aprueba Zona Franca juntos, o se revierte todo. No se mueve una actividad que ya empezó; la confirmación vuelve a comprobar la hora.
4. La tabla `reubicaciones` conserva propuesta, origen, destino, instantáneas, coordinadora y hora de autorización. Confirmar el mismo ID otra vez devuelve la operación aplicada sin repetir el cambio. Una propuesta desactualizada requiere reevaluación; un destino ocupado o sin aforo/elementos impide confirmar. Sin alternativa, se conserva la reserva original y se informa el conflicto.

API solo para coordinadora: `POST /api/solicitudes/{id}/reubicacion/proponer`, `POST /api/reubicaciones/{id}/confirmar`, `GET /api/reubicaciones/{id}`. Ante una respuesta perdida, la interfaz pide consultar esa operación antes de repetir. No hay desplazamientos automáticos, cadenas de reubicación, ni desplazamiento de inglés, Zona Franca o comercial mediante esta excepción. La entrega/devolución física sigue pendiente.

### Pendientes después del recorrido de solicitudes

- **Prioridades adicionales:** no se han definido excepciones para desplazar otras actividades ya aprobadas, ni cancelaciones automáticas. Las actividades académicas mantienen igual prioridad general.
- **Reubicación general:** quedan fuera los cambios de horario, múltiples bloqueos, cadenas y otras actividades distintas del caso SER/Azul/Zona Franca.
- **Entrega/devolución:** definir responsables, estados, registro de horas reales y tratamiento de retrasos. Mostrar `fin - 5 minutos` es únicamente una hora prevista; no registra una entrega ni una devolución y no libera ocupación antes de `fin`.
- **Integración real:** obtener y validar catálogo/aforos y programación oficiales, implementar identidad oficial por usuario y configurar un proveedor de IA autorizado para probar mensajes variados. La identidad actual sigue siendo global al servidor y los datos de prueba son ficticios. No hay pago verificado, tarifas ni indicadores de ocupación inventados.

## OpenRouter: dónde colocar la clave

Se preparó `.env.example` y un `.env` local nuevo, sin sobrescribir archivos existentes. **Solo falta rellenar `IA_API_KEY`** en:

`C:\Users\david\OneDrive\Desktop\Hackaton\SistemaOrganizacionSalas\.env`

La clave va únicamente después de `IA_API_KEY=` en ese archivo. No se pega en el chat, en el navegador ni en comandos compartidos. `.env`, `.venv/` y bases locales están excluidos de Git. El backend utiliza la clave en Authorization; la API y el frontend no la devuelven y los errores del cliente de IA no registran credenciales.

Configuración preparada:

```dotenv
IA_PROVEEDOR=openai
IA_URL=https://openrouter.ai/api/v1
IA_MODELO=nvidia/nemotron-3.5-super-vl:free
IA_API_KEY=
IA_TIMEOUT_SEGUNDOS=60
```

Modelo seleccionado: [NVIDIA Nemotron 3.5 Super VL (free)](https://openrouter.ai/nvidia/nemotron-3.5-super-vl:free). Consulta del [catálogo oficial en vivo](https://openrouter.ai/api/v1/models) el 16 de octubre de 2026: precio de entrada y salida cero; no se encontró ningún DeepSeek `:free` en ese catálogo, aunque existen páginas de variantes anteriores. Se eligió Nemotron conforme a la alternativa autorizada. La gratuidad no garantiza disponibilidad ni ausencia de límites de uso.

El cliente conserva `/chat/completions`, exige `:free` para OpenRouter, comprueba que el ID siga disponible con precios cero antes de inferir y envía un límite de precio cero sin fallback. No cambia de modelo automáticamente; si lo retiran, deja un error en lugar de usar uno de pago. La salud solo verifica catálogo/configuración; no acredita inferencia ni validez de la clave.

El entorno `.venv` está preparado con Python 3.12.14 y las dependencias fijadas. Iniciar o reiniciar en PowerShell (detener primero con Ctrl+C):

```powershell
Set-Location 'C:\Users\david\OneDrive\Desktop\Hackaton\SistemaOrganizacionSalas'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

La identidad inicial de la plantilla es `dev-profesor`, rol `profesor`. Para probar el otro rol, detener el servidor y volver a iniciarlo en otra consola con `$env:USUARIO_DESARROLLO='dev-coordinadora'` y `$env:ROL_DESARROLLO='coordinadora'`, conservando la base. Son identidades de desarrollo, no autenticación. Al volver a profesor, quitar esas variables de proceso o cerrar esa consola; el `.env` conserva su identidad original.

En una base nueva, cargar explícitamente el catálogo de demostración una sola vez con `.\.venv\Scripts\python.exe -m app.carga_datos`. La carga no ocurre automáticamente al reiniciar.

Comprobar la configuración sin mostrar la clave:

```powershell
.\.venv\Scripts\python.exe -c "from app import config; print('Proveedor:',config.IA_PROVEEDOR); print('Modelo:',config.IA_MODELO); print('Clave configurada:',bool(config.IA_API_KEY))"
```

Después de rellenar la clave y reiniciar, ejecutar `.\.venv\Scripts\python.exe -m unittest tests.test_chat.PruebaInferenciaReal -v` para probar inferencia real y consultar `http://127.0.0.1:8000/api/ia/salud` para el catálogo. La prueba se omite si falta configuración. Hasta disponer de la clave no se afirma que el proveedor haya inferido mensajes ni se presenta un mock como respuesta real.

## Instalación

### MVP integrado: incidencias y préstamos mínimos

Esta entrega parte del commit local `f3cec6e` de `feat/solicitudes-aulas`, posterior al revisado `df55244`, y conserva sus cambios. No amplía la reubicación limitada existente; la reubicación completa continúa pendiente.

En **Incidencias y equipos**, cualquier identidad válida puede reportar texto sobre un aula o equipo seleccionado del catálogo. El servidor guarda el reporte antes de inferir y valida estrictamente categoría (`infraestructura`, `tecnologia`, `limpieza`, `seguridad`, `otra`), prioridad (`baja`, `media`, `alta`, `critica`), área (`mantenimiento`, `soporte`, `servicios_generales`, `coordinacion`) y justificación. Una salida inválida o proveedor no disponible deja `pendiente_clasificacion`; una salida válida queda `pendiente_revision`. Estos valores son una taxonomía inicial del MVP, pendiente de validación por operación.

Solo la **coordinadora** puede confirmar una revisión, corregir clasificación y elegir explícitamente bloquear o no. La prioridad no bloquea automáticamente. Se registran autora y fecha; una respuesta tardía de IA no reemplaza una decisión humana. Los bloqueos sobreviven a la recarga de CSV y excluyen el recurso de nuevas solicitudes, confirmaciones, aprobaciones, disponibilidad, alternativas de reubicación y préstamos según corresponda. Las reservas, sesiones y préstamos activos afectados siguen visibles y no se cancelan. La grilla señala las aulas bloqueadas. No hay desbloqueo automático ni interfaz de cierre: es una limitación explícita de este mínimo.

El inventario `equipos` comienza **vacío**, separado del catálogo de aulas. La coordinadora puede registrar identificador, nombre, estado y marca de equipo ficticio. Para demostrar, conservar marcada **Equipo ficticio de desarrollo**; no cargarlo como inventario oficial. Los equipos de las pruebas se crean exclusivamente en SQLite temporal, nunca en `data/ficticio` ni en un inventario oficial.

Profesores, administrativos y coordinadora pueden prestar; los demás roles no. Profesor/administrativo solo a su propio identificador; coordinadora puede registrar un responsable desde la API y el botón web presta a su nombre. El servidor registra responsable, fecha y operadora. SQLite serializa préstamo/devolución; un índice único impide dos préstamos activos del mismo equipo. Un equipo prestado, en mantenimiento, inhabilitado o bloqueado se rechaza. La devolución registra autora y hora, rechaza una segunda devolución y nunca levanta un bloqueo. La coordinadora ve todos los préstamos/incidencias; los demás solo los propios (el inventario no revela responsables). Se conservan los roles existentes y la identidad global de desarrollo; esto no implementa autenticación real.

API: `GET/POST /api/equipos`, `GET/POST /api/prestamos`, `POST /api/prestamos/{id}/devolver`, `GET/POST /api/incidencias`, `POST /api/incidencias/{id}/revisar`. Las escrituras se validan en servidor. Un fallo de red en la interfaz bloquea la repetición hasta consultar estado; no se reenvía automáticamente ni se afirma éxito sin contrato válido. Un reporte incierto puede haberse guardado: revisar el listado y el texto antes de volver a enviarlo.

La configuración existente `.env` se conserva y Git la ignora. Ruta absoluta de esta instalación: `C:\Users\david\OneDrive\Desktop\Hackaton\SistemaOrganizacionSalas\.env`. Pegar la clave solo tras `IA_API_KEY=` en ese archivo (sustituir `PEGA_AQUI_TU_CLAVE` si se copió la plantilla). La clave no se sirve al frontend. El 16/10/2026 se volvió a consultar el catálogo oficial: `nvidia/nemotron-3.5-super-vl:free` mantiene entrada/salida cero; no apareció DeepSeek gratuito. La comprobación de catálogo no acredita inferencia. La plantilla con marcador no se considera una clave configurada.

Para reiniciar: detener con Ctrl+C y ejecutar desde la raíz `.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`. Después de completar la clave, comprobar chat e incidencias reales con:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_chat.PruebaInferenciaReal tests.test_operaciones.PruebaProveedorIncidencias -v
```

Sin clave estos casos se omiten; no se consideran aprobados ni se reemplazan por mocks. El recorrido chat → confirmación → aprobación → calendario, los permisos, la concurrencia, préstamo/segundo préstamo/devolución y bloqueo con operaciones afectadas se comprueban localmente con SQLite real temporal e IA simulada. La devolución esperada de aulas cinco minutos antes sigue siendo informativa; el nuevo registro de devolución pertenece a **equipos**, no implementa entrega/devolución física de aulas. Quedan pendientes datos oficiales, funciones individuales del equipo, usuarios oficiales, clasificación con proveedor real y reubicación completa.

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

Validación del incremento de interfaz (Windows, Python 3.12.14, Node 24.17.0): 103 pruebas Python, 102 satisfactorias y una omitida por falta de proveedor; 46 comprobaciones de interfaz con DOM y HTTP simulados. Se conservaron los casos anteriores y se ajustaron dos expectativas: selección automática E07 por aforo y el nuevo campo público `hora_devolucion`. Se verifican permisos por API, rechazo sin cambiar el pendiente, calendario, fechas nuevas, duplicados, pago no verificado y respuesta perdida después de aprobar. La inferencia del chat en estas pruebas es simulada.

Comprobación adicional en navegador real con FastAPI y SQLite temporales: solicitud de prueba precargada, aprobación mediante el botón de coordinadora, estado aprobado, nombre y motivo visibles, nueva fecha en el selector y reserva 06:00–08:00 con devolución 07:55 en la grilla. No verifica interpretación de mensajes por un proveedor real: el entorno sigue sin IA configurada.

Validación de la mejora del frontend desde `453193c` (Windows, Python 3.12.14, Node 24.17.0): 103 pruebas Python, 102 satisfactorias y una omitida por falta de proveedor, incluidas confirmaciones concurrentes y cancelaciones del chat; 58 comprobaciones de interfaz con DOM/HTTP simulados. Se añaden fechas libres, estados sin catálogo/conexión, carreras de fecha (éxito y error), aprobación tardía, historial, tarjetas, doble envío, conservación de texto, consulta tras resultado desconocido y navegación por teclado. Sintaxis JavaScript y Pyflakes sin errores. El backend permanece sin modificaciones en esta entrega.

En navegador real se comprobaron el escritorio y un viewport móvil de 390 × 844, sin desbordamiento horizontal del documento, así como el desplazamiento interno, encabezados/horas sticky y las 96 franjas. Con datos ficticios y una base SQLite temporal se aprobó desde Solicitudes y se consultó la reserva; otra reserva 22:00–02:00 aparece recortada en ambos días. Se comprobaron fechas libres, navegación y agrupación de Datos mediante teclado. El chat real devolvió IA no disponible y conservó el mensaje multilínea en escritorio y móvil; las propuestas y la recuperación de respuestas perdidas se verificaron con mocks, sin simular que hubo inferencia real.

La comprobación posterior a `f2e5dce` conserva los commits locales existentes (el remoto revisado sigue en `7287d88`). La prueba integrada comienza consultando disponibilidad por chat con IA simulada, crea y confirma la solicitud, repite la confirmación sin duplicar, rechaza aprobación como profesor, aprueba como coordinadora y comprueba calendario y disponibilidad final. Los otros casos cubren propuesta modificada antes de confirmar, carreras de fecha y aprobación rechazada sin cambiar el pendiente. No acredita inferencia real ni operación con datos oficiales.

Reejecución de cierre: 103 pruebas Python (102 satisfactorias, una omitida por falta de proveedor) y 58 comprobaciones de interfaz con DOM/HTTP simulados; sintaxis JavaScript y Pyflakes sin errores. En navegador real, con otra base SQLite temporal, una aprobación con solapamiento mostró el error y siguió pendiente después de actualizar desde la API; una segunda solicitud sin conflicto se aprobó y apareció en el calendario 24/7 para su fecha nueva. Se conservaron las capturas de escritorio y móvil de la misma versión del frontend. El recorrido completo con mensajes interpretados por IA real permanece bloqueado por falta de configuración.

Validación del incremento de catálogo, OpenRouter y reubicación desde `df55244`: **127 pruebas Python, 126 satisfactorias y una de inferencia real omitida por falta de IA_API_KEY**, y **60 comprobaciones de interfaz con DOM/HTTP simulados**, todas satisfactorias. Sintaxis JavaScript, Pyflakes y comprobación del diff sin errores. Se verifican IDs ajenos al dataset, alias ambiguos, catálogo limpio, migración repetida sobre una base anterior, prioridad comercial inferior, transacción/rollback, doble confirmación concurrente, propuestas desactualizadas, actividad iniciada, ausencia de alternativas, aforo/equipamiento cambiados, sesiones SER y reservas nocturnas. Los tests de OpenRouter simulan HTTP y comprueban que no se infiere sin clave, con modelo retirado o de pago; no acreditan inferencia real.

En navegador real (escritorio y móvil 390 × 844), sobre SQLite temporal y datos de prueba aislados, se mostró el solicitante autorizado; la aprobación normal de Zona Franca en Azul falló por solapamiento; evaluar propuso Blanca para SER sin moverla; confirmar movió SER a Blanca y aprobó Zona Franca en Azul, registrando `dev-coordinadora` y la hora. Listado y calendario mostraron ambas reservas, sin desbordamiento horizontal del documento en móvil. Las ocupaciones se sembraron solo para esta prueba, no se añadieron al catálogo de demostración. El navegador informó la falta de IA_API_KEY: sigue pendiente ejecutar mensajes variados y el recorrido completo con Nemotron real después de que el usuario coloque su clave.

**Variables de entorno:** todas son opcionales. Están documentadas en `.env.example`. Los valores vacíos usan los valores por defecto de `app/config.py`.

Validación del MVP integrado del 16/10/2026 desde `f3cec6e`: **144 pruebas Python, 142 satisfactorias y dos de proveedor real omitidas por falta de clave**, y **65 comprobaciones de interfaz con DOM/HTTP simulados**, todas satisfactorias. Sintaxis de ambos scripts y Pyflakes sin errores. Las nuevas pruebas cubren permisos, recursos inexistentes, clasificación inválida, reporte persistido ante fallo, prioridad sin bloqueo automático, revisión humana frente a IA tardía, bloqueo con reservas/préstamos conservados, exclusión tras recargar CSV, chat/confirmación/aprobación/calendario, préstamo y devolución simultáneos y doble confirmación de revisión.

Navegador real con FastAPI y SQLite temporal: préstamo del equipo explícitamente ficticio, reporte conservado sin IA, bloqueo humano, devolución sin levantarlo; incidencia en Azul con reserva de prueba conservada, autora y fecha de revisión. HTTP real posterior rechazó otro préstamo con 409 `equipo_no_disponible`; el catálogo mostró Azul bloqueada y la reserva permaneció. Capturas de escritorio y móvil 390 × 844, documento sin desbordamiento horizontal (375 px). No hubo clasificación real ni interpretación de chat real: ambas esperan IA_API_KEY. No se incorporaron esos equipos/ocupaciones de pruebas al catálogo ni al repositorio.
</content>
