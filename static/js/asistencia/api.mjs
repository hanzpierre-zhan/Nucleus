/** Transporte HTTP de asistencia; conserva errores y token CSRF. */
export function crearApi(csrf) {
  return async function api(url, datos) {
    const r = await fetch(url, {
      credentials: "same-origin",
      ...(datos
        ? {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-Asistencia-CSRF": csrf,
            },
            body: JSON.stringify(datos),
          }
        : {}),
    });
    let j;
    try {
      j = await r.json();
    } catch {
      throw Error("No se pudo leer la respuesta.");
    }
    if (!r.ok) throw Error(j.error || "No se pudo completar la operación.");
    return j;
  };
}
