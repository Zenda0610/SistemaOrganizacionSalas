# Casos borde de los datos ficticios

Todos los datos son ficticios. Cada caso indica el archivo, el registro y el comportamiento esperado de la carga.

| # | Caso | Archivo | Registro | Comportamiento esperado |
|---|------|---------|----------|-------------------------|
| 1 | Dos sesiones solapadas en la misma sala | sesiones.csv | S01 y S02 (Sputnik, lunes) | Se cargan ambas; conflicto `solapamiento` |
| 2 | Alquiler encima de una clase de Zona Franca | sesiones.csv | S20 (clase ZF) y S21 (alquiler), Cosmos, miércoles | Se cargan; conflicto `solapamiento` y `alquiler_sobre_zona_franca` |
| 3 | Grupo con más personas que el aforo | sesiones.csv | S28 (8 personas en Cubículo Amarillo, aforo 6) | Se carga; conflicto `aforo_excedido` |
| 4 | Hora fin anterior a la hora inicio | sesiones.csv | S29 (15:00 a 14:00) | Se rechaza con motivo de orden de horas |
| 5 | Hora sin AM/PM | sesiones.csv | S31 (hora "1:00" a "3:00") | Se rechaza: no se adivina si es 01:00 o 13:00 |
| 6 | Sesión en una sala que no existe | sesiones.csv | S30 (espacio E99) | Se rechaza: el espacio no existe en espacios.csv |
| 7 | Cohorte con fecha fin vencida | cohortes.csv | Z6 Jun-26 (fecha fin 2026-09-30) | Se carga; conflicto `cohorte_vencida`; días restantes negativos |
| 8 | Estado escrito de forma distinta | sesiones.csv | S24 (estado "CANCELADO") | Se normaliza a `cancelada` y la corrección queda registrada |
| 9 | Id de espacio duplicado | espacios.csv | E04 Sputnik (segunda aparición, última fila) | Se rechaza la segunda aparición; la primera se conserva |

## Casos adicionales

- **Sala Nueva (E11)**: aforo vacío. Se rechaza porque un espacio sin aforo no puede programarse. Ninguna sesión la usa.
- **S36**: alquiler ya cancelado (`cancelada`). No genera conflictos porque las sesiones canceladas se excluyen.
- **S12 y S33**: grupos grandes (90 y 70 personas) que caben en el Auditorio (aforo 100). Son casos válidos de control.

## Resultado esperado de la carga

| Archivo | Cargados | Corregidos | Rechazados |
|---------|----------|------------|------------|
| espacios.csv | 10 | 0 | 2 (E11 y E04 duplicado) |
| sesiones.csv | 37 | 1 (S24) | 3 (S29, S30, S31) |
| cohortes.csv | 9 | 0 | 0 |

Conflictos: 5 (2 solapamientos, 1 alquiler sobre Zona Franca, 1 aforo excedido, 1 cohorte vencida).
