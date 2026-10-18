from pathlib import Path
p=Path('static/js/asistencia.js');s=p.read_text(encoding='utf-8');folder=Path('static/js/asistencia');folder.mkdir(exist_ok=True)
a=s.index('  async function api(');b=s.index('  function dibujar()',a);api=s[a:b]
(folder/'api.mjs').write_text('/** Transporte HTTP de asistencia; conserva errores y token CSRF. */\nexport function crearApi(csrf) {\n'+api.replace('  async function api(', '  return async function api(',1).rstrip()+';\n}\n',encoding='utf-8')
s=s[:a]+'  const api = crearApi(csrf);\n'+s[b:]
a=s.index('    siglas = {');b=s.index('    csrf =',a);s=s[:a]+s[b:]
# Import functions rather than copying state across modules.
a=s.index('  const clave =');b=s.index('  function ordenarBoton(',a);s=s[:a]+s[b:]
a=s.index('  function visibles()');b=s.index('  function vigente()',a)
s=s[:a]+'''  function visibles() {
    return filtrarYOrdenar(planilla.registros, $("as-buscar").value, orden, contexto.estados, cambios);
  }
'''+s[b:]
s='''import { crearApi } from "./asistencia/api.mjs";
import { siglas, clave, filtrarYOrdenar } from "./asistencia/modelo.mjs";

'''+s;p.write_text(s,encoding='utf-8')
(folder/'modelo.mjs').write_text('''/** Reglas de identidad, búsqueda y orden. No acceden al DOM ni a la red. */
export const siglas = Object.freeze({
  PRESENTE: "A", FALTA: "F", DESCANSO: "D", PERMISO: "P",
  LICENCIA: "L", VACACIONES: "V", PENDIENTE: "—",
});

export const clave = (persona, dia = "") =>
  `${persona.personal_id}:${persona.proyecto_id}:${dia}`;

export function filtrarYOrdenar(personas, busqueda, orden, estados, cambios) {
  const texto = busqueda.trim().toLocaleLowerCase();
  const valor = persona => {
    if (orden.campo === "nombre") return persona.nombre;
    const marca = cambios.get(clave(persona, orden.campo)) || persona.marcas[orden.campo] || {estado: "PENDIENTE"};
    return estados[marca.estado];
  };
  return personas.filter(persona =>
    `${persona.nombre} ${persona.documento} ${persona.proyecto}`.toLocaleLowerCase().includes(texto)
  ).sort((a, b) =>
    orden.direccion * valor(a).localeCompare(valor(b), "es", {sensitivity: "base", numeric: true}) ||
    a.nombre.localeCompare(b.nombre, "es") || a.personal_id - b.personal_id
  );
}
''',encoding='utf-8')
p=Path('templates/asistencia.html');s=p.read_text(encoding='utf-8').replace('<script src="/static/js/asistencia.js?v=6">','<script type="module" src="/static/js/asistencia.js?v=7">');p.write_text(s,encoding='utf-8')
