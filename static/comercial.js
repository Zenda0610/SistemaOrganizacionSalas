// Área comercial: aulas libres con costo y "Mis solicitudes". El costo lo calcula el servidor.
const ROLES_COMERCIALES = ['estudiante', 'empresa'];
let cargaComercial = 0;

function pesos(valor) {
  return `$${Math.round(valor).toLocaleString('es-CO')} COP`;
}

function textoTarifa(costo) {
  return !costo || costo.tarifa_hora === null ? 'Por definir' : `${pesos(costo.tarifa_hora)} por hora`;
}

function textoTotal(costo) {
  return !costo || costo.total === null ? 'Por definir' : `${pesos(costo.total)} (${costo.horas} h)`;
}

async function cargarMisSolicitudesComerciales() {
  const [filas, espacios] = await Promise.all([pedir('/solicitudes'), pedir('/espacios')]);
  if (!Array.isArray(filas) || !Array.isArray(espacios)) throw new Error('Listado no válido.');
  const nombres = Object.fromEntries(espacios.map((e) => [e.id, e.nombre]));
  const contenedor = document.getElementById('mis-solicitudes-comerciales');
  contenedor.replaceChildren(filas.length ? crearTabla([
    { titulo: 'ID', valor: (f) => f.id },
    { titulo: 'Aula', valor: (f) => nombres[f.espacio_id] || f.espacio_id },
    { titulo: 'Inicio', valor: (f) => f.inicio },
    { titulo: 'Fin', valor: (f) => f.fin },
    { titulo: 'Estado', valor: (f) => f.estado, clase: (f) => `celda-${f.estado}` },
    { titulo: 'Costo por hora', valor: (f) => textoTarifa(f.costo) },
    { titulo: 'Total estimado', valor: (f) => textoTotal(f.costo) },
    { titulo: 'Pago', valor: (f) => (f.requiere_pago ? `${f.estado_pago || 'pendiente'} (no verificado)` : 'No aplica') },
    { titulo: 'Observación', valor: (f) => f.bloqueo || '' },
  ], filas) : crearElemento('p', 'estado', 'Aún no tienes solicitudes. Consulta aulas libres y pídela con el asistente.'));
}

async function cargarComercial() {
  const numero = ++cargaComercial;
  mostrarEstado('comercial', 'cargando', 'Consultando tus solicitudes…');
  const fecha = document.getElementById('fecha-comercial');
  if (!fecha.value) fecha.value = fechaLocalHoy();
  try {
    await cargarMisSolicitudesComerciales();
    if (numero === cargaComercial) mostrarEstado('comercial', 'ok', '');
  } catch (error) {
    if (numero === cargaComercial) mostrarEstado('comercial', 'error', `No se pudieron cargar tus solicitudes. ${error.message}`);
  }
}

function pedirConAsistente(aula, consulta) {
  activarPestana('grilla');
  const entrada = document.getElementById('entrada-chat');
  entrada.value = `Solicito ${aula.nombre} el ${consulta.fecha} de ${consulta.inicio} a ${consulta.fin} `
    + `para ${consulta.personas} personas. Motivo: `;
  entrada.focus();
}

async function consultarAulasComerciales(evento) {
  evento.preventDefault();
  const consulta = {
    fecha: document.getElementById('fecha-comercial').value,
    inicio: document.getElementById('inicio-comercial').value,
    fin: document.getElementById('fin-comercial').value,
    personas: document.getElementById('personas-comercial').value,
  };
  const resultado = document.getElementById('resultado-comercial');
  const lista = document.getElementById('aulas-comerciales');
  resultado.className = 'resultado estado-cargando';
  resultado.textContent = 'Buscando aulas libres…';
  lista.replaceChildren();
  try {
    const parametros = new URLSearchParams({
      inicio: `${consulta.fecha}T${consulta.inicio}`, fin: `${consulta.fecha}T${consulta.fin}`, personas: consulta.personas,
    });
    const aulas = await pedir(`/disponibilidad?${parametros}`);
    if (!Array.isArray(aulas)) throw new Error('Respuesta no reconocida.');
    aulas.forEach((aula) => {
      const tarjeta = crearElemento('article', 'tarjeta-propuesta tarjeta-aula');
      tarjeta.appendChild(crearElemento('h4', '', aula.nombre));
      tarjeta.appendChild(crearElemento('p', '', `Aforo ${aula.aforo} · ${aula.tipo}`));
      tarjeta.appendChild(crearElemento('p', 'precio', `Costo por hora: ${textoTarifa(aula.costo)}`));
      tarjeta.appendChild(crearElemento('p', '', `Total estimado: ${textoTotal(aula.costo)}`));
      const boton = crearElemento('button', '', 'Pedir con el asistente');
      boton.type = 'button';
      boton.addEventListener('click', () => pedirConAsistente(aula, consulta));
      tarjeta.appendChild(boton);
      lista.appendChild(tarjeta);
    });
    resultado.className = `resultado estado-${aulas.length ? 'ok' : 'vacio'}`;
    resultado.textContent = aulas.length
      ? `${aulas.length} aula(s) libre(s). Las franjas académicas prioritarias no se ofrecen.`
      : 'No hay aulas libres en esa franja. Prueba otro horario.';
  } catch (error) {
    resultado.className = 'resultado estado-error';
    resultado.textContent = error.message;
  }
}

cargadores.comercial = cargarComercial;
document.getElementById('form-disponibilidad-comercial').addEventListener('submit', consultarAulasComerciales);
document.getElementById('actualizar-comercial').addEventListener('click', () => cargarComercial());
pedir('/sesion').then((sesion) => {
  document.getElementById('tab-comercial').hidden = !ROLES_COMERCIALES.includes(sesion.rol);
}).catch(() => {});
