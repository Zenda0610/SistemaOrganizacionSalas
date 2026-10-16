// Asistente de coordinación: lista calculada por el servidor y resumen redactado por la IA.
// Visible solo si /api/sesion dice coordinadora; el servidor vuelve a comprobar el permiso.
let coordinacionEnviando = false;

function pintarNotificaciones(resumen) {
  const lista = document.getElementById('lista-notificaciones');
  const estado = document.getElementById('estado-notificaciones');
  lista.replaceChildren();
  if (!resumen || !Array.isArray(resumen.notificaciones)) throw new Error('Resumen no reconocido.');
  resumen.notificaciones.forEach((n) => {
    const item = crearElemento('li', `nivel-${n.nivel}`);
    item.appendChild(crearElemento('span', 'etiqueta', n.nivel === 'importante' ? 'Importante' : 'Necesaria'));
    item.appendChild(document.createTextNode(n.titulo));
    lista.appendChild(item);
  });
  const t = resumen.totales || {};
  estado.className = 'resultado estado-ok';
  estado.textContent = resumen.notificaciones.length
    ? `${t.importantes} importante(s) y ${t.necesarias} necesaria(s) · calculado ${resumen.generado_en}.`
    : 'No hay notificaciones pendientes.';
}

async function cargarNotificaciones() {
  const estado = document.getElementById('estado-notificaciones');
  estado.className = 'resultado estado-cargando';
  estado.textContent = 'Cargando notificaciones…';
  try {
    pintarNotificaciones(await pedir('/coordinacion/resumen'));
  } catch (error) {
    estado.className = 'resultado estado-error';
    estado.textContent = `No se pudieron cargar las notificaciones. ${error.message}`;
  }
}

function actualizarEnvioCoordinacion() {
  ['enviar-coordinacion', 'resumir-notificaciones', 'entrada-coordinacion'].forEach((id) => {
    document.getElementById(id).disabled = coordinacionEnviando;
  });
  document.getElementById('enviar-coordinacion').textContent = coordinacionEnviando ? 'Consultando…' : 'Enviar';
}

async function preguntarAsistente(texto) {
  if (coordinacionEnviando || !texto) return;
  const estado = document.getElementById('estado-asistente');
  const historial = document.getElementById('historial-coordinacion');
  const agregar = (autor, contenido) => {
    const mensaje = crearElemento('article', `mensaje mensaje-${autor === 'Tú' ? 'usuario' : 'asistente'}`);
    mensaje.appendChild(crearElemento('strong', 'autor-mensaje', autor));
    mensaje.appendChild(crearElemento('p', '', contenido));
    historial.appendChild(mensaje);
    historial.scrollTop = historial.scrollHeight;
  };
  coordinacionEnviando = true;
  actualizarEnvioCoordinacion();
  agregar('Tú', texto);
  estado.className = 'resultado estado-cargando';
  estado.textContent = 'La IA está redactando el resumen…';
  try {
    const datos = await pedir('/coordinacion/asistente', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mensaje: texto }),
    });
    if (typeof datos.respuesta !== 'string') throw new Error('Respuesta del asistente no reconocida.');
    agregar('Asistente', datos.respuesta);
    pintarNotificaciones(datos.resumen);
    estado.className = 'resultado estado-ok';
    estado.textContent = 'Texto generado por IA a partir de la lista. Verifica antes de actuar.';
    document.getElementById('entrada-coordinacion').value = '';
  } catch (error) {
    estado.className = 'resultado estado-error';
    estado.textContent = error.codigo === 'ia_no_disponible'
      ? `IA no disponible: ${error.message} La lista calculada sigue vigente.`
      : `No se pudo consultar al asistente. ${error.message}`;
    await cargarNotificaciones();
  } finally {
    coordinacionEnviando = false;
    actualizarEnvioCoordinacion();
  }
}

async function iniciarCoordinacion() {
  try {
    const sesion = await pedir('/sesion');
    if (sesion.rol !== 'coordinadora') return;
  } catch {
    return;
  }
  document.getElementById('asistente-coordinacion').hidden = false;
  await cargarNotificaciones();
}

document.getElementById('actualizar-notificaciones').addEventListener('click', cargarNotificaciones);
document.getElementById('tab-solicitudes').addEventListener('click', () => {
  if (!document.getElementById('asistente-coordinacion').hidden) cargarNotificaciones();
});
document.getElementById('resumir-notificaciones').addEventListener('click', () =>
  preguntarAsistente('Resume las notificaciones: primero las importantes y luego las necesarias.'));
document.getElementById('form-coordinacion').addEventListener('submit', (evento) => {
  evento.preventDefault();
  preguntarAsistente(document.getElementById('entrada-coordinacion').value.trim());
});
iniciarCoordinacion();
