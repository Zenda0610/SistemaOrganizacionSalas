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
