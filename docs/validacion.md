# Validación y pendientes

## Cierre de hackatón — 16 de octubre de 2026 (Colombia)

### Tarea 1: datos de demostración

Commit `ddfbf66`: carga ejecutada con `python -m scripts.cargar_demo` en `demo.sqlite`.
Resultado real: 9 aulas, 15 sesiones, 3 cohortes y 8 equipos ficticios; 1 rechazo por
hora `2` sin AM/PM y 2 conflictos (solapamiento y exceso de aforo).
Se comprobó Datos → Calidad de datos en navegador real con FastAPI y esa base.
146 pruebas Python ejecutadas: 144 satisfactorias y 2 omitidas por falta de IA;
65 comprobaciones de interfaz con DOM/HTTP simulados satisfactorias.

### Tarea 2: configuración y seguridad

Commit `edd856b`: `IA_API_KEY=` vacía en la plantilla; aula preferida configurable;
aforo efectivo configurable, redondeado hacia abajo y limitado a la capacidad física.
150 pruebas Python: 148 satisfactorias y 2 omitidas; 65 de interfaz satisfactorias.
Reejecución específica de configuración/reubicación: 20 satisfactorias.
Escaneo de los 25 commits accesibles con patrones OpenRouter/OpenAI/GitHub y claves
privadas: sin coincidencias. No hay `.env` ni bases versionadas. El escaneo por patrones
no acredita la ausencia de cualquier secreto de formato desconocido.

### Tarea 3: proveedor real — BLOQUEADA, no acreditada

Se leyó la configuración sin imprimir la clave: `Clave presente: False`.
Proveedor: `openai`; URL: `https://openrouter.ai/api/v1`;
modelo: `nvidia/nemotron-3.5-super-vl:free`.
El cliente informa: «Falta IA_API_KEY en el .env del servidor».

Se ejecutaron los dos casos optativos de proveedor real: ambos omitidos por falta
de configuración. No se enviaron reportes ni mensajes al proveedor y no existe una
respuesta real que reportar para disponibilidad, creación por chat o clasificación.
Los resultados con mocks no sustituyen esta comprobación.

La clave debe pegarse solo después de `IA_API_KEY=` en el `.env` local de la raíz
del proyecto. En esta instalación:
`C:\Users\david\OneDrive\Desktop\Hackaton\SistemaOrganizacionSalas\.env`.
No se modificó ese archivo. Reiniciar los servidores después de guardar.
OpenRouter sigue pendiente de autorización por los organizadores.


### Tarea 4: integración local a main

Merge `fb9fa8af2c09defbdd38bfe143e9c377c771710f` sin conflictos sobre
`origin/main` (`446401c`). Se conservó toda la historia y autoría.
En main: 150 pruebas Python ejecutadas, 148 satisfactorias y 2 omitidas;
65 comprobaciones de interfaz con DOM/HTTP simulados satisfactorias.
Sintaxis JavaScript y Pyflakes sin errores. No se publicó main.
Un primer intento de checkout con tracking falló por el refspec limitado del
checkout; se verificó el índice, se restauró el commit y se creó main sin tracking.
Las pruebas aquí reportadas corresponden a la integración recuperada y completa.

## Pendientes y límites actuales

- Falta clave y autorización de organizadores para verificar IA real. El acceso al
  catálogo gratuito no acredita inferencia ni autorización de la clave.
- Identidad global de desarrollo por proceso, sin autenticación oficial. Dos
  procesos con identidades distintas solo sirven para demostrar controles del servidor.
- Datos oficiales: estructura, programación, inventario y usuarios aún no recibidos.
  Todo horario, equipo, cohorte y persona de la demo es ficticio.
- La taxonomía de incidencias y los permisos de equipos requieren validación operativa.
  No hay cierre/desbloqueo de incidencias ni gestión completa de mantenimiento.
- Pago comercial no verificado, sin tarifas ni pasarela. Un alquiler cargado en
  sesiones es programación ficticia, no una solicitud cobrada.
- Reubicación completa pendiente. Se conserva solo la excepción anterior de SER
  desde el aula preferida para Zona Franca, explícita, transaccional y auditada.
- No hay registro físico de entrega/devolución de aulas. La hora prevista fin-5
  no libera el aula antes de fin. Sí se registra devolución de equipos.
- Separación entre reservas [inicio, fin): cero minutos. MINUTOS_BLOQUE es la
  granularidad de horarios, no un tiempo de separación entre reservas.
- El historial de chat no sobrevive a recargar la página. Una respuesta perdida
  obliga a consultar estado antes de repetir; no se reenvía automáticamente.
- La demo usa fechas fijas de la semana 12–18/10/2026. Para otra presentación,
  desplazar fechas explícitamente y volver a comprobar los tres casos de calidad.

## Registros históricos anteriores al cierre

Estas notas describen versiones anteriores; los conteos y los datos de demo
actuales son los del cierre arriba. No convierten pruebas con mocks en IA real.

Validación de la corrección de concurrencia del chat (Windows, Python 3.12.14): 92 pruebas Python, 91 satisfactorias y una omitida por falta de proveedor de IA; 36 comprobaciones de interfaz satisfactorias; sintaxis de `static/app.js` y `pyflakes app tests` sin errores. Las pruebas del chat simulan la IA. Los intercalados se controlan con eventos y barreras, sin esperas temporizadas para ordenar las operaciones: cubren confirmaciones antiguas tras cambiar personas u horario, cancelación en curso, confirmaciones simultáneas de la misma versión y respuestas tardías tras modificar o cancelar.

Validación del incremento de interfaz (Windows, Python 3.12.14, Node 24.17.0): 103 pruebas Python, 102 satisfactorias y una omitida por falta de proveedor; 46 comprobaciones de interfaz con DOM y HTTP simulados. Se conservaron los casos anteriores y se ajustaron dos expectativas: selección automática E07 por aforo y el nuevo campo público `hora_devolucion`. Se verifican permisos por API, rechazo sin cambiar el pendiente, calendario, fechas nuevas, duplicados, pago no verificado y respuesta perdida después de aprobar. La inferencia del chat en estas pruebas es simulada.

Comprobación adicional en navegador real con FastAPI y SQLite temporales: solicitud de prueba precargada, aprobación mediante el botón de coordinadora, estado aprobado, nombre y motivo visibles, nueva fecha en el selector y reserva 06:00–08:00 con devolución 07:55 en la grilla. No verifica interpretación de mensajes por un proveedor real: el entorno sigue sin IA configurada.

Validación de la mejora del frontend desde `453193c` (Windows, Python 3.12.14, Node 24.17.0): 103 pruebas Python, 102 satisfactorias y una omitida por falta de proveedor, incluidas confirmaciones concurrentes y cancelaciones del chat; 58 comprobaciones de interfaz con DOM/HTTP simulados. Se añaden fechas libres, estados sin catálogo/conexión, carreras de fecha (éxito y error), aprobación tardía, historial, tarjetas, doble envío, conservación de texto, consulta tras resultado desconocido y navegación por teclado. Sintaxis JavaScript y Pyflakes sin errores. El backend permanece sin modificaciones en esta entrega.

En navegador real se comprobaron el escritorio y un viewport móvil de 390 × 844, sin desbordamiento horizontal del documento, así como el desplazamiento interno, encabezados/horas sticky y las 96 franjas. Con datos ficticios y una base SQLite temporal se aprobó desde Solicitudes y se consultó la reserva; otra reserva 22:00–02:00 aparece recortada en ambos días. Se comprobaron fechas libres, navegación y agrupación de Datos mediante teclado. El chat real devolvió IA no disponible y conservó el mensaje multilínea en escritorio y móvil; las propuestas y la recuperación de respuestas perdidas se verificaron con mocks, sin simular que hubo inferencia real.

La comprobación posterior a `f2e5dce` conserva los commits locales existentes (el remoto revisado sigue en `7287d88`). La prueba integrada comienza consultando disponibilidad por chat con IA simulada, crea y confirma la solicitud, repite la confirmación sin duplicar, rechaza aprobación como profesor, aprueba como coordinadora y comprueba calendario y disponibilidad final. Los otros casos cubren propuesta modificada antes de confirmar, carreras de fecha y aprobación rechazada sin cambiar el pendiente. No acredita inferencia real ni operación con datos oficiales.

Reejecución de cierre: 103 pruebas Python (102 satisfactorias, una omitida por falta de proveedor) y 58 comprobaciones de interfaz con DOM/HTTP simulados; sintaxis JavaScript y Pyflakes sin errores. En navegador real, con otra base SQLite temporal, una aprobación con solapamiento mostró el error y siguió pendiente después de actualizar desde la API; una segunda solicitud sin conflicto se aprobó y apareció en el calendario 24/7 para su fecha nueva. Se conservaron las capturas de escritorio y móvil de la misma versión del frontend. El recorrido completo con mensajes interpretados por IA real permanece bloqueado por falta de configuración.

Validación del incremento de catálogo, OpenRouter y reubicación desde `df55244`: **127 pruebas Python, 126 satisfactorias y una de inferencia real omitida por falta de IA_API_KEY**, y **60 comprobaciones de interfaz con DOM/HTTP simulados**, todas satisfactorias. Sintaxis JavaScript, Pyflakes y comprobación del diff sin errores. Se verifican IDs ajenos al dataset, alias ambiguos, catálogo limpio, migración repetida sobre una base anterior, prioridad comercial inferior, transacción/rollback, doble confirmación concurrente, propuestas desactualizadas, actividad iniciada, ausencia de alternativas, aforo/equipamiento cambiados, sesiones SER y reservas nocturnas. Los tests de OpenRouter simulan HTTP y comprueban que no se infiere sin clave, con modelo retirado o de pago; no acreditan inferencia real.

En navegador real (escritorio y móvil 390 × 844), sobre SQLite temporal y datos de prueba aislados, se mostró el solicitante autorizado; la aprobación normal de Zona Franca en Azul falló por solapamiento; evaluar propuso Blanca para SER sin moverla; confirmar movió SER a Blanca y aprobó Zona Franca en Azul, registrando `dev-coordinadora` y la hora. Listado y calendario mostraron ambas reservas, sin desbordamiento horizontal del documento en móvil. Las ocupaciones se sembraron solo para esta prueba, no se añadieron al catálogo de demostración. El navegador informó la falta de IA_API_KEY: sigue pendiente ejecutar mensajes variados y el recorrido completo con Nemotron real después de que el usuario coloque su clave.


Validación del MVP integrado del 16/10/2026 desde `f3cec6e`: **144 pruebas Python, 142 satisfactorias y dos de proveedor real omitidas por falta de clave**, y **65 comprobaciones de interfaz con DOM/HTTP simulados**, todas satisfactorias. Sintaxis de ambos scripts y Pyflakes sin errores. Las nuevas pruebas cubren permisos, recursos inexistentes, clasificación inválida, reporte persistido ante fallo, prioridad sin bloqueo automático, revisión humana frente a IA tardía, bloqueo con reservas/préstamos conservados, exclusión tras recargar CSV, chat/confirmación/aprobación/calendario, préstamo y devolución simultáneos y doble confirmación de revisión.

Navegador real con FastAPI y SQLite temporal: préstamo del equipo explícitamente ficticio, reporte conservado sin IA, bloqueo humano, devolución sin levantarlo; incidencia en Azul con reserva de prueba conservada, autora y fecha de revisión. HTTP real posterior rechazó otro préstamo con 409 `equipo_no_disponible`; el catálogo mostró Azul bloqueada y la reserva permaneció. Capturas de escritorio y móvil 390 × 844, documento sin desbordamiento horizontal (375 px). No hubo clasificación real ni interpretación de chat real: ambas esperan IA_API_KEY. No se incorporaron esos equipos/ocupaciones de pruebas al catálogo ni al repositorio.
