// Pruebas de la recarga en la interfaz, sin navegador.
// Ejecuta static/app.js con un DOM y un fetch simulados.
// Uso: node tests/test_interfaz.js
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const codigoInterfaz = fs.readFileSync(path.join(__dirname, "..", "static", "app.js"), "utf8");

function crearElemento() {
  return {
    className: "", textContent: "", disabled: false, options: [], value: "",
    classList: { toggle() {} }, addEventListener() {}, appendChild() {}, replaceChildren() {},
    querySelector() { return crearElemento(); }, set onchange(_valor) {},
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
    querySelector: () => crearElemento(),
    getElementById: (id) => (elementos[id] = elementos[id] || crearElemento()),
    createElement: () => crearElemento(),
    createDocumentFragment: () => crearElemento(),
  };
  const contexto = {
    document: documento,
    console,
    Option: function Option() {},
    fetch: async (url, opciones = {}) => {
      if (opciones.method === "POST") return respuestaImportacion();
      return respuestaJson(200, []);
    },
  };
  vm.createContext(contexto);
  vm.runInContext(codigoInterfaz, contexto);
  return { contexto, banner: () => elementos["resultado-importacion"].textContent };
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
  console.log(fallos === 0 ? "Todas las pruebas de interfaz pasaron." : `${fallos} prueba(s) fallaron.`);
  process.exit(fallos === 0 ? 0 : 1);
})();
