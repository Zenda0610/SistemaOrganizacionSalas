// Interfaz mínima: consume la API y muestra estados de carga, vacío y error.
const API = "/api";
const HORA_APERTURA = 0;   // vista 24/7
const HORA_CIERRE = 24;    // vista 24/7 (24 = medianoche del día siguiente)
const PASO_MINUTOS = 15;   // debe coincidir con MINUTOS_BLOQUE
const NOMBRES_AREA = { software: "Software", ingles: "Inglés", ser: "SER", otra: "Otra" };

const cargadores = {
  operaciones: () => cargarOperaciones(),
  grilla: cargarGrilla,
  espacios: cargarEspacios,
  cohortes: cargarCohortes,
  calidad: cargarCalidad,
  chat: async () => {},
  solicitudes: cargarSolicitudes,
  datos: async () => {
    await Promise.all([
      cargarCohortes().catch((e) => mostrarEstado("cohortes", "error", e.message)),
      cargarCalidad().catch((e) => mostrarEstado("calidad", "error", e.message)),
    ]);
  },
};
const cargadosPorPestana = new Set();
let nombresAulas = {};

// --- Utilidades -----------------------------------------------------------------

// Códigos que el servidor devuelve solo cuando la importación no se aplicó.
const CODIGOS_IMPORTACION_NO_APLICADA = new Set([
  "archivo_ausente", "archivo_no_legible", "estructura_incompatible",
  "catalogo_vacio", "error_escritura", "error_interno", "sin_identidad", "sin_permiso", "reserva_incompatible",
]);

function errorResultadoDesconocido(mensaje) {
  const error = new Error(mensaje);
  error.resultadoDesconocido = true;
  return error;
}

async function pedir(ruta, opciones = {}) {
  let respuesta;
  try {
    respuesta = await fetch(API + ruta, opciones);
  } catch {
    throw errorResultadoDesconocido("No se pudo conectar con el servidor.");
  }
  let datos = null;
  try {
    datos = await respuesta.json();
  } catch {
    datos = null;
  }
  if (!respuesta.ok) {
    const error = new Error((datos && datos.mensaje) || `Error ${respuesta.status} al consultar la API.`);
    error.codigo = datos && datos.codigo;
    // Solo un código conocido demuestra que el servidor decidió no aplicar la importación.
    error.resultadoDesconocido = !CODIGOS_IMPORTACION_NO_APLICADA.has(error.codigo);
    throw error;
  }
  if (datos === null) throw errorResultadoDesconocido("El servidor respondió con un formato no reconocido.");
  return datos;
}

function mostrarEstado(panelId, tipo, texto) {
  const parrafo = document.querySelector(`#${panelId} .estado`);
  parrafo.className = `estado estado-${tipo}`;
  parrafo.textContent = texto;
}

function crearElemento(etiqueta, clase, texto) {
  const elemento = document.createElement(etiqueta);
  if (clase) elemento.className = clase;
  if (texto !== undefined && texto !== null) elemento.textContent = texto;
  return elemento;
}

function crearTabla(columnas, filas) {
  const tabla = crearElemento("table", "datos");
  const cabecera = crearElemento("tr");
  columnas.forEach((col) => cabecera.appendChild(crearElemento("th", "", col.titulo)));
  tabla.appendChild(crearElemento("thead")).appendChild(cabecera);
  const cuerpo = tabla.appendChild(crearElemento("tbody"));
  filas.forEach((fila) => {
    const tr = crearElemento("tr");
    columnas.forEach((col) => {
      const td = crearElemento("td", col.clase ? col.clase(fila) : "");
      td.textContent = col.valor(fila) ?? "";
      tr.appendChild(td);
    });
    cuerpo.appendChild(tr);
  });
  return tabla;
}

function pintarContenido(panelId, nodo) {
  const contenedor = document.querySelector(`#${panelId} .contenido`);
  contenedor.replaceChildren(nodo);
}

function minutosDesdeHora(hora) {
  const [h, m] = hora.split(":").map(Number);
  return h * 60 + m;
}

function horaDesdeMinutos(minutos) {
  const h = String(Math.floor(minutos / 60)).padStart(2, "0");
  const m = String(minutos % 60).padStart(2, "0");
  return `${h}:${m}`;
}

// --- Pestañas -------------------------------------------------------------------

function activarPestana(nombre) {
  document.querySelectorAll(".pestana").forEach((b) => {
    const activa = b.dataset.pestana === nombre;
    b.classList.toggle("activa", activa);
    b.setAttribute("aria-selected", String(activa));
    b.tabIndex = activa ? 0 : -1;
  });
  document.querySelectorAll(".panel").forEach((p) => {
    p.classList.toggle("activo", p.id === nombre);
    p.hidden = p.id !== nombre;
  });
  if (!cargadosPorPestana.has(nombre) || nombre === "grilla" || nombre === "solicitudes" || nombre === "operaciones" || nombre === "comercial") {
    cargadores[nombre]().catch((error) => mostrarEstado(nombre, "error", error.message));
    cargadosPorPestana.add(nombre);
  }
}

// --- Grilla semanal (por día) ---------------------------------------------------

function fechaLocalHoy() {
  const hoy = new Date();
  return `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}-${String(hoy.getDate()).padStart(2, "0")}`;
}

async function cargarGrilla(fechaPreferida) {
  const selector = document.getElementById("selector-fecha");
  return cargarDia(fechaPreferida || selector.value || fechaLocalHoy());
}

let numeroCargaDia = 0;

async function cargarDia(fecha) {
  const carga = ++numeroCargaDia;
  const selector = document.getElementById("selector-fecha");
  selector.value = fecha;
  document.getElementById("tabla-grilla").replaceChildren();
  document.getElementById("reservas-aprobadas").replaceChildren();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(fecha)) {
    mostrarEstado("grilla", "vacio", "Elige una fecha válida para consultar.");
    return false;
  }
  mostrarEstado("grilla", "cargando", `Consultando ${fecha}…`);
  try {
    const [espacios, sesiones, reservas] = await Promise.all([
      pedir("/espacios"), pedir(`/sesiones?fecha=${fecha}`), pedir(`/reservas?fecha=${fecha}`),
    ]);
    if (carga !== numeroCargaDia || selector.value !== fecha) return false;
    if (!espacios.length) {
      mostrarEstado("grilla", "vacio", "Datos sin cargar: importa el catálogo desde Datos → Calidad de datos.");
      return false;
    }
    nombresAulas = Object.fromEntries(espacios.map((e) => [e.id, e.nombre]));
    construirGrilla(espacios, sesiones, reservas, fecha);
    pintarReservas(espacios, reservas);
    pintarLeyenda();
    const ocupado = sesiones.some((s) => s.estado !== "cancelada") || reservas.length;
    mostrarEstado("grilla", "ok", ocupado ? `Ocupación del ${fecha}.` : `Día libre · ${fecha}. No hay ocupaciones registradas.`);
    return true;
  } catch (error) {
    if (carga !== numeroCargaDia || selector.value !== fecha) return false;
    mostrarEstado("grilla", "error", `No se pudo consultar ${fecha}. ${error.message}`);
    return false;
  }
}

const MINUTOS_DIA = 24 * 60;

function diaVecino(fecha, desplazamiento) {
  const dia = new Date(`${fecha}T00:00:00Z`);
  dia.setUTCDate(dia.getUTCDate() + desplazamiento);
  return dia.toISOString().slice(0, 10);
}

// Días que ocupa una reserva, todos incluidos. Una reserva que termina exactamente a las 00:00
// no ocupa el día siguiente.
function fechasDeReserva(reserva) {
  const primero = reserva.inicio.slice(0, 10);
  const ultimo = reserva.fin.endsWith(" 00:00") ? diaVecino(reserva.fin.slice(0, 10), -1) : reserva.fin.slice(0, 10);
  const fechas = [];
  for (let dia = primero; dia <= ultimo; dia = diaVecino(dia, 1)) fechas.push(dia);
  return fechas;
}

// Franjas que ocupan, dentro de un día, las sesiones no canceladas y las reservas aprobadas.
// Minutos desde 00:00. Una reserva que cruza medianoche se recorta a cada día: 00:00–24:00 en el
// día intermedio y así sucesivamente. Las sesiones canceladas no ocupan franjas.
function bloquesDelDia(fecha, sesiones, reservas) {
  const bloques = [];
  sesiones.filter((s) => s.estado !== "cancelada").forEach((s) => bloques.push({
    espacioId: s.espacio_id,
    inicio: minutosDesdeHora(s.hora_inicio),
    fin: minutosDesdeHora(s.hora_fin),
    reserva: false,
    datos: s,
  }));
  reservas.forEach((r) => {
    const diaInicio = r.inicio.slice(0, 10);
    const diaFin = r.fin.slice(0, 10);
    if (diaInicio > fecha || diaFin < fecha) return;
    const inicio = diaInicio < fecha ? 0 : minutosDesdeHora(r.inicio.slice(11));
    const fin = diaFin > fecha ? MINUTOS_DIA : minutosDesdeHora(r.fin.slice(11));
    if (fin > inicio) bloques.push({ espacioId: r.espacio_id, inicio, fin, reserva: true, datos: r });
  });
  bloques.forEach((a) => {
    a.enConflicto = bloques.some((b) => b !== a && b.espacioId === a.espacioId && b.inicio < a.fin && a.inicio < b.fin);
  });
  return bloques;
}

function construirGrilla(espacios, sesiones, reservas, fecha) {
  const tabla = document.getElementById("tabla-grilla");
  const bloques = bloquesDelDia(fecha, sesiones, reservas);

  const cabecera = crearElemento("tr");
  cabecera.appendChild(crearElemento("th", "hora", "Hora"));
  espacios.forEach((e) => cabecera.appendChild(crearElemento("th", "", `${e.nombre} (${e.aforo})${e.bloqueada ? ' · Bloqueada' : ''}`)));
  tabla.replaceChildren(crearElemento("thead"));
  tabla.querySelector("thead").appendChild(cabecera);

  const cuerpo = crearElemento("tbody");
  const celdas = new Map();
  for (let t = HORA_APERTURA * 60; t < HORA_CIERRE * 60; t += PASO_MINUTOS) {
    const fila = crearElemento("tr");
    fila.appendChild(crearElemento("td", "hora", t % 60 === 0 ? horaDesdeMinutos(t) : ""));
    espacios.forEach((e) => {
      const celda = crearElemento("td", "celda");
      celda.setAttribute("data-espacio", e.id);
      celda.setAttribute("data-minuto", String(t));
      celdas.set(`${e.id}|${t}`, celda);
      bloques.filter((b) => b.espacioId === e.id && b.inicio === t)  // el bloque se dibuja en su primera franja
        .forEach((b) => celda.appendChild(crearBloque(b)));
      fila.appendChild(celda);
    });
    cuerpo.appendChild(fila);
  }
  tabla.appendChild(cuerpo);
  // Selección por bloques (static/seleccion.js), si está cargada.
  if (typeof prepararSeleccion === "function") prepararSeleccion(espacios, bloques, fecha, celdas);
}

function crearBloque(bloque) {
  const altura = ((bloque.fin - bloque.inicio) / PASO_MINUTOS) * 22 - 2;  // 22 px es la altura de una franja (styles.css)
  if (bloque.reserva) {
    const r = bloque.datos;
    const clases = ["bloque", "reserva", r.tipo === "comercial" ? "comercial" : "academica"];
    if (bloque.enConflicto) clases.push("conflicto");
    const elemento = crearElemento("div", clases.join(" "), "Reserva aprobada");
    elemento.title = `Reserva aprobada · ${r.inicio} → ${r.fin} · Devolución: ${r.hora_devolucion || ""}`;
    elemento.style.height = `${altura}px`;
    return elemento;
  }
  const s = bloque.datos;
  const clases = ["bloque", `area-${s.area}`];
  if (s.es_zona_franca) clases.push("zona-franca");
  if (s.tipo === "alquiler") clases.push("alquiler");
  if (bloque.enConflicto) clases.push("conflicto");
  const elemento = crearElemento("div", clases.join(" "), `${s.grupo} · ${s.responsable}`);
  elemento.title = `${s.id} · ${s.tipo} · ${s.grupo} · ${s.responsable} · ${s.hora_inicio}-${s.hora_fin}`;
  elemento.style.height = `${altura}px`;
  return elemento;
}

function pintarReservas(espacios, reservas) {
  const contenedor = document.getElementById("reservas-aprobadas");
  if (!reservas.length) {
    contenedor.replaceChildren(crearElemento("p", "estado", "No hay reservas aprobadas para este día."));
    return;
  }
  const nombres = Object.fromEntries(espacios.map((e) => [e.id, e.nombre]));
  contenedor.replaceChildren(crearTabla([
    { titulo: "Espacio", valor: (r) => nombres[r.espacio_id] || r.espacio_id },
    { titulo: "Desde", valor: (r) => r.inicio },
    { titulo: "Hasta", valor: (r) => r.fin },
    { titulo: "Devolución (-5 min por defecto)", valor: (r) => r.hora_devolucion },
    { titulo: "Tipo", valor: (r) => (r.tipo === "comercial" ? "Comercial (pago no verificado por el sistema)" : "Académica") },
  ], reservas));
}

function pintarLeyenda() {
  const leyenda = document.getElementById("leyenda");
  leyenda.replaceChildren(
    ...Object.entries(NOMBRES_AREA).map(([clave, nombre]) => crearElemento("span", `area-${clave}`, nombre)),
    crearElemento("span", "zona-franca", "Zona Franca"),
    crearElemento("span", "alquiler", "Alquiler"),
    crearElemento("span", "cancelada", "Cancelada"),
  );
}

// --- Espacios -------------------------------------------------------------------

function textoTarifaAula(tarifa) {
  return tarifa === null || tarifa === undefined ? "Por definir" : `$${Math.round(tarifa).toLocaleString("es-CO")} COP`;
}

async function cargarEspacios() {
  mostrarEstado("espacios", "cargando", "Cargando espacios…");
  const [espacios, sesion] = await Promise.all([pedir("/espacios"), pedir("/sesion").catch(() => ({}))]);
  if (!espacios.length) {
    pintarContenido("espacios", crearElemento("div"));
    mostrarEstado("espacios", "vacio", "No hay espacios cargados.");
    return;
  }
  const tabla = crearTabla([
    { titulo: "ID", valor: (e) => e.id },
    { titulo: "Nombre", valor: (e) => e.nombre },
    { titulo: "Tipo", valor: (e) => e.tipo },
    { titulo: "Aforo", valor: (e) => e.aforo },
    { titulo: "Estado", valor: (e) => e.estado },
    { titulo: "Tarifa por hora", valor: (e) => textoTarifaAula(e.tarifa_hora) },
  ], espacios);
  // Solo la coordinadora edita; el servidor vuelve a verificar el permiso gestionar_tarifas.
  if (sesion.rol === "coordinadora") {
    tabla.querySelector("thead").querySelector("tr").appendChild(crearElemento("th", "", "Acción"));
    const filas = tabla.querySelector("tbody").children;
    espacios.forEach((espacio, indice) => {
      const celda = crearElemento("td");
      const boton = crearElemento("button", "", "Editar tarifa");
      boton.type = "button";
      boton.addEventListener("click", () => editarTarifa(espacio, filas[indice].children[5], celda));
      celda.appendChild(boton);
      filas[indice].appendChild(celda);
    });
  }
  pintarContenido("espacios", tabla);
  mostrarEstado("espacios", "ok", "");
}

function editarTarifa(espacio, celdaTarifa, celdaAccion) {
  const entrada = crearElemento("input");
  entrada.type = "number";
  entrada.min = "0";
  entrada.step = "1000";
  entrada.inputMode = "numeric";
  entrada.placeholder = "Vacío = Por definir";
  entrada.setAttribute("aria-label", `Tarifa por hora en COP de ${espacio.nombre}`);
  entrada.value = espacio.tarifa_hora ?? "";
  const guardar = crearElemento("button", "", "Guardar");
  guardar.type = "button";
  const cancelar = crearElemento("button", "", "Cancelar");
  cancelar.type = "button";
  celdaTarifa.replaceChildren(entrada);
  celdaAccion.replaceChildren(guardar, cancelar);
  entrada.focus();
  cancelar.addEventListener("click", () => cargarEspacios().catch((e) => mostrarEstado("espacios", "error", e.message)));
  guardar.addEventListener("click", async () => {
    const texto = String(entrada.value).trim();
    const valor = texto === "" ? null : Number(texto);
    if (valor !== null && (!Number.isFinite(valor) || valor < 0)) {
      mostrarEstado("espacios", "error", "Escribe un número mayor o igual a 0, o deja el campo vacío.");
      return;
    }
    guardar.disabled = true;
    cancelar.disabled = true;
    mostrarEstado("espacios", "cargando", "Guardando tarifa…");
    try {
      const resultado = await pedir(`/espacios/${encodeURIComponent(espacio.id)}/tarifa`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tarifa_hora: valor }),
      });
      await cargarEspacios();
      mostrarEstado("espacios", "ok", `Tarifa de ${espacio.nombre}: ${textoTarifaAula(resultado.tarifa_hora)}. Las cotizaciones ya creadas no cambian.`);
    } catch (error) {
      mostrarEstado("espacios", "error", `No se guardó la tarifa. ${error.message}`);
      guardar.disabled = false;
      cancelar.disabled = false;
    }
  });
}

// --- Cohortes -------------------------------------------------------------------

async function cargarCohortes() {
  mostrarEstado("cohortes", "cargando", "Cargando cohortes…");
  const cohortes = await pedir("/cohortes");
  if (!cohortes.length) {
    mostrarEstado("cohortes", "vacio", "No hay cohortes cargadas.");
    pintarContenido("cohortes", crearElemento("div"));
    return;
  }
  pintarContenido("cohortes", crearTabla([
    { titulo: "Código", valor: (c) => c.codigo },
    { titulo: "Espacio", valor: (c) => c.espacio_id },
    { titulo: "Jornada", valor: (c) => c.jornada },
    { titulo: "Ruta", valor: (c) => c.ruta },
    { titulo: "Campers", valor: (c) => c.cantidad_campers },
    { titulo: "Fecha fin", valor: (c) => c.fecha_fin },
    { titulo: "Trainer", valor: (c) => c.trainer },
    {
      titulo: "Días restantes",
      valor: (c) => (c.dias_restantes < 0 ? `Vencida (${Math.abs(c.dias_restantes)} días)` : c.dias_restantes),
      clase: (c) => (c.dias_restantes < 0 ? "vencida" : ""),
    },
  ], cohortes));
  mostrarEstado("cohortes", "ok", "");
}

// --- Calidad de datos -----------------------------------------------------------

async function cargarCalidad() {
  mostrarEstado("calidad", "cargando", "Cargando calidad de datos…");
  const datos = await pedir("/calidad-datos");
  const bloques = document.createDocumentFragment();

  bloques.appendChild(crearElemento("h2", "seccion-titulo", "Resumen por archivo"));
  bloques.appendChild(crearTabla([
    { titulo: "Archivo", valor: (r) => r.archivo },
    { titulo: "Cargados", valor: (r) => r.cargados },
    { titulo: "Corregidos", valor: (r) => r.corregidos },
    { titulo: "Rechazados", valor: (r) => r.rechazados },
    { titulo: "Conflictos", valor: (r) => r.conflictos },
  ], datos.resumen));

  bloques.appendChild(crearElemento("h2", "seccion-titulo", "Última importación"));
  bloques.appendChild(pintarUltimaImportacion(datos.ultima_importacion));

  bloques.appendChild(crearElemento("h2", "seccion-titulo", "Registros rechazados"));
  bloques.appendChild(datos.rechazados.length
    ? crearTabla([
      { titulo: "Archivo", valor: (r) => r.archivo },
      { titulo: "Fila", valor: (r) => r.fila },
      { titulo: "Motivo", valor: (r) => r.motivo },
      { titulo: "Contenido original", valor: (r) => JSON.stringify(r.contenido) },
    ], datos.rechazados)
    : crearElemento("p", "estado", "No hay registros rechazados."));

  bloques.appendChild(crearElemento("h2", "seccion-titulo", "Correcciones aplicadas"));
  bloques.appendChild(datos.correcciones.length
    ? crearTabla([
      { titulo: "Archivo", valor: (c) => c.archivo },
      { titulo: "Fila", valor: (c) => c.fila },
      { titulo: "Registro", valor: (c) => c.id_registro },
      { titulo: "Campo", valor: (c) => c.campo },
      { titulo: "Original", valor: (c) => c.valor_original },
      { titulo: "Corregido", valor: (c) => c.valor_corregido },
    ], datos.correcciones)
    : crearElemento("p", "estado", "No hubo correcciones."));

  bloques.appendChild(crearElemento("h2", "seccion-titulo", "Conflictos detectados"));
  bloques.appendChild(datos.conflictos.length
    ? crearTabla([
      { titulo: "Tipo", valor: (c) => c.tipo },
      { titulo: "Archivo", valor: (c) => c.archivo },
      { titulo: "Referencia", valor: (c) => c.referencia },
      { titulo: "Descripción", valor: (c) => c.descripcion },
    ], datos.conflictos)
    : crearElemento("p", "estado", "No hay conflictos."));

  pintarContenido("calidad", bloques);
  mostrarEstado("calidad", "ok", "");
}

// Muestra el último intento de importación. Vive fuera de .estado, así que no lo borra la carga de la tabla.
function pintarUltimaImportacion(importacion) {
  if (!importacion) return crearElemento("p", "estado", "Todavía no se ha importado ningún dato.");
  const texto = importacion.exito
    ? `${importacion.fecha_hora}: ${importacion.mensaje}`
    : `${importacion.fecha_hora}: la importación falló (${importacion.codigo}). ${importacion.mensaje}. Se conservaron los datos anteriores.`;
  return crearElemento("p", importacion.exito ? "estado estado-ok" : "estado estado-error", texto);
}

function mostrarResultadoImportacion(tipo, texto) {
  const caja = document.getElementById("resultado-importacion");
  caja.className = `resultado estado-${tipo}`;
  caja.textContent = texto;
}

function esEnteroNoNegativo(valor) {
  return Number.isInteger(valor) && valor >= 0;
}

// Contrato de POST /api/datos/recargar en éxito. Cualquier otra forma
// no demuestra que la importación se aplicó.
function contratoRecargaValido(datos) {
  if (datos === null || typeof datos !== "object" || Array.isArray(datos)) return false;
  if (datos.ok !== true) return false;
  const cargados = datos.cargados;
  if (cargados === null || typeof cargados !== "object" || Array.isArray(cargados)) return false;
  return Object.values(cargados).every(esEnteroNoNegativo) && esEnteroNoNegativo(datos.conflictos);
}

async function recargarDatos() {
  const boton = document.getElementById("boton-recargar");
  boton.disabled = true;
  mostrarEstado("calidad", "cargando", "Importando datos…");
  try {
    const resumen = await pedir("/datos/recargar", { method: "POST" });
    if (!contratoRecargaValido(resumen)) {
      throw errorResultadoDesconocido("La respuesta del servidor no tiene el formato esperado.");
    }
    mostrarResultadoImportacion("ok", `Importación correcta. Cargados: ${JSON.stringify(resumen.cargados)}. Conflictos: ${resumen.conflictos}.`);
    cargadosPorPestana.clear();
  } catch (error) {
    if (error.resultadoDesconocido) {
      mostrarResultadoImportacion("error",
        "No se pudo confirmar el resultado de la importación. Consulte la última importación antes de repetirla.");
    } else {
      mostrarResultadoImportacion("error",
        `La importación no se aplicó (${error.codigo}): ${error.message} Se conservaron los datos anteriores.`);
    }
  } finally {
    boton.disabled = false;
    await cargarCalidad().catch((error) => mostrarEstado("calidad", "error", error.message));
  }
}

// --- Sesión --------------------------------------------------------------------

async function cargarSesion() {
  const aviso = document.getElementById("aviso-sesion");
  try {
    const sesion = await pedir("/sesion");
    aviso.textContent = `USUARIO DE DESARROLLO: ${sesion.usuario_id} (rol ${sesion.rol}). No es autenticación.`;
    document.getElementById("saludo").textContent = `Hola, ${sesion.usuario_id} 👋`;
    document.getElementById("rol-activo").textContent = sesion.rol;
    document.getElementById("avatar").textContent = sesion.usuario_id.replace(/[^A-Za-z0-9]/g, "").slice(0, 2).toUpperCase() || "?";
    // Solo oculta la pestaña; el servidor responde 403 a /cohortes y /calidad-datos para otros roles.
    document.getElementById("tab-datos").hidden = sesion.rol !== "coordinadora";
  } catch (error) {
    aviso.textContent = error.codigo === "sin_identidad"
      ? "Sin identidad de desarrollo configurada. Las acciones protegidas no están disponibles."
      : `No se pudo leer la sesión. ${error.message}`;
  }
}

// --- Solicitudes registradas ----------------------------------------------------

let numeroCargaSolicitudes = 0;
const aprobacionesEnCurso = new Set();

async function cargarSolicitudes() {
  const carga = ++numeroCargaSolicitudes;
  const resultado = document.getElementById("resultado-solicitudes");
  const contenedor = document.getElementById("solicitudes-registradas");
  resultado.textContent = "Cargando solicitudes…";
  try {
    const [filas, sesion, espacios] = await Promise.all([pedir("/solicitudes"), pedir("/sesion"), pedir("/espacios")]);
    if (carga !== numeroCargaSolicitudes) return;
    const coordinadora = sesion.rol === "coordinadora";
    document.getElementById("titulo-solicitudes").textContent = coordinadora ? "Todas las solicitudes" : "Mis solicitudes";
    document.getElementById("subtitulo-solicitudes").textContent = coordinadora
      ? "Solicitudes de todos los usuarios · Aprobación" : `Solo las solicitudes de ${sesion.usuario_id}`;
    const nombres = Object.fromEntries(espacios.map((e) => [e.id, e.nombre]));
    nombresAulas = nombres;
    const tabla = crearTabla([
      { titulo: "ID", valor: (f) => f.id },
      { titulo: "Aula", valor: (f) => nombres[f.espacio_id] || f.espacio_id },
      { titulo: "Inicio", valor: (f) => f.inicio },
      { titulo: "Fin", valor: (f) => f.fin },
      { titulo: "Devolución anticipada", valor: (f) => f.hora_devolucion },
      { titulo: "Personas", valor: (f) => f.personas },
      { titulo: "Solicitante", valor: (f) => f.solicitante_id || "No disponible" },
      { titulo: "Motivo", valor: (f) => f.descripcion },
      { titulo: "Estado", valor: (f) => f.estado, clase: (f) => `celda-${f.estado}` },
      { titulo: "Condición", valor: (f) => f.tipo === "comercial"
        ? `Comercial · Pago ${f.estado_pago || "pendiente"} (no verificado por el sistema)` : "Académica" },
    ], filas);
    if (sesion.rol === "coordinadora") {
      tabla.querySelector("thead").querySelector("tr").appendChild(crearElemento("th", "", "Acción"));
      const cuerpo = tabla.querySelector("tbody");
      filas.forEach((fila, indice) => {
        const celda = crearElemento("td");
        if (fila.estado === "pendiente" && fila.solicitante_id !== sesion.usuario_id) {
          const boton = crearElemento("button", "", "Aprobar");
          boton.type = "button";
          boton.disabled = aprobacionesEnCurso.has(fila.id);
          boton.addEventListener("click", () => aprobarSolicitud(fila.id, boton));
          celda.appendChild(boton);
          if (fila.actividad === "zona_franca" && fila.tipo === "academica") {
            const evaluar = crearElemento("button", "", "Evaluar reubicación de SER");
            evaluar.type = "button";
            evaluar.addEventListener("click", () => proponerReubicacion(fila.id, evaluar));
            celda.appendChild(evaluar);
          }
        }
        cuerpo.children[indice].appendChild(celda);
      });
    }
    // Cambiar/cancelar propias y cambios por revisar (static/cambios.js), si está cargado.
    if (typeof agregarAccionesTitular === "function") agregarAccionesTitular(tabla, filas, sesion);
    if (typeof cargarCambios === "function") cargarCambios(sesion);
    contenedor.replaceChildren(filas.length ? tabla : crearElemento("p", "estado", "No hay solicitudes registradas."));
    resultado.className = "resultado estado-ok";
    resultado.textContent = `${filas.length} solicitud(es) registrada(s).`;
    return true;
  } catch (error) {
    if (carga !== numeroCargaSolicitudes) return;
    contenedor.replaceChildren();
    resultado.className = "resultado estado-error";
    resultado.textContent = `No se pudieron actualizar las solicitudes. ${error.message}`;
    return false;
  }
}

async function aprobarSolicitud(id, boton) {
  if (boton.disabled || aprobacionesEnCurso.has(id)) return;
  aprobacionesEnCurso.add(id);
  boton.disabled = true;
  const fechaAlAprobar = document.getElementById("selector-fecha").value;
  const resultado = document.getElementById("resultado-solicitudes");
  let aprobada;
  try {
    aprobada = await pedir(`/solicitudes/${id}/aprobar`, { method: "POST" });
    if (!aprobada || aprobada.id !== id || aprobada.estado !== "aprobada"
        || typeof aprobada.inicio !== "string" || !/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(aprobada.inicio)) {
      throw errorResultadoDesconocido("La respuesta no confirma la aprobación.");
    }
  } catch (error) {
    resultado.className = "resultado estado-error";
    const rechazoConfirmado = ["sin_identidad", "sin_permiso", "autoaprobacion_no_permitida",
      "solicitud_no_encontrada", "no_pendiente", "espacio_no_disponible", "aforo_excedido", "solapamiento",
      "prioridad_academica", "elementos_no_verificados"]
      .includes(error.codigo);
    resultado.textContent = rechazoConfirmado
      ? `No se aprobó la solicitud (${error.codigo}): ${error.message}`
      : "No se pudo confirmar el resultado de la aprobación. Actualice las solicitudes antes de repetirla.";
    aprobacionesEnCurso.delete(id);
    boton.disabled = !rechazoConfirmado; // consultar el estado antes de repetir un resultado desconocido
    return;
  }
  aprobacionesEnCurso.delete(id);
  try {
    const fechaActual = document.getElementById("selector-fecha").value;
    const fechaRefresco = fechaActual === fechaAlAprobar ? aprobada.inicio.slice(0, 10) : fechaActual;
    const [listaActualizada, calendarioActualizado] = await Promise.all([cargarSolicitudes(), cargarGrilla(fechaRefresco)]);
    if (!listaActualizada || !calendarioActualizado) throw new Error("Consulte de nuevo las solicitudes y el calendario.");
    resultado.className = "resultado estado-ok";
    resultado.textContent = `Solicitud ${id} aprobada. Devolución: ${aprobada.hora_devolucion}.`;
  } catch (error) {
    resultado.className = "resultado estado-error";
    resultado.textContent = `Solicitud ${id} aprobada. No se pudo actualizar la vista: ${error.message}`;
  }
}

// La evaluación solo guarda una propuesta. Únicamente confirmar aplica el cambio.
async function proponerReubicacion(solicitudId, boton) {
  if (boton.disabled) return;
  boton.disabled = true;
  const panel = document.getElementById("reubicacion-propuesta");
  panel.replaceChildren(crearElemento("p", "estado", "Evaluando alternativa sin mover actividades…"));
  try {
    const plan = await pedir(`/solicitudes/${solicitudId}/reubicacion/proponer`, { method: "POST" });
    if (!plan || plan.estado !== "propuesta" || typeof plan.id !== "string") throw new Error("Respuesta de evaluación no reconocida.");
    pintarReubicacion(plan);
  } catch (error) {
    panel.replaceChildren(crearElemento("p", "estado estado-error", `No se aplicó ninguna reubicación con esta evaluación. ${error.message}`));
  } finally {
    boton.disabled = false;
  }
}

function pintarReubicacion(plan) {
  const panel = document.getElementById("reubicacion-propuesta");
  const tarjeta = crearElemento("article", "tarjeta-propuesta");
  tarjeta.appendChild(crearElemento("h3", "", plan.estado === "aplicada" ? "Reubicación y aprobación confirmadas" : "Propuesta de reubicación · Requiere autorización"));
  tarjeta.appendChild(crearElemento("p", "", `SER: ${plan.aula_origen} → ${plan.aula_destino}. ${plan.inicio} → ${plan.fin}, ${plan.personas} personas. Zona Franca solicita el aula original.`));
  if (plan.estado === "aplicada") {
    tarjeta.appendChild(crearElemento("p", "", `Autorizada por ${plan.autorizada_por} · ${plan.autorizada_en}.`));
  } else {
    const confirmar = crearElemento("button", "", "Confirmar reubicación y aprobar Zona Franca");
    confirmar.type = "button";
    confirmar.addEventListener("click", () => confirmarReubicacion(plan, confirmar));
    tarjeta.appendChild(confirmar);
  }
  panel.replaceChildren(tarjeta);
}

async function confirmarReubicacion(plan, boton) {
  if (boton.disabled) return;
  boton.disabled = true;
  const fechaAlConfirmar = document.getElementById("selector-fecha").value;
  const panel = document.getElementById("reubicacion-propuesta");
  try {
    const resultado = await pedir(`/reubicaciones/${plan.id}/confirmar`, { method: "POST" });
    if (!resultado || resultado.id !== plan.id || resultado.estado !== "aplicada") throw new Error("La respuesta no confirma el cambio.");
    pintarReubicacion(resultado);
    const fechaActual = document.getElementById("selector-fecha").value;
    const preferida = fechaAlConfirmar === fechaActual ? (resultado.solicitud_inicio || resultado.inicio).slice(0, 10) : fechaActual;
    const [lista, calendario] = await Promise.all([cargarSolicitudes(), cargarGrilla(preferida)]);
    if (!lista || !calendario) panel.appendChild(crearElemento("p", "estado", "El cambio fue aplicado, pero debes actualizar las vistas."));
  } catch (error) {
    panel.appendChild(crearElemento("p", "estado estado-error", `No se confirmó el resultado. ${error.message} Consulta el estado antes de repetir.`));
    const consultar = crearElemento("button", "", "Consultar reubicación");
    consultar.type = "button";
    consultar.addEventListener("click", async () => {
      consultar.disabled = true;
      try {
        const estado = await pedir(`/reubicaciones/${plan.id}`);
        if (!estado || estado.id !== plan.id || !["propuesta", "aplicada"].includes(estado.estado)) throw new Error("Estado no reconocido.");
        pintarReubicacion(estado);
        await Promise.all([cargarSolicitudes(), cargarGrilla()]);
      } catch (fallo) {
        panel.appendChild(crearElemento("p", "estado estado-error", fallo.message));
        consultar.disabled = false;
      }
    });
    panel.appendChild(consultar);
  }
}

// --- Estado de la IA -----------------------------------------------------------

async function cargarEstadoIA() {
  const insignia = document.getElementById("estado-ia");
  try {
    const salud = await pedir("/ia/salud");
    const conectada = salud.estado === "conectada";
    insignia.className = `insignia ${conectada ? "insignia-ok" : "insignia-error"}`;
    insignia.textContent = conectada
      ? `IA: catálogo accesible (${salud.modelo}). Inferencia por verificar.`
      : `IA: no disponible. ${salud.mensaje}`;
  } catch (error) {
    insignia.className = "insignia insignia-error";
    insignia.textContent = `IA: no disponible. ${error.message}`;
  }
}

// --- Chat de solicitudes --------------------------------------------------------

const ESTADOS_CHAT_CORRECTOS = new Set(["consulta", "propuesta", "solicitud_creada", "solicitudes", "ya_creada"]);

// Identificador de la conversación de esta pestaña: separa los borradores de cada conversación.
const CONVERSACION_ID = typeof crypto !== "undefined" && crypto.randomUUID
  ? crypto.randomUUID()
  : `c${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;

let chatEnviando = false;
let chatRequiereConsulta = false;

function agregarMensaje(autor, texto) {
  const historial = document.getElementById("historial-chat");
  const mensaje = crearElemento("article", `mensaje mensaje-${autor === "Tú" ? "usuario" : "asistente"}`);
  mensaje.appendChild(crearElemento("strong", "autor-mensaje", autor));
  mensaje.appendChild(crearElemento("p", "", texto));
  historial.appendChild(mensaje);
  historial.scrollTop = historial.scrollHeight;
  return mensaje;
}

function tarjetaSolicitud(fila, estadoChat) {
  const tarjeta = crearElemento("article", "tarjeta-propuesta");
  const estado = fila.estado || (estadoChat === "propuesta" ? "propuesta" : "pendiente");
  const titulo = estado === "propuesta" ? "Propuesta · Requiere tu confirmación"
    : estado === "aprobada" ? "Reserva aprobada" : "Solicitud pendiente de aprobación";
  tarjeta.appendChild(crearElemento("h3", "", titulo));
  const inicio = fila.inicio || "";
  const fin = fila.fin || "";
  const horaInicio = inicio.includes(" ") ? inicio.slice(11) : inicio;
  const horaFin = fin.includes(" ") && fin.slice(0, 10) === inicio.slice(0, 10) ? fin.slice(11) : fin;
  const campos = [
    ["Aula", fila.nombre || nombresAulas[fila.espacio_id] || fila.espacio_id],
    ["Fecha", fila.fecha || (fila.inicio || "").slice(0, 10)],
    ["Horario", `${horaInicio} → ${horaFin}`],
    ["Asistentes", fila.personas], ["Actividad", fila.descripcion],
  ];
  const lista = crearElemento("dl");
  campos.forEach(([nombre, valor]) => {
    if (valor === undefined || valor === null || valor === "") return;
    lista.appendChild(crearElemento("dt", "", nombre));
    lista.appendChild(crearElemento("dd", "", String(valor)));
  });
  tarjeta.appendChild(lista);
  if (fila.requiere_reubicacion) tarjeta.appendChild(crearElemento("p", "ayuda", "Aula ocupada por SER. La coordinadora debe evaluar y confirmar la reubicación; todavía no está disponible."));
  if (fila.tipo === "comercial") tarjeta.appendChild(crearElemento("p", "ayuda", "Comercial · Pago pendiente, no verificado por el sistema."));
  return tarjeta;
}

function pintarDatosChat(datos, estado, destino) {
  if (estado === "propuesta" || estado === "solicitud_creada" || estado === "solicitudes") {
    datos.forEach((fila) => destino.appendChild(tarjetaSolicitud(fila, estado)));
  } else if (estado === "consulta") {
    datos.forEach((fila) => destino.appendChild(crearElemento("p", "aula-disponible", `${fila.nombre || fila.id} · Aforo ${fila.aforo}`)));
  }
  const historial = document.getElementById("historial-chat");
  historial.scrollTop = historial.scrollHeight;
}

function actualizarEstadoEnvio() {
  const boton = document.getElementById("enviar-chat");
  boton.disabled = chatEnviando || chatRequiereConsulta;
  boton.textContent = chatEnviando ? "Enviando…" : "Enviar mensaje";
  document.getElementById("entrada-chat").disabled = chatEnviando;
  document.getElementById("form-chat").setAttribute("aria-busy", String(chatEnviando));
  document.getElementById("consultar-resultado-chat").hidden = !chatRequiereConsulta;
}

async function consultarResultadoChat() {
  const respuesta = document.getElementById("respuesta-chat");
  const consultar = document.getElementById("consultar-resultado-chat");
  consultar.disabled = true;
  try {
    const [filas, espacios] = await Promise.all([pedir("/solicitudes"), pedir("/espacios")]);
    if (!Array.isArray(filas) || !Array.isArray(espacios)) throw new Error("Respuesta no reconocida.");
    const nombres = Object.fromEntries(espacios.map((e) => [e.id, e.nombre]));
    const mensaje = agregarMensaje("Asistente", "Estado consultado. Revisa las solicitudes registradas antes de volver a confirmar. "
      + "El listado no permite atribuir una solicitud a este mensaje; no se reenvió ninguna confirmación.");
    pintarDatosChat(filas.map((f) => ({ ...f, nombre: nombres[f.espacio_id] || f.espacio_id })), "solicitudes", mensaje);
    if (!filas.length) mensaje.appendChild(crearElemento("p", "", "No hay solicitudes registradas para la identidad actual."));
    respuesta.textContent = "Resultado del mensaje anterior desconocido. Se consultó el estado; revisa el listado antes de repetir en esta conversación.";
    chatRequiereConsulta = false;
    await cargarSolicitudes();
  } catch (error) {
    respuesta.textContent = `Resultado desconocido. No se pudo consultar el estado: ${error.message} Consulta antes de repetir.`;
  } finally {
    consultar.disabled = false;
    actualizarEstadoEnvio();
  }
}

async function enviarChat(evento) {
  evento.preventDefault();
  if (chatEnviando || chatRequiereConsulta) return;
  const entrada = document.getElementById("entrada-chat");
  const respuesta = document.getElementById("respuesta-chat");
  const datosPanel = document.getElementById("datos-chat");
  const texto = entrada.value.trim();
  if (!texto) return;
  chatEnviando = true;
  actualizarEstadoEnvio();
  agregarMensaje("Tú", texto);
  datosPanel.replaceChildren();
  respuesta.className = "resultado estado-cargando";
  respuesta.textContent = "Consultando…";
  try {
    const datos = await pedir("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensaje: texto, conversacion_id: CONVERSACION_ID }),
    });
    if (!datos || typeof datos.estado !== "string" || typeof datos.respuesta !== "string" || !Array.isArray(datos.datos)) {
      throw errorResultadoDesconocido("La respuesta del chat no permite confirmar el resultado.");
    }
    respuesta.className = `resultado estado-${ESTADOS_CHAT_CORRECTOS.has(datos.estado) ? "ok" : "vacio"}`;
    respuesta.textContent = datos.respuesta;
    const mensaje = agregarMensaje("Asistente", datos.respuesta);
    if (datos.estado === "solicitud_creada") mensaje.appendChild(crearElemento("p", "etiqueta", "Solicitud pendiente de aprobación"));
    pintarDatosChat(datos.datos, datos.estado, mensaje);
    entrada.value = "";
  } catch (error) {
    respuesta.className = "resultado estado-error";
    respuesta.textContent = error.message;
    agregarMensaje("Asistente", error.message);
    const sinAccion = ["ia_no_disponible", "mensaje_no_valido", "sin_identidad", "sin_permiso"].includes(error.codigo);
    if (!sinAccion) {
      chatRequiereConsulta = true;
      await consultarResultadoChat();
    }
  } finally {
    await cargarSolicitudes();
    chatEnviando = false;
    actualizarEstadoEnvio();
  }
}

document.getElementById("form-chat").addEventListener("submit", enviarChat);

// --- Arranque -------------------------------------------------------------------

document.querySelectorAll(".pestana").forEach((boton) => {
  boton.addEventListener("click", () => activarPestana(boton.dataset.pestana));
  boton.addEventListener("keydown", (evento) => {
    const teclas = ["ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp", "Home", "End"];
    if (!teclas.includes(evento.key)) return;
    evento.preventDefault();
    const botones = [...document.querySelectorAll(".pestana")].filter((b) => !b.hidden);
    const actual = botones.indexOf(boton);
    const indice = evento.key === "Home" ? 0 : evento.key === "End" ? botones.length - 1
      : (actual + (["ArrowRight", "ArrowDown"].includes(evento.key) ? 1 : -1) + botones.length) % botones.length;
    botones[indice].focus();
    activarPestana(botones[indice].dataset.pestana);
  });
});

document.getElementById("selector-fecha").addEventListener("change", (evento) => cargarDia(evento.target.value));
document.getElementById("dia-anterior").addEventListener("click", () => cargarGrilla(diaVecino(document.getElementById("selector-fecha").value || fechaLocalHoy(), -1)));
document.getElementById("dia-siguiente").addEventListener("click", () => cargarGrilla(diaVecino(document.getElementById("selector-fecha").value || fechaLocalHoy(), 1)));
document.getElementById("dia-hoy").addEventListener("click", () => cargarGrilla(fechaLocalHoy()));
document.getElementById("consultar-resultado-chat").addEventListener("click", consultarResultadoChat);
document.getElementById("boton-recargar").addEventListener("click", recargarDatos);
document.getElementById("boton-actualizar-solicitudes").addEventListener("click", cargarSolicitudes);
activarPestana("grilla");
cargarEstadoIA();
cargarSesion();
