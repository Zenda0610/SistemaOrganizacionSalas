// Pedir un aula seleccionando bloques de 15 min en el calendario. El chat queda como opción.
// El navegador solo arma inicio/fin: aforo, solapamientos, bloqueos, prioridad y costo los decide el servidor.
const ROLES_SOLICITANTES = ['profesor', 'administrativo', 'estudiante', 'empresa'];
const ROLES_COMERCIALES_SEL = ['estudiante', 'empresa'];
const ACTIVIDADES_SEL = { ser: 'SER', zona_franca: 'Zona Franca', ingles: 'Inglés', software: 'Software', otra: 'Otra' };

const estadoSeleccion = {
  rol: null, activo: false, fecha: null, espacios: [], ocupadas: new Set(), celdas: new Map(),
  seleccion: null, cursor: null, arrastrando: false, enviando: false,
};

const claveCelda = (espacioId, minuto) => `${espacioId}|${minuto}`;

function puedeSeleccionar(rol) {
  return ROLES_SOLICITANTES.includes(rol);
}

// Minutos ocupados de cada aula: sesiones, reservas aprobadas, aulas bloqueadas o inactivas y franjas pasadas.
function calcularOcupadas(espacios, bloques, fecha, ahora = new Date()) {
  const ocupadas = new Set();
  const hoy = `${ahora.getFullYear()}-${String(ahora.getMonth() + 1).padStart(2, '0')}-${String(ahora.getDate()).padStart(2, '0')}`;
  const limitePasado = fecha < hoy ? MINUTOS_DIA : fecha === hoy ? ahora.getHours() * 60 + ahora.getMinutes() : 0;
  espacios.forEach((e) => {
    const cerrada = e.bloqueada || e.estado !== 'activo';
    for (let m = 0; m < MINUTOS_DIA; m += PASO_MINUTOS) {
      if (cerrada || m < limitePasado) ocupadas.add(claveCelda(e.id, m));
    }
  });
  bloques.forEach((b) => {
    for (let m = b.inicio - (b.inicio % PASO_MINUTOS); m < b.fin; m += PASO_MINUTOS) ocupadas.add(claveCelda(b.espacioId, m));
  });
  return ocupadas;
}

function rangoLibre(ocupadas, espacioId, desde, hasta) {
  for (let m = desde; m < hasta; m += PASO_MINUTOS) if (ocupadas.has(claveCelda(espacioId, m))) return false;
  return true;
}

// Marca o extiende. Ignora celdas ocupadas y nunca salta sobre una ocupada.
function nuevaSeleccion(seleccion, espacioId, minuto, ocupadas) {
  if (ocupadas.has(claveCelda(espacioId, minuto))) return seleccion;
  if (!seleccion || seleccion.espacioId !== espacioId) {
    return { espacioId, ancla: minuto, inicio: minuto, fin: minuto + PASO_MINUTOS };
  }
  const inicio = Math.min(seleccion.ancla, minuto);
  const fin = Math.max(seleccion.ancla, minuto) + PASO_MINUTOS;
  if (!rangoLibre(ocupadas, espacioId, inicio, fin)) return seleccion;
  return { espacioId, ancla: seleccion.ancla, inicio, fin };
}

function horaFin(minuto) {
  return minuto >= MINUTOS_DIA ? '24:00' : horaDesdeMinutos(minuto);
}

function momentoISO(fecha, minuto) {
  if (minuto >= MINUTOS_DIA) return `${diaVecino(fecha, 1)}T00:00`;
  return `${fecha}T${horaDesdeMinutos(minuto)}`;
}

// Cuerpo de POST /api/solicitudes. Sin rol, tipo, usuario ni costo: eso lo decide el servidor.
function cuerpoSolicitud(seleccion, fecha, campos, comercial) {
  const cuerpo = {
    espacio_id: seleccion.espacioId,
    inicio: momentoISO(fecha, seleccion.inicio),
    fin: momentoISO(fecha, seleccion.fin),
    personas: Number(campos.personas),
    descripcion: String(campos.descripcion || '').trim(),
  };
  if (!comercial && campos.actividad) cuerpo.actividad = campos.actividad;
  return cuerpo;
}

// --- Pintado ---------------------------------------------------------------------

function pintarCeldas() {
  const { seleccion, ocupadas, celdas, activo, cursor } = estadoSeleccion;
  celdas.forEach((celda, clave) => {
    const [espacioId, texto] = clave.split('|');
    const minuto = Number(texto);
    const dentro = Boolean(seleccion && seleccion.espacioId === espacioId && minuto >= seleccion.inicio && minuto < seleccion.fin);
    celda.classList.toggle('seleccionable', activo && !ocupadas.has(clave));
    celda.classList.toggle('no-seleccionable', activo && ocupadas.has(clave));
    celda.classList.toggle('seleccionada', activo && dentro);
    celda.setAttribute('aria-selected', String(activo && dentro));
    celda.tabIndex = activo && cursor && cursor.espacioId === espacioId && cursor.minuto === minuto ? 0 : -1;
  });
  pintarResumen();
}

function nombreEspacio(id) {
  const espacio = estadoSeleccion.espacios.find((e) => e.id === id);
  return espacio ? espacio.nombre : id;
}

function pintarResumen() {
  const panel = document.getElementById('resumen-seleccion');
  const { seleccion, activo, fecha } = estadoSeleccion;
  panel.hidden = !(activo && seleccion);
  if (panel.hidden) return;
  const espacio = estadoSeleccion.espacios.find((e) => e.id === seleccion.espacioId) || {};
  const minutos = seleccion.fin - seleccion.inicio;
  document.getElementById('resumen-seleccion-datos').textContent =
    `${espacio.nombre || seleccion.espacioId} · aforo ${espacio.aforo ?? '—'} · ${fecha} · `
    + `${horaDesdeMinutos(seleccion.inicio)}–${horaFin(seleccion.fin)}`
    + ` · ${minutos >= 60 ? `${minutos / 60} h` : `${minutos} min`}`;
  const comercial = ROLES_COMERCIALES_SEL.includes(estadoSeleccion.rol);
  document.getElementById('campo-actividad-seleccion').hidden = comercial;
  document.getElementById('costo-seleccion').hidden = !comercial;
}

async function cotizarSeleccion() {
  // El costo lo calcula el servidor en /api/disponibilidad; además confirma que la franja se ofrece a este rol.
  const { seleccion, fecha } = estadoSeleccion;
  const destino = document.getElementById('costo-seleccion');
  if (!seleccion || !ROLES_COMERCIALES_SEL.includes(estadoSeleccion.rol)) return;
  destino.textContent = 'Consultando costo…';
  const parametros = new URLSearchParams({ inicio: momentoISO(fecha, seleccion.inicio), fin: momentoISO(fecha, seleccion.fin) });
  try {
    const libres = await pedir(`/disponibilidad?${parametros}`);
    if (seleccion !== estadoSeleccion.seleccion) return;
    const aula = Array.isArray(libres) ? libres.find((a) => a.id === seleccion.espacioId) : null;
    if (!aula) {
      destino.textContent = 'Esta franja no se ofrece para alquiler comercial (ocupada o con prioridad académica).';
      return;
    }
    const costo = aula.costo || {};
    destino.textContent = costo.tarifa_hora === null || costo.tarifa_hora === undefined
      ? 'Costo por hora: Por definir · Total estimado: Por definir'
      : `Costo por hora: $${Math.round(costo.tarifa_hora).toLocaleString('es-CO')} COP · Total estimado: $${Math.round(costo.total).toLocaleString('es-CO')} COP`;
  } catch (error) {
    destino.textContent = `No se pudo consultar el costo. ${error.message}`;
  }
}

function aplicarSeleccion(nueva) {
  const cambio = nueva !== estadoSeleccion.seleccion;
  estadoSeleccion.seleccion = nueva;
  if (cambio) {
    document.getElementById('resultado-seleccion').textContent = '';
    cotizarSeleccion();
  }
  pintarCeldas();
}

function limpiarSeleccion() {
  estadoSeleccion.seleccion = null;
  estadoSeleccion.arrastrando = false;
  pintarCeldas();
}

// --- Envío -----------------------------------------------------------------------

async function enviarSeleccion(evento) {
  if (evento) evento.preventDefault();
  const { seleccion, fecha } = estadoSeleccion;
  if (!seleccion || estadoSeleccion.enviando) return;
  const resultado = document.getElementById('resultado-seleccion');
  const comercial = ROLES_COMERCIALES_SEL.includes(estadoSeleccion.rol);
  const cuerpo = cuerpoSolicitud(seleccion, fecha, {
    personas: document.getElementById('personas-seleccion').value,
    descripcion: document.getElementById('motivo-seleccion').value,
    actividad: document.getElementById('actividad-seleccion').value,
  }, comercial);
  if (!Number.isInteger(cuerpo.personas) || cuerpo.personas < 1 || cuerpo.descripcion.length < 3) {
    resultado.className = 'resultado estado-error';
    resultado.textContent = 'Indica cuántas personas asistirán y un motivo de al menos 3 caracteres.';
    return;
  }
  estadoSeleccion.enviando = true;
  const boton = document.getElementById('enviar-seleccion');
  boton.disabled = true;
  resultado.className = 'resultado estado-cargando';
  resultado.textContent = 'Enviando solicitud…';
  try {
    const creada = await pedir('/solicitudes', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo),
    });
    if (!creada || !Number.isInteger(creada.id)) throw errorResultadoDesconocido('Respuesta sin confirmación válida. Revisa Mis solicitudes antes de repetir.');
    resultado.className = 'resultado estado-ok';
    resultado.textContent = `Solicitud #${creada.id} enviada, pendiente de aprobación.`;
    estadoSeleccion.seleccion = null;
  } catch (error) {
    resultado.className = 'resultado estado-error';
    resultado.textContent = `No se envió la solicitud: ${error.message}`;
  } finally {
    estadoSeleccion.enviando = false;
    boton.disabled = false;
    refrescarTrasEnvio();
  }
}

function refrescarTrasEnvio() {
  // Tras éxito o conflicto se refrescan el calendario y las listas; el mensaje del envío se conserva.
  Promise.resolve(cargarGrilla(estadoSeleccion.fecha)).catch(() => {});
  if (typeof cargarSolicitudes === 'function') cargarSolicitudes();
  if (typeof cargarComercial === 'function' && ROLES_COMERCIALES_SEL.includes(estadoSeleccion.rol)) cargarComercial();
}

// --- Integración con la grilla (llamado por construirGrilla) ----------------------

function prepararSeleccion(espacios, bloques, fecha, celdas) {
  const mismoDia = estadoSeleccion.fecha === fecha;
  Object.assign(estadoSeleccion, {
    espacios, fecha, celdas, ocupadas: calcularOcupadas(espacios, bloques, fecha),
    seleccion: mismoDia ? estadoSeleccion.seleccion : null,
  });
  if (estadoSeleccion.seleccion && !rangoLibre(estadoSeleccion.ocupadas, estadoSeleccion.seleccion.espacioId,
    estadoSeleccion.seleccion.inicio, estadoSeleccion.seleccion.fin)) estadoSeleccion.seleccion = null;
  celdas.forEach((celda, clave) => {
    const [espacioId, texto] = clave.split('|');
    const minuto = Number(texto);
    celda.setAttribute('role', 'gridcell');
    celda.setAttribute('aria-label', `Sala ${nombreEspacio(espacioId)}, ${horaDesdeMinutos(minuto)}-`
      + `${horaFin(minuto + PASO_MINUTOS)}, ${estadoSeleccion.ocupadas.has(clave) ? 'ocupada' : 'libre'}`);
  });
  if (!estadoSeleccion.cursor && espacios.length) estadoSeleccion.cursor = { espacioId: espacios[0].id, minuto: 8 * 60 };
  pintarCeldas();
}

function celdaDesdeElemento(elemento) {
  const celda = elemento && elemento.closest ? elemento.closest('td.celda') : null;
  if (!celda) return null;
  const espacioId = celda.getAttribute('data-espacio');
  const minuto = Number(celda.getAttribute('data-minuto'));
  return espacioId ? { espacioId, minuto } : null;
}

function moverCursor(dx, dy, extender) {
  const { espacios, cursor } = estadoSeleccion;
  if (!cursor || !espacios.length) return;
  const indice = Math.max(0, espacios.findIndex((e) => e.id === cursor.espacioId));
  const nuevoIndice = Math.min(espacios.length - 1, Math.max(0, indice + dx));
  const minuto = Math.min(MINUTOS_DIA - PASO_MINUTOS, Math.max(0, cursor.minuto + dy * PASO_MINUTOS));
  estadoSeleccion.cursor = { espacioId: espacios[nuevoIndice].id, minuto };
  if (extender) aplicarSeleccion(nuevaSeleccion(estadoSeleccion.seleccion, estadoSeleccion.cursor.espacioId, minuto, estadoSeleccion.ocupadas));
  else pintarCeldas();
  const celda = estadoSeleccion.celdas.get(claveCelda(estadoSeleccion.cursor.espacioId, minuto));
  if (celda) { celda.focus(); if (celda.scrollIntoView) celda.scrollIntoView({ block: 'nearest', inline: 'nearest' }); }
}

function teclaGrilla(evento) {
  if (!estadoSeleccion.activo) return;
  const flechas = { ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0] };
  if (flechas[evento.key]) {
    evento.preventDefault();
    moverCursor(...flechas[evento.key], evento.shiftKey);
  } else if (evento.key === ' ' || evento.key === 'Enter') {
    evento.preventDefault();
    const { cursor } = estadoSeleccion;
    if (cursor) aplicarSeleccion(nuevaSeleccion(estadoSeleccion.seleccion, cursor.espacioId, cursor.minuto, estadoSeleccion.ocupadas));
  } else if (evento.key === 'Escape') {
    evento.preventDefault();
    limpiarSeleccion();
  }
}

function inicioPuntero(evento) {
  if (!estadoSeleccion.activo) return;
  const celda = celdaDesdeElemento(evento.target);
  if (!celda) return;
  estadoSeleccion.cursor = celda;
  const nueva = nuevaSeleccion(estadoSeleccion.seleccion, celda.espacioId, celda.minuto, estadoSeleccion.ocupadas);
  // Arrastre: con mouse siempre; en táctil solo desde un bloque ya seleccionado (el resto desplaza la grilla).
  const dentro = estadoSeleccion.seleccion && estadoSeleccion.seleccion.espacioId === celda.espacioId
    && celda.minuto >= estadoSeleccion.seleccion.inicio && celda.minuto < estadoSeleccion.seleccion.fin;
  estadoSeleccion.arrastrando = evento.pointerType === 'mouse' || dentro;
  if (evento.pointerType === 'mouse') evento.preventDefault();
  aplicarSeleccion(nueva);
}

function movimientoPuntero(evento) {
  if (!estadoSeleccion.activo || !estadoSeleccion.arrastrando) return;
  const celda = celdaDesdeElemento(document.elementFromPoint(evento.clientX, evento.clientY));
  if (!celda || !estadoSeleccion.seleccion || celda.espacioId !== estadoSeleccion.seleccion.espacioId) return;
  evento.preventDefault();
  aplicarSeleccion(nuevaSeleccion(estadoSeleccion.seleccion, celda.espacioId, celda.minuto, estadoSeleccion.ocupadas));
}

function alternarModoSeleccion() {
  estadoSeleccion.activo = !estadoSeleccion.activo;
  const boton = document.getElementById('modo-seleccion');
  boton.setAttribute('aria-pressed', String(estadoSeleccion.activo));
  boton.textContent = estadoSeleccion.activo ? 'Salir de la selección' : 'Seleccionar bloques';
  document.getElementById('ayuda-seleccion').hidden = !estadoSeleccion.activo;
  document.getElementById('tabla-grilla').classList.toggle('modo-seleccion', estadoSeleccion.activo);
  if (!estadoSeleccion.activo) estadoSeleccion.seleccion = null;
  pintarCeldas();
}

async function iniciarSeleccion() {
  const boton = document.getElementById('modo-seleccion');
  boton.hidden = true;
  try {
    const sesion = await pedir('/sesion');
    estadoSeleccion.rol = sesion.rol;
  } catch {
    return;
  }
  // La coordinadora no ve este modo; el servidor vuelve a decidir el tipo y el permiso.
  boton.hidden = !puedeSeleccionar(estadoSeleccion.rol);
  const actividad = document.getElementById('actividad-seleccion');
  if (!actividad.children.length) {
    Object.entries(ACTIVIDADES_SEL).forEach(([valor, texto]) => {
      const opcion = crearElemento('option', '', texto);
      opcion.value = valor;
      actividad.appendChild(opcion);
    });
  }
}

document.getElementById('modo-seleccion').addEventListener('click', alternarModoSeleccion);
document.getElementById('form-seleccion').addEventListener('submit', enviarSeleccion);
document.getElementById('limpiar-seleccion').addEventListener('click', limpiarSeleccion);
document.getElementById('tabla-grilla').addEventListener('keydown', teclaGrilla);
document.getElementById('tabla-grilla').addEventListener('pointerdown', inicioPuntero);
document.addEventListener && document.addEventListener('pointermove', movimientoPuntero, { passive: false });
document.addEventListener && document.addEventListener('pointerup', () => { estadoSeleccion.arrastrando = false; });
iniciarSeleccion();
