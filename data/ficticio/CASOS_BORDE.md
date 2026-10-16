# Demostración ficticia: semana del 12 al 18 de octubre de 2026

Personas, grupos, cohortes, equipos y horarios son inventados para la demostración.
Solo los nombres y capacidades de las nueve aulas fueron confirmados por operación.
Los fixtures extensos de regresión permanecen en `tests/fixtures/defectuosos`.

1. **Solapamiento:** DEMO-S12 y DEMO-S14 ocupan Skilab el 16/10 de 09:00 a 10:00. Ambas se cargan y se marca un conflicto.
2. **Aforo:** DEMO-S15 lleva 16 personas a Blanca (12). Se carga y se marca un conflicto de aforo; no se corrige inventando otra cantidad.
3. **Hora ambigua:** DEMO-S16 empieza a `2`, sin AM/PM. Se rechaza; no se adivina que signifique 02:00 o 14:00.

Resultado previsto: nueve aulas, 15 sesiones cargadas de 16 filas, tres cohortes,
una sesión rechazada y dos conflictos. Hay dos sesiones de Zona Franca y un alquiler
programado ficticio (no demuestra cobro ni pago verificado).

Desde la raíz ejecutar `python -m scripts.cargar_demo`. Usa `demo.sqlite`, separada de
la base operativa, e incorpora los ocho equipos de `equipos.csv`, todos ficticios;
uno en mantenimiento y otro inhabilitado. Repetir no duplica ni reactiva equipos.
La importación normal `python -m app.carga_datos` solo carga aulas, sesiones y cohortes.

Para ver los problemas: Calendario → 2026-10-16; Datos → Calidad de datos.
Para solicitudes nuevas de la demo usar un día libre posterior, por ejemplo 2026-10-19.
