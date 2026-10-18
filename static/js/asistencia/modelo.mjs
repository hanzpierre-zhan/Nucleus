/** Reglas de identidad, búsqueda y orden. No acceden al DOM ni a la red. */
export const siglas = Object.freeze({
  PRESENTE: "A",
  FALTA: "F",
  DESCANSO: "D",
  PERMISO: "P",
  LICENCIA: "L",
  VACACIONES: "V",
  PENDIENTE: "—",
});

export const clave = (persona, dia = "") =>
  `${persona.personal_id}:${persona.proyecto_id}:${dia}`;

export function filtrarYOrdenar(personas, busqueda, orden, estados, cambios) {
  const texto = busqueda.trim().toLocaleLowerCase();
  const valor = (persona) => {
    if (orden.campo === "nombre") return persona.nombre;
    const marca = cambios.get(clave(persona, orden.campo)) ||
      persona.marcas[orden.campo] || { estado: "PENDIENTE" };
    return estados[marca.estado];
  };
  return personas
    .filter((persona) =>
      `${persona.nombre} ${persona.documento} ${persona.proyecto}`
        .toLocaleLowerCase()
        .includes(texto),
    )
    .sort(
      (a, b) =>
        orden.direccion *
          valor(a).localeCompare(valor(b), "es", {
            sensitivity: "base",
            numeric: true,
          }) ||
        a.nombre.localeCompare(b.nombre, "es") ||
        a.personal_id - b.personal_id,
    );
}
