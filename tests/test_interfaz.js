// Pruebas de la recarga en la interfaz, sin navegador.
// Ejecuta static/app.js con un DOM y un fetch simulados.
// Uso: node tests/test_interfaz.js
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const codigoInterfaz = fs.readFileSync(path.join(__dirname, "..", "static", "app.js"), "utf8");

function crearElemento(etiqueta = "div") {
  return {
    etiqueta, children: [], listeners: {}, style: {},
    className: "", textContent: "", disabled: false, options: [], value: "",
    classList: { toggle() {} },
    addEventListener(nombre, fn) { this.listeners[nombre] = fn; },
    appendChild(hijo) {
      this.children.push(hijo);
      if (this.etiqueta === "select") {
        this.options.push(hijo);
        if (!this.value) this.value = hijo.value;
      }
      return hijo;
    },
    replaceChildren(...hijos) {
      this.children = [];
      if (this.etiqueta === "select") { this.options = []; this.value = ""; }
      hijos.forEach((h) => this.appendChild(h));
    },
    querySelector(selector) {
      for (const hijo of this.children) {
        if (hijo.etiqueta === selector) return hijo;
        const encontrado = hijo.querySelector && hijo.querySelector(selector);
        if (encontrado) return encontrado;
      }
      return null;
    },
  };
}

function respuestaJson(status, cuerpo) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo };
}

function respuestaNoJson(status) {
  return { ok: status >= 200 && status < 300, status, json: async () => { throw new SyntaxError("no es JSON"); } };
}

// Carga la interfaz; `respuestaImportacion` decide qué devuelve POST /api/datos/recargar.
function cargarInterfaz(respuestaImportacion) {
  const elementos = {};
  const documento = {
    querySelectorAll: () => [],
    querySelector: (selector) => (elementos[selector] = elementos[selector] || crearElemento()),
    getElementById: (id) => (elementos[id] = elementos[id] || crearElemento(id === "selector-fecha" ? "select" : "div")),
    createElement: (etiqueta) => crearElemento(etiqueta),
    createDocumentFragment: () => crearElemento(),
  };
  const contexto = {
    document: documento,
    console,
    Option: function Option(texto, valor) { return { textContent: texto, value: valor }; },
    fetch: async (url, opciones = {}) => {
      if (opciones.method === "POST") {
        contexto.ultimoCuerpo = opciones.body;
        return respuestaImportacion();
      }
      if (url.endsWith("/sesion")) return respuestaJson(200, { usuario_id: "dev-prueba", rol: "coordinadora", origen: "desarrollo" });
      return respuestaJson(200, []);
    },
  };
  vm.createContext(contexto);
  vm.runInContext(codigoInterfaz, contexto);
  return { contexto, elementos, banner: () => elementos["resultado-importacion"].textContent };
}

// Respuesta 200 cuyo cuerpo no cumple el contrato de éxito: el resultado es desconocido.
function casoContratoInvalido(nombre, cuerpo) {
  return {
    nombre: `contrato inválido (${nombre}): resultado desconocido, sin éxito`,
    respuesta: () => respuestaJson(200, cuerpo),
    esperado: (texto) => {
      assert.match(texto, /No se pudo confirmar/);
      assert.match(texto, /última importación/);
      assert.doesNotMatch(texto, /Importación correcta/);
      assert.doesNotMatch(texto, /conservaron/);
    },
  };
}

const casos = [
  {
    nombre: "error confirmado del servidor: se indica que no se aplicó y que se conservaron los datos",
    respuesta: () => respuestaJson(422, { mensaje: "falta espacios.csv", codigo: "archivo_ausente", archivo: "espacios.csv" }),
    esperado: (texto) => {
      assert.match(texto, /no se aplicó/);
      assert.match(texto, /Se conservaron los datos anteriores/);
    },
  },
  {
    nombre: "error de red: el resultado es desconocido y no se afirma conservación",
    respuesta: () => { throw new TypeError("Failed to fetch"); },
    esperado: (texto) => {
      assert.match(texto, /No se pudo confirmar/);
      assert.doesNotMatch(texto, /conservaron/);
      assert.match(texto, /última importación/);
    },
  },
  {
    nombre: "respuesta 200 que no es JSON: resultado desconocido",
    respuesta: () => respuestaNoJson(200),
    esperado: (texto) => {
      assert.match(texto, /No se pudo confirmar/);
      assert.doesNotMatch(texto, /conservaron/);
    },
  },
  {
    nombre: "500 sin código conocido: resultado desconocido",
    respuesta: () => respuestaJson(500, { mensaje: "Error interno del servidor.", codigo: "error_interno_servidor" }),
    esperado: (texto) => {
      assert.match(texto, /No se pudo confirmar/);
      assert.doesNotMatch(texto, /conservaron/);
    },
  },
  {
    nombre: "error de escritura confirmado por el servidor: se indica que se conservaron los datos",
    respuesta: () => respuestaJson(500, { mensaje: "No se pudo guardar la importación", codigo: "error_escritura" }),
    esperado: (texto) => {
      assert.match(texto, /no se aplicó/);
      assert.match(texto, /Se conservaron los datos anteriores/);
    },
  },
  {
    nombre: "importación correcta con el contrato completo",
    respuesta: () => respuestaJson(200, { ok: true, cargados: { "espacios.csv": 10 }, conflictos: 5 }),
    esperado: (texto) => {
      assert.match(texto, /Importación correcta/);
      assert.match(texto, /"espacios\.csv":10/);
      assert.match(texto, /Conflictos: 5/);
      assert.doesNotMatch(texto, /undefined/);
    },
  },
  {
    nombre: "sin identidad (401): se indica que no se aplicó y que se conservaron los datos",
    respuesta: () => respuestaJson(401, { mensaje: "Sin identidad.", codigo: "sin_identidad" }),
    esperado: (texto) => {
      assert.match(texto, /no se aplicó \(sin_identidad\)/);
      assert.match(texto, /Se conservaron los datos anteriores/);
    },
  },
  {
    nombre: "sin permiso (403): se indica que no se aplicó y que se conservaron los datos",
    respuesta: () => respuestaJson(403, { mensaje: "Sin permiso.", codigo: "sin_permiso" }),
    esperado: (texto) => {
      assert.match(texto, /no se aplicó \(sin_permiso\)/);
      assert.match(texto, /Se conservaron los datos anteriores/);
    },
  },
  {
    nombre: "reserva incompatible (409): se indica que no se aplicó y que se conservaron los datos",
    respuesta: () => respuestaJson(409, { mensaje: "La importación se canceló.", codigo: "reserva_incompatible", archivo: "sesiones.csv" }),
    esperado: (texto) => {
      assert.match(texto, /no se aplicó \(reserva_incompatible\)/);
      assert.match(texto, /Se conservaron los datos anteriores/);
    },
  },
  casoContratoInvalido("cuerpo {}", {}),
  casoContratoInvalido("cuerpo []", []),
  casoContratoInvalido("cuerpo null", null),
  casoContratoInvalido("ok:false con 200", { ok: false, cargados: { "espacios.csv": 10 }, conflictos: 0 }),
  casoContratoInvalido("ok ausente", { cargados: { "espacios.csv": 10 }, conflictos: 0 }),
  casoContratoInvalido("cargados ausente", { ok: true, conflictos: 0 }),
  casoContratoInvalido("cargados es un array", { ok: true, cargados: [10], conflictos: 0 }),
  casoContratoInvalido("conteo negativo", { ok: true, cargados: { "espacios.csv": -1 }, conflictos: 0 }),
  casoContratoInvalido("conteo decimal", { ok: true, cargados: { "espacios.csv": 1.5 }, conflictos: 0 }),
  casoContratoInvalido("conteo como texto", { ok: true, cargados: { "espacios.csv": "10" }, conflictos: 0 }),
  casoContratoInvalido("conflictos ausente", { ok: true, cargados: { "espacios.csv": 10 } }),
  casoContratoInvalido("conflictos negativo", { ok: true, cargados: { "espacios.csv": 10 }, conflictos: -2 }),
  casoContratoInvalido("conflictos como texto", { ok: true, cargados: { "espacios.csv": 10 }, conflictos: "5" }),
];

(async () => {
  let fallos = 0;
  for (const caso of casos) {
    const interfaz = cargarInterfaz(caso.respuesta);
    try {
      await vm.runInContext("recargarDatos()", interfaz.contexto);
      caso.esperado(interfaz.banner());
      console.log("ok   -", caso.nombre);
    } catch (error) {
      fallos += 1;
      console.log("FAIL -", caso.nombre, "\n     ", error.message.split("\n")[0], "\n      banner:", interfaz.banner());
    }
  }
  // Días ocupados por una reserva: medianoche cuenta como dos días; 00:00 final no ocupa el siguiente.
  const auxiliares = cargarInterfaz(() => respuestaJson(200, {}));
  const dias = vm.runInContext(
    'JSON.stringify([fechasDeReserva({inicio:"2026-10-20 22:00", fin:"2026-10-21 02:00"}), fechasDeReserva({inicio:"2026-10-20 22:00", fin:"2026-10-21 00:00"})])',
    auxiliares.contexto);
  try {
    assert.deepStrictEqual(JSON.parse(dias), [["2026-10-20", "2026-10-21"], ["2026-10-20"]]);
    console.log("ok   - una reserva que cruza medianoche ocupa dos días; a las 00:00 no ocupa el siguiente");
  } catch (error) {
    fallos += 1;
    console.log("FAIL - días de reserva\n     ", error.message.split("\n")[0]);
  }
  // Ocupación visual: franjas por día, reservas nocturnas, multidía, cancelaciones y conflictos.
  const aux = cargarInterfaz(() => respuestaJson(200, {}));
  const bloques = (fecha, sesiones, reservas) => JSON.parse(vm.runInContext(
    `JSON.stringify(bloquesDelDia(${JSON.stringify(fecha)}, ${JSON.stringify(sesiones)}, ${JSON.stringify(reservas)}))`,
    aux.contexto));
  const fechas = (reserva) => JSON.parse(vm.runInContext(`JSON.stringify(fechasDeReserva(${JSON.stringify(reserva)}))`, aux.contexto));
  const prueba = (nombre, fn) => {
    try {
      fn();
      console.log("ok   -", nombre);
    } catch (error) {
      fallos += 1;
      console.log("FAIL -", nombre, "\n     ", error.message.split("\n")[0]);
    }
  };
  const nocturna = { id: 1, espacio_id: "E01", inicio: "2026-10-20 22:00", fin: "2026-10-21 02:00", tipo: "academica" };
  const varios = { id: 2, espacio_id: "E01", inicio: "2026-11-02 20:00", fin: "2026-11-05 06:00", tipo: "comercial" };
  const franjas = (lista) => lista.map((b) => [b.inicio, b.fin]);

  prueba("reserva nocturna: 22:00–24:00 el primer día y 00:00–02:00 el siguiente", () => {
    assert.deepStrictEqual(franjas(bloques("2026-10-20", [], [nocturna])), [[1320, 1440]]);
    assert.deepStrictEqual(franjas(bloques("2026-10-21", [], [nocturna])), [[0, 120]]);
    assert.deepStrictEqual(bloques("2026-10-22", [], [nocturna]), []);
  });
  prueba("reserva de varios días ocupa cada día, completo en los intermedios", () => {
    assert.deepStrictEqual(franjas(bloques("2026-11-02", [], [varios])), [[1200, 1440]]);
    assert.deepStrictEqual(franjas(bloques("2026-11-03", [], [varios])), [[0, 1440]]);
    assert.deepStrictEqual(franjas(bloques("2026-11-04", [], [varios])), [[0, 1440]]);
    assert.deepStrictEqual(franjas(bloques("2026-11-05", [], [varios])), [[0, 360]]);
    assert.deepStrictEqual(bloques("2026-11-06", [], [varios]), []);
  });
  prueba("los días de una reserva de varios días se añaden todos al selector", () => {
    assert.deepStrictEqual(fechas(varios), ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"]);
  });
  prueba("una reserva que termina a las 00:00 no ocupa el día siguiente", () => {
    const hasta_medianoche = { ...nocturna, fin: "2026-10-21 00:00" };
    assert.deepStrictEqual(fechas(hasta_medianoche), ["2026-10-20"]);
    assert.deepStrictEqual(bloques("2026-10-21", [], [hasta_medianoche]), []);
  });
  prueba("una sesión cancelada no ocupa franjas; una programada sí", () => {
    const sesion = { id: "S1", espacio_id: "E01", fecha: "2026-10-20", hora_inicio: "08:00", hora_fin: "10:00", area: "software", tipo: "clase", estado: "cancelada" };
    assert.deepStrictEqual(bloques("2026-10-20", [sesion], []), []);
    assert.deepStrictEqual(franjas(bloques("2026-10-20", [{ ...sesion, estado: "programada" }], [])), [[480, 600]]);
  });
  prueba("reservas consecutivas no se marcan como conflicto", () => {
    const a = { id: 3, espacio_id: "E01", inicio: "2026-11-02 08:00", fin: "2026-11-02 09:00", tipo: "academica" };
    const b = { id: 4, espacio_id: "E01", inicio: "2026-11-02 09:00", fin: "2026-11-02 10:00", tipo: "academica" };
    assert.ok(bloques("2026-11-02", [], [a, b]).every((x) => x.enConflicto === false));
  });
  prueba("una sesión programada y una reserva solapadas se marcan en conflicto", () => {
    const sesion = { id: "S2", espacio_id: "E01", fecha: "2026-11-02", hora_inicio: "09:00", hora_fin: "10:00", area: "software", tipo: "clase", estado: "programada" };
    const reserva = { id: 5, espacio_id: "E01", inicio: "2026-11-02 08:30", fin: "2026-11-02 09:30", tipo: "academica" };
    assert.ok(bloques("2026-11-02", [sesion], [reserva]).every((x) => x.enConflicto === true));
  });
  // Render de la grilla con un DOM mínimo: 24 horas en franjas de 15 minutos y bloques de reserva.
  const nodo = (etiqueta) => ({
    etiqueta, className: "", textContent: "", title: "", style: {}, hijos: [],
    appendChild(hijo) { this.hijos.push(hijo); return hijo; },
    replaceChildren(...nodos) { this.hijos = nodos; },
    querySelector(selector) { return this.hijos.find((h) => h.etiqueta === selector); },
  });
  const pintar = (fecha, sesiones, reservas) => {
    const tabla = nodo("table");
    const grilla = cargarInterfaz(() => respuestaJson(200, {}));
    grilla.contexto.document.getElementById = () => tabla;
    grilla.contexto.document.createElement = nodo;
    Object.assign(grilla.contexto, { espacios: [{ id: "E01", nombre: "Auditorio", aforo: 100 }], sesiones, reservas, fecha });
    vm.runInContext("construirGrilla(espacios, sesiones, reservas, fecha)", grilla.contexto);
    return tabla.hijos.find((h) => h.etiqueta === "tbody").hijos;
  };
  const bloquesEnCelda = (filas, indiceFila) => filas[indiceFila].hijos[1].hijos;

  prueba("la grilla cubre 24 horas en franjas de 15 minutos", () => {
    assert.strictEqual(pintar("2026-10-20", [], []).length, 96);
  });
  prueba("la reserva nocturna se dibuja de 22:00 a 24:00 con su altura, y de 00:00 a 02:00 al día siguiente", () => {
    const filas = pintar("2026-10-20", [], [nocturna]);
    const bloque = bloquesEnCelda(filas, 88)[0];   // 22:00 = fila 88
    assert.ok(bloque.className.includes("reserva"));
    assert.strictEqual(bloque.style.height, "174px");  // 8 franjas de 22 px menos 2 px
    const siguiente = pintar("2026-10-21", [], [nocturna]);
    assert.ok(bloquesEnCelda(siguiente, 0)[0].className.includes("reserva"));
  });
  prueba("una sesión cancelada no se dibuja como ocupación", () => {
    const cancelada = { id: "S9", espacio_id: "E01", fecha: "2026-10-20", hora_inicio: "08:00", hora_fin: "10:00", area: "software", tipo: "clase", estado: "cancelada" };
    assert.strictEqual(bloquesEnCelda(pintar("2026-10-20", [cancelada], []), 32).length, 0);
  });
  // Chat: el texto de error o de éxito viene del servidor y se muestra tal cual.
  let ultimoCuerpoChat = null;
  const chatCon = async (respuestaChat) => {
    const interfaz = cargarInterfaz(respuestaChat);
    interfaz.contexto.document.getElementById("entrada-chat").value = "reserve el auditorio";
    await vm.runInContext("enviarChat({ preventDefault() {} })", interfaz.contexto);
    ultimoCuerpoChat = JSON.parse(interfaz.contexto.ultimoCuerpo);
    return interfaz.contexto.document.getElementById("respuesta-chat").textContent;
  };
  try {
    const texto = await chatCon(() => respuestaJson(503, { mensaje: "La IA no está disponible en este momento. No se ejecutó ninguna acción.", codigo: "ia_no_disponible" }));
    assert.match(texto, /No se ejecutó ninguna acción/);
    console.log("ok   - chat: IA no disponible se muestra sin ejecutar acciones");
  } catch (error) {
    fallos += 1;
    console.log("FAIL - chat IA no disponible\n     ", error.message.split("\n")[0]);
  }
  try {
    const texto = await chatCon(() => respuestaJson(200, { estado: "solicitud_creada", respuesta: "Solicitud 7 creada en estado pendiente (academica).", datos: [] }));
    assert.strictEqual(texto, "Solicitud 7 creada en estado pendiente (academica).");
    assert.strictEqual(ultimoCuerpoChat.mensaje, "reserve el auditorio");
    assert.ok(ultimoCuerpoChat.conversacion_id.length >= 8);
    console.log("ok   - chat: solicitud creada se muestra con el texto del servidor");
  } catch (error) {
    fallos += 1;
    console.log("FAIL - chat solicitud creada\n     ", error.message.split("\n")[0]);
  }
  // La sesión muestra la identidad de desarrollo y el aviso de que no es autenticación.
  const sesion = cargarInterfaz(() => respuestaJson(200, {}));
  await vm.runInContext("cargarSesion()", sesion.contexto);
  try {
    assert.match(sesion.elementos["aviso-sesion"].textContent, /USUARIO DE DESARROLLO: dev-prueba \(rol coordinadora\)\. No es autenticación\./);
    console.log("ok   - la sesión muestra usuario de desarrollo y aviso");
  } catch (error) {
    fallos += 1;
    console.log("FAIL - la sesión muestra usuario de desarrollo y aviso\n     ", error.message.split("\n")[0]);
  }
  // Panel de solicitudes: DOM con hijos y eventos; las respuestas HTTP siguen siendo simuladas.
  const pruebaAsync = async (nombre, fn) => {
    try { await fn(); console.log("ok   -", nombre); }
    catch (error) { fallos += 1; console.log("FAIL -", nombre, "\n     ", error.stack); }
  };
  const textoNodo = (n) => [n.textContent, ...(n.children || []).map(textoNodo)].join(" ");
  const botonesNodo = (n) => (n.etiqueta === "button" ? [n] : (n.children || []).flatMap(botonesNodo));
  const escenario = async (rol = "coordinadora", opciones = {}) => {
    const vista = cargarInterfaz(() => respuestaJson(200, {}));
    await new Promise(setImmediate);  // terminar las cargas de arranque antes de fijar el escenario
    const llamadas = [];
    let aprobada = false;
    const solicitud = { id: 7, espacio_id: "E07", inicio: "2026-11-02 06:00", fin: "2026-11-02 08:00",
      hora_devolucion: "2026-11-02 07:55", personas: 8, descripcion: "Clase de SER", tipo: "academica", estado: "pendiente", solicitante_id: "dev-profesor",
      ...opciones.solicitud };
    vista.contexto.fetch = async (url, config = {}) => {
      llamadas.push([url, config.method || "GET"]);
      if (url === "/api/solicitudes/7/aprobar") {
        if (opciones.errorTrasAplicar) aprobada = true;
        if (opciones.error) return opciones.error();
        aprobada = true;
        return respuestaJson(200, { ...solicitud, estado: "aprobada" });
      }
      if (url === "/api/solicitudes") {
        if (aprobada && opciones.errorRefresco) throw new TypeError("red caída al refrescar");
        return respuestaJson(200, [{ ...solicitud, estado: aprobada ? "aprobada" : "pendiente" }]);
      }
      if (url === "/api/sesion") return respuestaJson(200, { usuario_id: "dev-prueba", rol });
      if (url === "/api/espacios") return respuestaJson(200, [{ id: "E07", nombre: "Sala Blanca", aforo: 12 }]);
      if (url.startsWith("/api/reservas")) return respuestaJson(200, aprobada ? [solicitud] : []);
      if (url === "/api/chat") return respuestaJson(200, { estado: "solicitud_creada", respuesta: "Solicitud creada", datos: [] });
      return respuestaJson(200, []);
    };
    return { ...vista, llamadas, solicitud };
  };
  await pruebaAsync("solicitudes: coordinadora aprueba desde el botón y refresca lista, grilla y fecha nueva", async () => {
    const vista = await escenario();
    const selector = vista.contexto.document.getElementById("selector-fecha");
    selector.appendChild(new vista.contexto.Option("2026-10-01", "2026-10-01"));
    await vm.runInContext("cargarSolicitudes()", vista.contexto);
    const boton = botonesNodo(vista.elementos["solicitudes-registradas"])[0];
    assert.strictEqual(boton.textContent, "Aprobar");
    const primera = boton.listeners.click();
    await boton.listeners.click(); // un segundo clic en curso no repite el POST
    await primera;
    assert.strictEqual(vista.llamadas.filter(([url]) => url.endsWith("/aprobar")).length, 1);
    assert.match(vista.elementos["resultado-solicitudes"].textContent, /Solicitud 7 aprobada/);
    assert.match(textoNodo(vista.elementos["solicitudes-registradas"]), /aprobada/);
    assert.strictEqual(botonesNodo(vista.elementos["solicitudes-registradas"]).length, 0);
    assert.strictEqual(selector.value, "2026-11-02");
    assert.ok(selector.options.some((o) => o.value === "2026-11-02"));
    assert.strictEqual(vista.elementos["#grilla .estado"].className, "estado estado-ok");
    assert.match(textoNodo(vista.elementos["reservas-aprobadas"]), /Devolución/);
    assert.match(textoNodo(vista.elementos["reservas-aprobadas"]), /2026-11-02 07:55/);
  });
  await pruebaAsync("solicitudes: tabla muestra hora_devolucion y profesor no tiene botón Aprobar", async () => {
    const vista = await escenario("profesor");
    await vm.runInContext("cargarSolicitudes()", vista.contexto);
    assert.match(textoNodo(vista.elementos["solicitudes-registradas"]), /Devolución anticipada/);
    assert.match(textoNodo(vista.elementos["solicitudes-registradas"]), /2026-11-02 07:55/);
    assert.match(textoNodo(vista.elementos["solicitudes-registradas"]), /Sala Blanca/);
    assert.match(textoNodo(vista.elementos["solicitudes-registradas"]), /Clase de SER/);
    assert.strictEqual(botonesNodo(vista.elementos["solicitudes-registradas"]).length, 0);
  });
  await pruebaAsync("solicitudes: comercial indica pago pendiente sin verificar", async () => {
    const vista = await escenario("estudiante", { solicitud: { tipo: "comercial", requiere_pago: true, estado_pago: "pendiente" } });
    await vm.runInContext("cargarSolicitudes()", vista.contexto);
    assert.match(textoNodo(vista.elementos["solicitudes-registradas"]), /Comercial · Pago pendiente \(no verificado por el sistema\)/);
    assert.strictEqual(botonesNodo(vista.elementos["solicitudes-registradas"]).length, 0);
  });
  await pruebaAsync("solicitudes: rechazo confirmado se muestra y no afirma aprobación", async () => {
    const vista = await escenario("coordinadora", { error: () => respuestaJson(409, { codigo: "solapamiento", mensaje: "Aula ocupada" }) });
    await vm.runInContext("cargarSolicitudes()", vista.contexto);
    const boton = botonesNodo(vista.elementos["solicitudes-registradas"])[0];
    await boton.listeners.click();
    assert.match(vista.elementos["resultado-solicitudes"].textContent, /No se aprobó.*solapamiento/);
    assert.strictEqual(boton.disabled, false);
  });
  for (const [nombre, error] of [["red", () => { throw new TypeError("red caída"); }],
    ["500", () => respuestaJson(500, { codigo: "error_interno_servidor" })],
    ["contrato 200 inválido", () => respuestaJson(200, {})]]) {
    await pruebaAsync(`solicitudes: fallo de ${nombre} indica resultado desconocido`, async () => {
      const vista = await escenario("coordinadora", { error });
      await vm.runInContext("cargarSolicitudes()", vista.contexto);
      const boton = botonesNodo(vista.elementos["solicitudes-registradas"])[0];
      await boton.listeners.click();
      assert.match(vista.elementos["resultado-solicitudes"].textContent, /No se pudo confirmar/);
      assert.doesNotMatch(vista.elementos["resultado-solicitudes"].textContent, /No se aprobó/);
      assert.strictEqual(boton.disabled, true);
      await vm.runInContext("cargarSolicitudes()", vista.contexto);
      assert.strictEqual(botonesNodo(vista.elementos["solicitudes-registradas"])[0].disabled, false);
    });
  }
  await pruebaAsync("solicitudes: consultar tras perder la respuesta recupera aprobación sin repetir el POST", async () => {
    const vista = await escenario("coordinadora", { errorTrasAplicar: true, error: () => { throw new TypeError("se perdió la respuesta"); } });
    await vm.runInContext("cargarSolicitudes()", vista.contexto);
    await botonesNodo(vista.elementos["solicitudes-registradas"])[0].listeners.click();
    assert.match(vista.elementos["resultado-solicitudes"].textContent, /No se pudo confirmar/);
    await vm.runInContext("cargarSolicitudes()", vista.contexto);
    assert.match(textoNodo(vista.elementos["solicitudes-registradas"]), /aprobada/);
    assert.strictEqual(botonesNodo(vista.elementos["solicitudes-registradas"]).length, 0);
    assert.strictEqual(vista.llamadas.filter(([url]) => url.endsWith("/aprobar")).length, 1);
  });
  await pruebaAsync("solicitudes: fallo de refresco conserva la confirmación de aprobación", async () => {
    const vista = await escenario("coordinadora", { errorRefresco: true });
    await vm.runInContext("cargarSolicitudes()", vista.contexto);
    await botonesNodo(vista.elementos["solicitudes-registradas"])[0].listeners.click();
    assert.match(vista.elementos["resultado-solicitudes"].textContent, /Solicitud 7 aprobada.*No se pudo actualizar/);
  });
  await pruebaAsync("solicitudes: se actualizan al abrir la pestaña repetidamente y tras enviar mensaje", async () => {
    const vista = await escenario();
    for (let i = 0; i < 2; i += 1) {
      vm.runInContext('activarPestana("solicitudes")', vista.contexto);
      await new Promise(setImmediate);
    }
    assert.strictEqual(vista.llamadas.filter(([url]) => url === "/api/solicitudes").length, 2);
    vista.contexto.document.getElementById("entrada-chat").value = "Una clase";
    await vm.runInContext("enviarChat({ preventDefault() {} })", vista.contexto);
    assert.strictEqual(vista.llamadas.filter(([url]) => url === "/api/solicitudes").length, 3);
    assert.strictEqual(vista.elementos["respuesta-chat"].textContent, "Solicitud creada");
  });
  console.log(fallos === 0 ? "Todas las pruebas de interfaz pasaron." : `${fallos} prueba(s) fallaron.`);
  process.exit(fallos === 0 ? 0 : 1);
})();
