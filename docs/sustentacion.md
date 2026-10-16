# Sustentación del MVP

## Antes de empezar

- Ejecutar `python -m scripts.cargar_demo` y levantar los dos procesos del README
  sobre el mismo `demo.sqlite`: profesor en 8000 y coordinadora en 8001.
- Comprobar `/api/sesion` en ambos: personas distintas, identidades de desarrollo.
  No es autenticación; el navegador no manda ni elige roles.
- Calendario: seleccionar 2026-10-16 para ver ocupación. Solicitud nueva: usar
  Blanca el 2026-10-19, 14:00–15:00, ocho personas, si sigue libre.
- Consultar `/api/ia/salud` y ejecutar los tests reales indicados en validacion.md
  tras configurar la clave. Salud de catálogo no demuestra inferencia.
  **Hoy falta IA_API_KEY: los pasos de interpretación/clasificación real siguen
  pendientes. Nunca presentar una respuesta simulada como salida del proveedor.**
- Confirmar con organizadores el permiso para usar OpenRouter. Probar antes del
  pitch; el modelo gratuito puede tardar o fallar. No cambiar a uno de pago.
- Tener preparadas las pestañas Datos, Solicitudes, Incidencias y equipos, y Swagger
  `http://127.0.0.1:8000/docs` para demostrar un rechazo directo de préstamo.
  Si se usan capturas, identificarlas como comprobaciones anteriores.

## Guion de tres minutos (ensayar con el proveedor antes de presentarlo)

| Tiempo | Acción y frase |
|---|---|
| 0:00–0:25 | Datos → Calidad: 15 sesiones cargadas, una hora ambigua rechazada y dos conflictos. «Conservamos el origen y explicamos lo que no se puede aceptar». |
| 0:25–1:10 | En profesor: «¿Qué aulas hay libres el 19 de octubre de 2026 de 14:00 a 15:00 para ocho personas?». Luego «Solicita Blanca para una clase de SER con esos datos». Revisar tarjeta y enviar «Confirmo». «Esto crea una solicitud pendiente, todavía no una reserva». |
| 1:10–1:30 | En coordinadora: actualizar Solicitudes, comprobar solicitante y aprobar. En profesor: seleccionar 2026-10-19 y ver reserva; devolución prevista 14:55, ocupación hasta 15:00. |
| 1:30–1:55 | Mostrar los tres controles: solapamiento rechaza una aprobación incompatible; petición con 13 personas no puede usar Blanca (12); aula bloqueada no admite nueva asignación. «Las reglas las ejecuta el servidor, no el modelo». Usar los casos preparados abajo para no gastar el tiempo en teclear. |
| 1:55–2:35 | Reportar «El proyector no enciende en Blanca» seleccionando el aula. Si hay inferencia real, revisar categoría/prioridad/área y justificación. La coordinadora elige explícitamente Confirmar bloqueo y confirma. Se conserva la reserva afectada. Volver a pedir Blanca: se rechaza esa aula o se propone otra disponible. «La IA propone y una persona decide». |
| 2:35–3:00 | Mostrar equipo disponible y préstamo; ejecutar el segundo préstamo preparado para ver 409, registrar devolución. O mostrar 409 para DEMO-EQ-05 en mantenimiento. «El bloqueo no cancela préstamos existentes; devolver no reactiva un equipo bloqueado». Cerrar con los límites reales. |

La latencia de tres llamadas de chat y una clasificación puede superar este guion.
Preparar el estado antes y ensayar; si tarda, explicar el estado de envío y continuar
con las reglas deterministas. Si falta clave o falla el modelo, enseñar el reporte
pendiente y revisión manual; **no afirmar que hubo clasificación real**.

### Preparación de los rechazos, sin inventar operaciones aprobadas

Preparar antes, en Swagger de profesor (8000), dos solicitudes reales para Blanca
el 2026-10-19, 14:00–15:00, ocho personas, con descripciones que indiquen prueba.
Después de aprobar una, aprobar la otra desde coordinadora debe dar solapamiento y
conservarla pendiente. No ejecutar esta preparación encima de una reserva previa
sin revisar el calendario. La petición de 13 personas se puede enviar al mismo
endpoint con otro horario: debe dar `aforo_excedido` (409).

En Swagger de profesor, `POST /api/prestamos`:

```json
{"equipo_id":"DEMO-EQ-05","responsable":"dev-profesor"}
```

Ese equipo está en mantenimiento: esperar 409 `equipo_no_disponible`. Para probar
doble préstamo, usar DEMO-EQ-01 disponible, prestarlo una vez y repetir el mismo
cuerpo: 409 `equipo_prestado`. Registrar su devolución desde la interfaz. Nunca
explicar falta de botón como prueba suficiente de autorización del servidor.

Para el caso de aula bloqueada, intentar una nueva solicitud directa en Swagger
contra el aula bloqueada: 409 `espacio_no_disponible`. El chat puede ofrecer una
alternativa; eso no significa que asignó el aula bloqueada. El listado de incidencias
de coordinadora conserva las reservas/préstamos afectados y la autora de revisión.

## Cuatro cambios probables del jurado

Líneas verificadas en esta entrega; localizar además por función porque una edición
previa desplaza números. Reiniciar **ambos** procesos después de editar. Las variables
de entorno y `.env` prevalecen sobre el valor por defecto de config.py: si están
definidas, cambiar ese valor o vaciarlo para que se aplique el defecto editado.
Hacer un cambio por vez y ejecutar su comprobación. Las propuestas de los puntos
2 y 4 **no están implementadas** y no forman parte de la configuración actual.

1. **Aforo al 80 %.** `app/config.py:31`, cambiar el último argumento de
   `PORCENTAJE_AFORO_MAXIMO = _entero("PORCENTAJE_AFORO_MAXIMO", 100)` de `100` a `80`.
   Equivalente en `.env`: `PORCENTAJE_AFORO_MAXIMO=80`. Blanca pasa de 12 a 9 personas
   permitidas (redondeo hacia abajo): nueve se admiten y diez se rechazan. El catálogo
   conserva el aforo físico. Probar con `tests.test_configuracion_demo` y por API.

2. **Cinco minutos entre reservas.** Hoy el margen es cero. `MINUTOS_BLOQUE` cambia
   granularidad; `MINUTOS_DEVOLUCION_ANTICIPADA` solo cambia la devolución prevista.
   Ninguno crea separación. Si lo piden, en `app/solicitudes.py:87`, inmediatamente
   después del docstring de `buscar_conflictos`, insertar estas dos líneas:

   ```python
   inicio = _texto(datetime.strptime(inicio, FORMATO) - timedelta(minutes=5))
   fin = _texto(datetime.strptime(fin, FORMATO) + timedelta(minutes=5))
   ```

   Así la búsqueda de conflictos reserva un margen a ambos lados sin alterar las
   horas guardadas. Ya están importados datetime y timedelta. Probar fin 08:00:
   inicio 08:00 se rechaza, 08:05 se admite; repetir al cruzar medianoche, con
   sesiones y con reservas. Añadir esas expectativas antes de entregar el cambio;
   los tests actuales de reservas consecutivas deben cambiar deliberadamente.

3. **Otra aula preferida para Zona Franca.** `app/config.py:32`, cambiar el defecto
   `"Sala Azul"` por `"Cosmos"` en `AULA_PREFERIDA_ZONA_FRANCA`, o poner
   `AULA_PREFERIDA_ZONA_FRANCA=Cosmos` en `.env`. `app/reglas.py:20` (`es_azul`, nombre
   histórico) reconoce el nombre configurado y sus alias, sin ID fijo. No cambia
   el catálogo ni mueve reservas. Verificar preferencia y aforo con otro ID;
   mantener la confirmación humana de cualquier reubicación. Si hay duplicidad
   de nombres, el chat pide aclaración en lugar de inventar un ID.

4. **Qué prioridad impide aprobar una comercial.** Actualmente toda académica
   pendiente solapada tiene prioridad sobre una comercial. `app/solicitudes.py:181`,
   dentro de `aprobar_en`, contiene:

   ```python
   "SELECT id FROM solicitudes WHERE estado = 'pendiente' AND tipo = 'academica' "
   ```

   Solo si el jurado pide que bloquee exclusivamente Zona Franca, sustituir por:

   ```python
   "SELECT id FROM solicitudes WHERE estado = 'pendiente' AND tipo = 'academica' AND actividad = 'zona_franca' "
   ```

   Probar comercial contra pendiente de Zona Franca (rechaza) y contra SER/inglés
   (ya no bloquean por esta condición). Esto cambia el acuerdo actual: no hacerlo
   por iniciativa propia. La prioridad de presentación sigue en
   `app/reglas.py:43` (`prioridad`); si se pide cambiar el orden, ajustar también
   esa función y sus tests. **No convertir una prioridad de incidencia en bloqueo
   automático:** la decisión humana sigue en `app/operaciones.py:169` (`revisar`).

## Qué hace cada archivo de app/

- **`__init__.py`**: identifica el paquete Python de la aplicación.
  No levanta el servidor ni hace llamadas a IA por sí solo.
- **`config.py`**: lee variables de entorno y `.env`, con valores por defecto.
  Centraliza rutas, modelo, identidad de desarrollo y parámetros de aforo/horarios.
- **`db.py`**: abre SQLite, crea tablas y aplica ampliaciones compatibles.
  Las transacciones serializan escrituras y el índice evita dos préstamos activos.
- **`modelos.py`**: valida las filas de aulas, sesiones y cohortes con Pydantic.
  Comprueba tipos, fechas, horas y valores permitidos; no aprueba solicitudes.
- **`carga_datos.py`**: importa CSV con origen y motivo de rechazo por fila.
  Detecta conflictos y protege reservas aprobadas ante una recarga incompatible.
- **`identidad.py`**: obtiene usuario y rol exclusivamente del servidor.
  Es un adaptador de desarrollo, no una implementación de autenticación real.
- **`permisos.py`**: mantiene la matriz de acciones permitidas por rol.
  Niega permisos desconocidos; el cuerpo enviado por el navegador no cambia el rol.
- **`reglas.py`**: reúne alias, prioridad, orden por aforo y aula preferida.
  Calcula aforo permitido y devolución prevista sin modificar la ocupación guardada.
- **`solicitudes.py`**: consulta disponibilidad, crea pendientes y aprueba con reglas.
  Revalida aforo, bloqueos y cruces dentro de la transacción antes de aprobar.
- **`chat.py`**: convierte el JSON de IA en acciones permitidas y tarjetas de propuesta.
  Conserva borradores por conversación y comprueba versión antes de confirmar o cancelar.
- **`ia.py`**: llama al proveedor compatible con OpenAI u Ollama y comunica fallos.
  En OpenRouter exige modelo gratuito explícito y no usa fallback de pago.
- **`operaciones.py`**: guarda incidencias antes de inferir y valida la clasificación.
  Gestiona revisión/bloqueo humano, operaciones afectadas, equipos, préstamos y devolución.
- **`reubicaciones.py`**: conserva la excepción limitada de SER para Zona Franca.
  Proponer no mueve; confirmar revalida y cambia todo o nada con autora y fecha.
- **`main.py`**: expone FastAPI, dependencias de identidad y respuestas de errores.
  Sirve también el frontend; las rutas llaman a los servicios de dominio.

## Cómo cerrar la defensa

«Los tres módulos comparten SQLite y reglas del servidor. La IA ayuda a interpretar
y clasificar; las decisiones operativas sensibles son humanas y quedan registradas».
Identificar qué se ejecutó en vivo, qué proviene de tests con mocks y qué queda
pendiente de proveedor y datos oficiales. No presentar reubicación completa,
autenticación oficial, pagos ni devolución física de aulas como terminados.
