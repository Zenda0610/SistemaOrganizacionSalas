// Cambiar o cancelar solicitudes propias y revisión de cambios por la coordinadora.
// La factibilidad la decide el servidor; aquí solo se muestran el veredicto y el análisis de IA.
let cambioEnCurso = false;

function resultadoSolicitudes(tipo, texto) {
  const resultado = document.getElementById('resultado-solicitudes');
  resultado.className = `resultado estado-${tipo}`;
  resultado.textContent = texto;
}

function textoDatos(d) {
  return `${nombresAulas[d.espacio_id] || d.espacio_id} · ${d.inicio} → ${d.fin} · ${d.personas} persona(s)`;
}

async function accionCambio(ruta, cuerpo, exito) {
  if (cambioEnCurso) return;
  cambioEnCurso = true;
  resultadoSolicitudes('cargando', 'Enviando…');
  try {
    const respuesta = await pedir(ruta, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      ...(cuerpo ? { body: JSON.stringify(cuerpo) } : {}) });
    await cargarSolicitudes();
    resultadoSolicitudes('ok', exito(respuesta));
  } catch (error) {
    await cargarSolicitudes();
    resultadoSolicitudes('error', `No se aplicó: ${error.message}`);
  } finally {
    cambioEnCurso = false;
  }
}

function abrirEditor(fila) {
  const editor = document.getElementById('editor-solicitud');
  const form = crearElemento('form', 'formulario-fila');
  const campo = (titulo, entrada) => { const l = crearElemento('label', '', titulo); l.appendChild(entrada); form.appendChild(l); return entrada; };
  const entrada = (tipo, valor) => { const e = crearElemento('input'); e.type = tipo; e.value = valor; e.required = true; return e; };
  const fecha = campo('Fecha', entrada('date', fila.inicio.slice(0, 10)));
  const inicio = campo('Inicio', entrada('time', fila.inicio.slice(11)));
  const fin = campo('Fin', entrada('time', fila.fin.slice(11)));
  const personas = campo('Personas', entrada('number', fila.personas));
  const aula = campo('Aula', crearElemento('select'));
  Object.entries(nombresAulas).forEach(([id, nombre]) => {
    const opcion = crearElemento('option', '', nombre);
    opcion.value = id;
    aula.appendChild(opcion);
  });
  aula.value = fila.espacio_id;
  const enviar = crearElemento('button', '', fila.estado === 'aprobada' ? 'Pedir cambio a coordinación' : 'Guardar cambios');
  enviar.type = 'submit';
  const cerrar = crearElemento('button', '', 'Cerrar');
  cerrar.type = 'button';
  cerrar.addEventListener('click', () => { editor.hidden = true; });
  form.append(enviar, cerrar);
  form.addEventListener('submit', (evento) => {
    evento.preventDefault();
    // Fin anterior al inicio: el intervalo cruza medianoche.
    const finFecha = fin.value <= inicio.value ? diaVecino(fecha.value, 1) : fecha.value;
    const cuerpo = { espacio_id: aula.value, inicio: `${fecha.value}T${inicio.value}`, fin: `${finFecha}T${fin.value}`, personas: Number(personas.value) };
    editor.hidden = true;
    accionCambio(`/solicitudes/${fila.id}/cambios`, cuerpo, (r) => (r.tipo === 'edicion'
      ? `Solicitud #${fila.id} actualizada; sigue pendiente de aprobación.`
      : `Cambio #${r.cambio.id} enviado a coordinación (${r.cambio.factible ? 'factible' : 'no factible: ' + r.cambio.motivos.join(' ')}). Tu reserva actual sigue vigente.`));
  });
  const titulo = crearElemento('h3', '', `Cambiar solicitud #${fila.id} (${fila.estado})`);
  editor.replaceChildren(titulo, form);
  editor.hidden = false;
  fecha.focus();
}

// Llamado desde cargarSolicitudes: botones para las solicitudes futuras propias.
function agregarAccionesTitular(tabla, filas, sesion) {
  if (sesion.rol === 'coordinadora') return;
  const ahora = new Date();
  const futura = (f) => new Date(f.inicio.replace(' ', 'T')) > ahora;
  tabla.querySelector('thead').querySelector('tr').appendChild(crearElemento('th', '', 'Acción'));
  const cuerpo = tabla.querySelector('tbody');
  filas.forEach((fila, indice) => {
    const celda = crearElemento('td');
    if (fila.solicitante_id === sesion.usuario_id && ['pendiente', 'aprobada'].includes(fila.estado) && futura(fila)) {
      const cambiar = crearElemento('button', '', 'Cambiar');
      cambiar.type = 'button';
      cambiar.addEventListener('click', () => abrirEditor(fila));
      const cancelar = crearElemento('button', '', 'Cancelar');
      cancelar.type = 'button';
      cancelar.addEventListener('click', () => {
        const aviso = fila.estado === 'aprobada' ? ' La franja se liberará de inmediato.' : '';
        if (!window.confirm(`¿Cancelar la solicitud #${fila.id}?${aviso}`)) return;
        accionCambio(`/solicitudes/${fila.id}/cancelar`, null, () => `Solicitud #${fila.id} cancelada.`);
      });
      celda.append(cambiar, cancelar);
    }
    cuerpo.children[indice].appendChild(celda);
  });
}

function tarjetaCambio(cambio) {
  const tarjeta = crearElemento('article', 'tarjeta-propuesta tarjeta-cambio');
  tarjeta.appendChild(crearElemento('h4', '', `Cambio #${cambio.id} · reserva #${cambio.solicitud_id} · ${cambio.creado_por} · ${cambio.estado}`));
  tarjeta.appendChild(crearElemento('p', '', `Antes: ${textoDatos(cambio.datos_antes)}`));
  tarjeta.appendChild(crearElemento('p', '', `Después: ${textoDatos(cambio.datos_despues)}`));
  tarjeta.appendChild(crearElemento('p', cambio.factible ? 'veredicto-ok' : 'veredicto-no',
    cambio.factible ? 'Veredicto del servidor: factible' : `Veredicto del servidor: no factible · ${cambio.motivos.join(' ')}`));
  tarjeta.appendChild(crearElemento('p', 'analisis-ia', `Análisis de IA: ${cambio.analisis_ia}`));
  if (cambio.motivo_descarte) tarjeta.appendChild(crearElemento('p', '', `Motivo del descarte: ${cambio.motivo_descarte}`));
  if (cambio.estado === 'pendiente') {
    const acciones = crearElemento('div', 'pie-chat');
    const motivo = crearElemento('input');
    motivo.placeholder = 'Motivo para descartar';
    motivo.maxLength = 300;
    motivo.setAttribute('aria-label', `Motivo para descartar el cambio ${cambio.id}`);
    const descartar = crearElemento('button', '', 'Descartar');
    descartar.type = 'button';
    descartar.addEventListener('click', () => {
      if (motivo.value.trim().length < 3) { resultadoSolicitudes('error', 'Escribe un motivo de al menos 3 caracteres para descartar.'); return; }
      accionCambio(`/cambios/${cambio.id}/descartar`, { motivo: motivo.value }, () => `Cambio #${cambio.id} descartado. La reserva no cambió.`);
    });
    const aprobar = crearElemento('button', '', 'Aprobar cambio');
    aprobar.type = 'submit';
    aprobar.addEventListener('click', () => accionCambio(`/cambios/${cambio.id}/aprobar`, null,
      () => `Cambio #${cambio.id} aprobado y aplicado a la reserva.`));
    acciones.append(motivo, descartar, aprobar);
    tarjeta.appendChild(acciones);
  }
  return tarjeta;
}

// Llamado desde cargarSolicitudes para la coordinadora.
async function cargarCambios(sesion) {
  const seccion = document.getElementById('cambios-por-revisar');
  seccion.hidden = sesion.rol !== 'coordinadora';
  if (seccion.hidden) return;
  const lista = document.getElementById('lista-cambios');
  try {
    const cambiosLista = await pedir('/cambios');
    lista.replaceChildren(...(cambiosLista.length ? cambiosLista.map(tarjetaCambio)
      : [crearElemento('p', 'estado', 'No hay cambios por revisar.')]));
  } catch (error) {
    lista.replaceChildren(crearElemento('p', 'estado estado-error', `No se pudieron cargar los cambios. ${error.message}`));
  }
}
