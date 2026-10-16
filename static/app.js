// Interfaz mínima: consume la API y muestra estados de carga, vacío y error.
const API = "/api";
const HORA_APERTURA = 6;   // debe coincidir con GRILLA_APERTURA_HORA
const HORA_CIERRE = 18;    // debe coincidir con GRILLA_CIERRE_HORA
const PASO_MINUTOS = 15;   // debe coincidir con MINUTOS_BLOQUE
const NOMBRES_AREA = { software: "Software", ingles: "Inglés", ser: "SER", otra: "Otra" };

const cargadores = {
  grilla: cargarGrilla,
  espacios: cargarEspacios,
  cohortes: cargarCohortes,
  calidad: cargarCalidad,
};
const cargadosPorPestana = new Set();

// --- Utilidades -----------------------------------------------------------------

async function pedir(ruta, opciones = {}) {
  let respuesta;
  try {
    respuesta = await fetch(API + ruta, opciones);
  } catch {
    throw new Error("No se pudo conectar con el servidor.");
  }
  let datos = null;
  try {
    datos = await respuesta.json();
  } catch {
    // La respuesta no era JSON; se usa el mensaje genérico de abajo.
  }
  if (!respuesta.ok) {
    const error = new Error((datos && datos.mensaje) || `Error ${respuesta.status} al consultar la API.`);
    error.codigo = datos && datos.codigo;
    throw error;
  }
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
  if (!cargadosPorPestana.has(nombre) || nombre === "grilla") {
    cargadores[nombre]().catch((error) => mostrarEstado(nombre, "error", error.message));
    cargadosPorPestana.add(nombre);
  }
}

// --- Grilla semanal (por día) ---------------------------------------------------

async function cargarGrilla() {
  mostrarEstado("grilla", "cargando", "Cargando grilla…");
  const selector = document.getElementById("selector-fecha");
  if (!selector.options.length) {
    const todas = await pedir("/sesiones");
    const fechas = [...new Set(todas.map((s) => s.fecha))].sort();
    if (!fechas.length) {
      mostrarEstado("grilla", "vacio", "No hay sesiones cargadas. Recargue los datos desde la pestaña Calidad de datos.");
      document.getElementById("tabla-grilla").replaceChildren();
      return;
    }
    fechas.forEach((f) => selector.appendChild(new Option(f, f)));
    selector.onchange = () => cargarDia(selector.value);
  }
  await cargarDia(selector.value);
  pintarLeyenda();
}

async function cargarDia(fecha) {
  const [espacios, sesiones] = await Promise.all([pedir("/espacios"), pedir(`/sesiones?fecha=${fecha}`)]);
  if (!espacios.length) {
    mostrarEstado("grilla", "vacio", "No hay espacios cargados.");
    return;
  }
  construirGrilla(espacios, sesiones);
  mostrarEstado("grilla", sesiones.length ? "ok" : "vacio",
    sesiones.length ? "" : `No hay sesiones programadas para ${fecha}.`);
}

function construirGrilla(espacios, sesiones) {
  const tabla = document.getElementById("tabla-grilla");
  const ocupacion = {};
  sesiones.forEach((s) => {
    for (let t = minutosDesdeHora(s.hora_inicio); t < minutosDesdeHora(s.hora_fin); t += PASO_MINUTOS) {
      const clave = `${s.espacio_id}|${horaDesdeMinutos(t)}`;
      (ocupacion[clave] = ocupacion[clave] || []).push(s);
    }
  });

  const cabecera = crearElemento("tr");
  cabecera.appendChild(crearElemento("th", "hora", "Hora"));
  espacios.forEach((e) => cabecera.appendChild(crearElemento("th", "", `${e.nombre} (${e.aforo})`)));
  tabla.replaceChildren(crearElemento("thead"));
  tabla.querySelector("thead").appendChild(cabecera);

  const cuerpo = crearElemento("tbody");
  for (let t = HORA_APERTURA * 60; t < HORA_CIERRE * 60; t += PASO_MINUTOS) {
    const hora = horaDesdeMinutos(t);
    const fila = crearElemento("tr");
    const celdaHora = crearElemento("td", "hora", t % 60 === 0 ? hora : "");
    fila.appendChild(celdaHora);
    espacios.forEach((e) => {
      const celda = crearElemento("td", "celda");
      const enCelda = ocupacion[`${e.id}|${hora}`] || [];
      enCelda
        .filter((s) => s.hora_inicio === hora)   // el bloque se dibuja en su primera franja
        .forEach((s) => celda.appendChild(crearBloque(s, enCelda.length > 1)));
      fila.appendChild(celda);
    });
    cuerpo.appendChild(fila);
  }
  tabla.appendChild(cuerpo);
}

function crearBloque(sesion, enConflicto) {
  const clases = ["bloque", `area-${sesion.area}`];
  if (sesion.es_zona_franca) clases.push("zona-franca");
  if (sesion.tipo === "alquiler") clases.push("alquiler");
  if (sesion.estado === "cancelada") clases.push("cancelada");
  if (enConflicto) clases.push("conflicto");
  const bloque = crearElemento("div", clases.join(" "));
  bloque.title = `${sesion.id} · ${sesion.tipo} · ${sesion.grupo} · ${sesion.responsable} · ${sesion.hora_inicio}-${sesion.hora_fin}`;
  bloque.textContent = `${sesion.grupo} · ${sesion.responsable}`;
  const franjas = (minutosDesdeHora(sesion.hora_fin) - minutosDesdeHora(sesion.hora_inicio)) / PASO_MINUTOS;
  bloque.style.height = `${franjas * 22 - 2}px`;  // 22 px es la altura de una franja en styles.css
  return bloque;
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

async function recargarDatos() {
  const boton = document.getElementById("boton-recargar");
  boton.disabled = true;
  mostrarEstado("calidad", "cargando", "Importando datos…");
  try {
    const resumen = await pedir("/datos/recargar", { method: "POST" });
    mostrarResultadoImportacion("ok", `Importación correcta. Cargados: ${JSON.stringify(resumen.cargados)}. Conflictos: ${resumen.conflictos}.`);
    cargadosPorPestana.clear();
  } catch (error) {
    const codigo = error.codigo ? ` (${error.codigo})` : "";
    mostrarResultadoImportacion("error", `La importación falló${codigo}: ${error.message} Se conservaron los datos anteriores.`);
  } finally {
    boton.disabled = false;
    await cargarCalidad().catch((error) => mostrarEstado("calidad", "error", error.message));
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

// --- Arranque -------------------------------------------------------------------

document.querySelectorAll(".pestana").forEach((boton) => {
  boton.addEventListener("click", () => activarPestana(boton.dataset.pestana));
});
document.getElementById("boton-recargar").addEventListener("click", recargarDatos);
activarPestana("grilla");
cargarEstadoIA();
