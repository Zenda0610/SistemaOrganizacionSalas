// Operaciones mínimas; la autorización y las transacciones residen en el servidor.
let operacionEnCurso = false;
let operacionIncierta = false;
let cargaOperaciones = 0;

function campoOperacion(form, titulo, valores, seleccionado) {
  const label = crearElemento('label', '', titulo);
  const select = crearElemento('select');
  valores.forEach((valor) => {
    const opcion = crearElemento('option', '', valor);
    opcion.value = valor;
    select.appendChild(opcion);
  });
  select.value = seleccionado || valores[0];
  label.appendChild(select);
  form.appendChild(label);
  return select;
}

async function mutarOperacion(ruta, cuerpo, validar) {
  if (operacionEnCurso || operacionIncierta) return false;
  operacionEnCurso = true;
  document.querySelectorAll('#operaciones button').forEach((b) => { b.disabled = true; });
  try {
    const resultado = await pedir(ruta, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      ...(cuerpo ? { body: JSON.stringify(cuerpo) } : {}) });
    if (!validar(resultado)) throw errorResultadoDesconocido('Respuesta sin confirmación válida.');
    await cargarOperaciones();
    cargadosPorPestana.delete('grilla');
    cargadosPorPestana.delete('espacios');
    mostrarEstado('operaciones', 'ok', 'Operación confirmada por el servidor.');
    return true;
  } catch (error) {
    // Los errores de negocio JSON conocidos son rechazos; red/contrato/500 son inciertos.
    operacionIncierta = !error.codigo || error.codigo === 'error_interno_servidor';
    mostrarEstado('operaciones', 'error', operacionIncierta
      ? 'Resultado desconocido. Pulsa Consultar estado y revisa las listas antes de repetir. No se reenvió la operación.' : error.message);
    return false;
  } finally {
    operacionEnCurso = false;
    document.querySelectorAll('#operaciones button').forEach((b) => { b.disabled = operacionIncierta; });
    document.getElementById('actualizar-operaciones').disabled = false;
  }
}

async function cargarOperaciones() {
  const numero = ++cargaOperaciones;
  mostrarEstado('operaciones', 'cargando', 'Consultando estado…');
  try {
    const [sesion, aulas, equipos, incidencias] = await Promise.all([
      pedir('/sesion'), pedir('/espacios'), pedir('/equipos'), pedir('/incidencias'),
    ]);
    const puedePrestar = ['profesor', 'administrativo', 'coordinadora'].includes(sesion.rol);
    const prestamos = puedePrestar ? await pedir('/prestamos') : [];
    if (numero !== cargaOperaciones) return;
    if (![aulas, equipos, incidencias, prestamos].every(Array.isArray)) throw new Error('Listado no válido.');
    const coordinadora = sesion.rol === 'coordinadora';
    document.getElementById('form-equipo').hidden = !coordinadora;
    const selector = document.getElementById('recurso-incidencia');
    const anterior = selector.value;
    selector.replaceChildren();
    const nombres = {};
    [['aula', aulas], ['equipo', equipos]].forEach(([tipo, lista]) => lista.forEach((r) => {
      const valor = JSON.stringify([tipo, r.id]);
      nombres[valor] = r.nombre;
      const opcion = crearElemento('option', '', `${tipo}: ${r.nombre}${r.ficticio ? ' (FICTICIO)' : ''}`);
      opcion.value = valor;
      selector.appendChild(opcion);
    }));
    if (nombres[anterior]) selector.value = anterior;
    const lista = document.getElementById('lista-incidencias');
    lista.replaceChildren();
    if (!incidencias.length) lista.appendChild(crearElemento('p', '', 'Sin incidencias registradas para esta identidad.'));
    incidencias.forEach((i) => {
      const tarjeta = crearElemento('article', 'tarjeta-propuesta');
      tarjeta.appendChild(crearElemento('h3', '', `Incidencia ${i.id} · ${nombres[JSON.stringify([i.recurso_tipo, i.recurso_id])] || i.recurso_id}`));
      tarjeta.appendChild(crearElemento('p', '', i.descripcion));
      const estados = { pendiente_clasificacion: 'Pendiente de clasificación', pendiente_revision: 'Clasificación propuesta por IA · Pendiente de revisión humana',
        bloqueo_confirmado: 'Bloqueo confirmado', revisada_sin_bloqueo: 'Revisada sin bloqueo' };
      tarjeta.appendChild(crearElemento('p', '', `${estados[i.estado] || i.estado} · Reportada por ${i.reportada_por}`));
      tarjeta.appendChild(crearElemento('p', '', i.categoria ? `${i.categoria} · Prioridad ${i.prioridad} · ${i.area}: ${i.justificacion}` : 'Pendiente de clasificación: revisión humana necesaria.'));
      if (i.afectados) Object.entries(i.afectados).forEach(([tipo, filas]) => {
        const titulo = { reservas: 'Reservas afectadas', sesiones: 'Sesiones afectadas', prestamos: 'Préstamos afectados' }[tipo] || tipo;
        tarjeta.appendChild(crearElemento('p', '', `${titulo} (sin cancelación automática): ${filas.length ? filas.map((f) => `#${f.id} ${f.inicio || f.fecha || ''} ${f.fin || f.hora_fin || ''}`).join('; ') : 'sin registros activos'}`));
      });
      if (i.revisada_por) tarjeta.appendChild(crearElemento('p', '', `Revisada por ${i.revisada_por} · ${i.revisada_en}`));
      if (coordinadora && !i.revisada_por) {
        const form = crearElemento('form');
        const categoria = campoOperacion(form, 'Categoría', ['infraestructura', 'tecnologia', 'limpieza', 'seguridad', 'otra'], i.categoria);
        const prioridad = campoOperacion(form, 'Prioridad (no implica bloqueo)', ['baja', 'media', 'alta', 'critica'], i.prioridad);
        const area = campoOperacion(form, 'Área responsable', ['mantenimiento', 'soporte', 'servicios_generales', 'coordinacion'], i.area);
        const label = crearElemento('label', '', 'Justificación de la revisión');
        const texto = crearElemento('textarea'); texto.required = true; texto.minLength = 3; texto.maxLength = 400; texto.value = i.justificacion || '';
        label.appendChild(texto); form.appendChild(label);
        const decision = campoOperacion(form, 'Decisión humana', ['Revisar sin bloquear', 'Confirmar bloqueo del recurso']);
        const boton = crearElemento('button', '', 'Confirmar revisión'); boton.type = 'submit'; form.appendChild(boton);
        form.addEventListener('submit', (evento) => {
          evento.preventDefault();
          mutarOperacion(`/incidencias/${i.id}/revisar`, { categoria: categoria.value, prioridad: prioridad.value,
            area: area.value, justificacion: texto.value, bloquear: decision.value === 'Confirmar bloqueo del recurso' },
          (r) => r.id === i.id && Boolean(r.revisada_por) && ['bloqueo_confirmado', 'revisada_sin_bloqueo'].includes(r.estado));
        });
        tarjeta.appendChild(form);
      }
      lista.appendChild(tarjeta);
    });
    const inventario = document.getElementById('lista-equipos'); inventario.replaceChildren();
    if (!equipos.length) inventario.appendChild(crearElemento('p', '', 'Sin inventario cargado. No hay equipos oficiales disponibles para demostrar.'));
    equipos.forEach((e) => {
      const tarjeta = crearElemento('article', 'tarjeta-propuesta');
      tarjeta.appendChild(crearElemento('h4', '', `${e.nombre} · ${e.id}${e.ficticio ? ' · FICTICIO' : ''}`));
      const estado = e.bloqueado ? 'Bloqueo confirmado' : e.estado !== 'disponible' ? e.estado : e.prestado ? 'Prestado' : 'Disponible';
      tarjeta.appendChild(crearElemento('p', '', `${estado}${e.bloqueado && e.prestado ? ' · préstamo activo conservado' : ''}`));
      if (puedePrestar && e.estado === 'disponible' && !e.prestado && !e.bloqueado) {
        const boton = crearElemento('button', '', 'Prestar a mi nombre'); boton.type = 'button';
        boton.addEventListener('click', () => mutarOperacion('/prestamos', { equipo_id: e.id, responsable: sesion.usuario_id },
          (r) => Number.isInteger(r.id) && r.equipo_id === e.id && !r.devuelto_en));
        tarjeta.appendChild(boton);
      }
      inventario.appendChild(tarjeta);
    });
    const historial = document.getElementById('lista-prestamos'); historial.replaceChildren();
    if (!prestamos.length) historial.appendChild(crearElemento('p', '', 'Sin préstamos autorizados para esta identidad.'));
    prestamos.forEach((p) => {
      const tarjeta = crearElemento('article', 'tarjeta-propuesta');
      tarjeta.appendChild(crearElemento('p', '', `#${p.id} · ${p.equipo_id} · Responsable ${p.responsable} · ${p.fecha} · ${p.devuelto_en ? `Devuelto ${p.devuelto_en} por ${p.devuelto_por}` : 'En préstamo'}`));
      if (!p.devuelto_en) {
        const boton = crearElemento('button', '', 'Registrar devolución'); boton.type = 'button';
        boton.addEventListener('click', () => mutarOperacion(`/prestamos/${p.id}/devolver`, null, (r) => r.id === p.id && Boolean(r.devuelto_en)));
        tarjeta.appendChild(boton);
      }
      historial.appendChild(tarjeta);
    });
    const incierta = operacionIncierta;
    operacionIncierta = false;
    document.querySelectorAll('#operaciones button').forEach((b) => { b.disabled = operacionEnCurso; });
    mostrarEstado('operaciones', 'ok', incierta ? 'Estado consultado. Revisa las listas: la petición anterior no se reenvió.' : 'Datos consultados. Identidad de desarrollo; no es autenticación real.');
  } catch (error) {
    if (numero === cargaOperaciones) mostrarEstado('operaciones', 'error', error.message);
    throw error;
  }
}

document.getElementById('actualizar-operaciones').addEventListener('click', () => cargarOperaciones().catch(() => {}));
document.getElementById('form-incidencia').addEventListener('submit', async (evento) => {
  evento.preventDefault();
  const valor = document.getElementById('recurso-incidencia').value;
  if (!valor) return;
  const [tipo, id] = JSON.parse(valor);
  const texto = document.getElementById('texto-incidencia');
  if (await mutarOperacion('/incidencias', { descripcion: texto.value, recurso_tipo: tipo, recurso_id: id },
    (r) => Number.isInteger(r.id) && typeof r.estado === 'string')) texto.value = '';
});
document.getElementById('form-equipo').addEventListener('submit', async (evento) => {
  evento.preventDefault();
  await mutarOperacion('/equipos', { id: document.getElementById('id-equipo').value, nombre: document.getElementById('nombre-equipo').value,
    estado: document.getElementById('estado-equipo').value, ficticio: document.getElementById('ficticio-equipo').checked },
  (r) => typeof r.id === 'string' && typeof r.nombre === 'string');
});
