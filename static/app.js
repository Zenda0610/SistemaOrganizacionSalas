// Interfaz mínima: consume la API y muestra estados de carga, vacío y error.
const API = "/api";
const HORA_APERTURA = 0;   // vista 24/7
const HORA_CIERRE = 24;    // vista 24/7 (24 = medianoche del día siguiente)
const PASO_MINUTOS = 15;   // debe coincidir con MINUTOS_BLOQUE
const NOMBRES_AREA = { software: "Software", ingles: "Inglés", ser: "SER", otra: "Otra" };

const cargadores = {
  grilla: cargarGrilla,
  espacios: cargarEspacios,
  cohortes: cargarCohortes,
  calidad: cargarCalidad,
  chat: async () => {},
  solicitudes: cargarSolicitudes,
};
const cargadosPorPestana = new Set();

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
  document.querySelectorAll(".pestana").forEach((b) => b.classList.toggle("activa", b.dataset.pestana === nombre));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("activo", p.id === nombre));
  if (!cargadosPorPestana.has(nombre) || nombre === "grilla" || nombre === "solicitudes") {
    cargadores[nombre]().catch((error) => mostrarEstado(nombre, "error", error.message));
    cargadosPorPestana.add(nombre);
  }
}

// --- Grilla semanal (por día) ---------------------------------------------------

async function cargarGrilla(fechaPreferida) {
  mostrarEstado("grilla", "cargando", "Cargando grilla…");
  const selector = document.getElementById("selector-fecha");
  const seleccionAnterior = fechaPreferida || selector.value;
  {
    const [todas, reservas] = await Promise.all([pedir("/sesiones"), pedir("/reservas")]);
    const fechas = [...new Set([...todas.map((s) => s.fecha), ...reservas.flatMap(fechasDeReserva)])].sort();
    if (!fechas.length) {
      mostrarEstado("grilla", "vacio", "No hay sesiones cargadas. Recargue los datos desde la pestaña Calidad de datos.");
      document.getElementById("tabla-grilla").replaceChildren();
      selector.replaceChildren();
      document.getElementById("reservas-aprobadas").replaceChildren();
      return;
    }
    selector.replaceChildren();
    fechas.forEach((f) => selector.appendChild(new Option(f, f)));
    if (fechas.includes(seleccionAnterior)) selector.value = seleccionAnterior;
    selector.onchange = () => cargarDia(selector.value);
  }
  await cargarDia(selector.value);
  pintarLeyenda();
}

async function cargarDia(fecha) {
  const [espacios, sesiones, reservas] = await Promise.all([
    pedir("/espacios"), pedir(`/sesiones?fecha=${fecha}`), pedir(`/reservas?fecha=${fecha}`),
  ]);
  if (!espacios.length) {
    mostrarEstado("grilla", "vacio", "No hay espacios cargados.");
    return;
  }
  construirGrilla(espacios, sesiones, reservas, fecha);
  pintarReservas(espacios, reservas);
  mostrarEstado("grilla", sesiones.length || reservas.length ? "ok" : "vacio",
    sesiones.length || reservas.length ? "" : `No hay sesiones ni reservas programadas para ${fecha}.`);
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
  espacios.forEach((e) => cabecera.appendChild(crearElemento("th", "", `${e.nombre} (${e.aforo})`)));
  tabla.replaceChildren(crearElemento("thead"));
  tabla.querySelector("thead").appendChild(cabecera);

  const cuerpo = crearElemento("tbody");
  for (let t = HORA_APERTURA * 60; t < HORA_CIERRE * 60; t += PASO_MINUTOS) {
    const fila = crearElemento("tr");
    fila.appendChild(crearElemento("td", "hora", t % 60 === 0 ? horaDesdeMinutos(t) : ""));
    espacios.forEach((e) => {
      const celda = crearElemento("td", "celda");
      bloques.filter((b) => b.espacioId === e.id && b.inicio === t)  // el bloque se dibuja en su primera franja
        .forEach((b) => celda.appendChild(crearBloque(b)));
      fila.appendChild(celda);
    });
    cuerpo.appendChild(fila);
  }
  tabla.appendChild(cuerpo);
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

async function cargarEspacios() {
  mostrarEstado("espacios", "cargando", "Cargando espacios…");
  const espacios = await pedir("/espacios");
  if (!espacios.length) {
    pintarContenido("espacios", crearElemento("div"));
    mostrarEstado("espacios", "vacio", "No hay espacios cargados.");
    return;
  }
  pintarContenido("espacios", crearTabla([
    { titulo: "ID", valor: (e) => e.id },
    { titulo: "Nombre", valor: (e) => e.nombre },
    { titulo: "Tipo", valor: (e) => e.tipo },
    { titulo: "Aforo", valor: (e) => e.aforo },
    { titulo: "Estado", valor: (e) => e.estado },
  ], espacios));
  mostrarEstado("espacios", "ok", "");
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
    const nombres = Object.fromEntries(espacios.map((e) => [e.id, e.nombre]));
    const tabla = crearTabla([
      { titulo: "ID", valor: (f) => f.id },
      { titulo: "Aula", valor: (f) => nombres[f.espacio_id] || f.espacio_id },
      { titulo: "Inicio", valor: (f) => f.inicio },
      { titulo: "Fin", valor: (f) => f.fin },
      { titulo: "Devolución anticipada", valor: (f) => f.hora_devolucion },
      { titulo: "Personas", valor: (f) => f.personas },
      { titulo: "Motivo", valor: (f) => f.descripcion },
      { titulo: "Estado", valor: (f) => f.estado },
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
        }
        cuerpo.children[indice].appendChild(celda);
      });
    }
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
      "solicitud_no_encontrada", "no_pendiente", "espacio_no_disponible", "aforo_excedido", "solapamiento"]
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
    const [listaActualizada] = await Promise.all([cargarSolicitudes(), cargarGrilla(aprobada.inicio.slice(0, 10))]);
    if (!listaActualizada) throw new Error("Consulte de nuevo las solicitudes registradas.");
    resultado.className = "resultado estado-ok";
    resultado.textContent = `Solicitud ${id} aprobada. Devolución: ${aprobada.hora_devolucion}.`;
  } catch (error) {
    resultado.className = "resultado estado-error";
    resultado.textContent = `Solicitud ${id} aprobada. No se pudo actualizar la vista: ${error.message}`;
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
      ? `IA: conectada (${salud.proveedor} · ${salud.modelo})`
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

async function enviarChat(evento) {
  evento.preventDefault();
  const entrada = document.getElementById("entrada-chat");
  const respuesta = document.getElementById("respuesta-chat");
  const datosPanel = document.getElementById("datos-chat");
  const texto = entrada.value.trim();
  if (!texto) return;
  respuesta.className = "resultado estado-cargando";
  respuesta.textContent = "Consultando…";
  try {
    const datos = await pedir("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensaje: texto, conversacion_id: CONVERSACION_ID }),
    });
    respuesta.className = `resultado estado-${ESTADOS_CHAT_CORRECTOS.has(datos.estado) ? "ok" : "vacio"}`;
    respuesta.textContent = datos.respuesta;
    if (datos.datos.length) {
      const columnas = Object.keys(datos.datos[0]).map((clave) => ({ titulo: clave, valor: (f) => String(f[clave]) }));
      datosPanel.replaceChildren(crearTabla(columnas, datos.datos));
    } else {
      datosPanel.replaceChildren();
    }
  } catch (error) {
    respuesta.className = "resultado estado-error";
    respuesta.textContent = error.message;
    datosPanel.replaceChildren();
  } finally {
    await cargarSolicitudes();
  }
}

document.getElementById("form-chat").addEventListener("submit", enviarChat);

// --- Arranque -------------------------------------------------------------------

document.querySelectorAll(".pestana").forEach((boton) => {
  boton.addEventListener("click", () => activarPestana(boton.dataset.pestana));
});
document.getElementById("boton-recargar").addEventListener("click", recargarDatos);
document.getElementById("boton-actualizar-solicitudes").addEventListener("click", cargarSolicitudes);
activarPestana("grilla");
cargarEstadoIA();
cargarSesion();
