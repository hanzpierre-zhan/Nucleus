import { crearApi } from "./asistencia/api.mjs";
import { siglas, clave, filtrarYOrdenar } from "./asistencia/modelo.mjs";

(() => {
  "use strict";
  const $ = (id) => document.getElementById(id),
    csrf = document.querySelector('meta[name="asistencia-csrf"]').content;
  let contexto,
    planilla,
    mesCargado,
    proyectoCargado,
    carga = 0,
    guardando = false,
    cambios = new Map(),
    elegidos = new Set(),
    orden = { campo: "nombre", direccion: 1 };
  const el = (tag, text) => {
    const n = document.createElement(tag);
    n.textContent = text;
    return n;
  };
  const periodo = () => `${$("as-anio").value}-${$("as-mes").value}`;
  const seleccion = () =>
    new URLSearchParams({
      mes: periodo(),
      proyecto: $("as-proyecto").value,
      personal: $("as-personal").value,
    });
  const api = crearApi(csrf);
  function dibujar() {
    if (!planilla) return;
    $("as-planilla").style.setProperty("--attendance-days", planilla.dias);
    const [anio, mes] = mesCargado.split("-").map(Number),
      head = el("tr", "");
    const fijo = el("th", ""),
      todos = el("input", "");
    todos.type = "checkbox";
    todos.setAttribute("aria-label", "Seleccionar personal visible");
    todos.onchange = () => {
      for (const p of visibles())
        if (p.editar && p.activo)
          todos.checked ? elegidos.add(clave(p)) : elegidos.delete(clave(p));
      dibujar();
    };
    fijo.append(
      todos,
      document.createTextNode(" Personal / Proyecto"),
      ordenarBoton("nombre", "Personal"),
    );
    fijo.setAttribute(
      "aria-sort",
      orden.campo === "nombre"
        ? orden.direccion === 1
          ? "ascending"
          : "descending"
        : "none",
    );
    head.append(fijo);
    for (let d = 1; d <= planilla.dias; d++) {
      const fecha = new Date(anio, mes - 1, d),
        th = el("th", "");
      th.append(
        el(
          "small",
          [
            "ENE",
            "FEB",
            "MAR",
            "ABR",
            "MAY",
            "JUN",
            "JUL",
            "AGO",
            "SEP",
            "OCT",
            "NOV",
            "DIC",
          ][mes - 1],
        ),
        document.createTextNode(String(d).padStart(2, "0")),
      );
      th.append(
        el("small", ["Do", "Lu", "Ma", "Mi", "Ju", "Vi", "Sá"][fecha.getDay()]),
      );
      th.append(ordenarBoton(d, `día ${d}`));
      th.setAttribute(
        "aria-sort",
        orden.campo === d
          ? orden.direccion === 1
            ? "ascending"
            : "descending"
          : "none",
      );
      if ([0, 6].includes(fecha.getDay())) th.className = "weekend";
      head.append(th);
    }
    $("as-cabecera").replaceChildren(head);
    const filas = visibles(),
      body = document.createDocumentFragment(),
      totales = Object.fromEntries(Object.keys(siglas).map((s) => [s, 0]));
    for (const p of filas) {
      const tr = el("tr", ""),
        nombre = el("td", "");
      const check = el("input", "");
      check.type = "checkbox";
      check.checked = elegidos.has(clave(p));
      check.disabled = !p.editar || !p.activo;
      check.setAttribute("aria-label", `Seleccionar ${p.nombre}`);
      check.onchange = () => {
        check.checked ? elegidos.add(clave(p)) : elegidos.delete(clave(p));
      };
      nombre.append(
        check,
        el("strong", p.nombre),
        el("small", `${p.documento} · ${p.proyecto}`),
      );
      nombre.title = `${p.nombre} · ${p.proyecto}`;
      tr.append(nombre);
      for (let d = 1; d <= planilla.dias; d++) {
        const marca = cambios.get(clave(p, d)) ||
            p.marcas[d] || { estado: "PENDIENTE", observacion: "", version: 0 },
          td = el("td", ""),
          b = el("button", siglas[marca.estado]);
        totales[marca.estado]++;
        b.type = "button";
        b.dataset.state = marca.estado;
        b.title = `${d}/${mes}/${anio}: ${contexto.estados[marca.estado]}${marca.observacion ? " · " + marca.observacion : ""}`;
        b.setAttribute(
          "aria-label",
          `${p.nombre}, ${d}/${mes}/${anio}, ${contexto.estados[marca.estado]}`,
        );
        b.disabled = !p.editar || (!p.activo && !p.marcas[d]);
        b.onclick = () => {
          if (!vigente()) return;
          marcar(p, d);
          dibujar();
        };
        if (cambios.has(clave(p, d))) b.classList.add("unsaved");
        td.append(b);
        if ([0, 6].includes(new Date(anio, mes - 1, d).getDay()))
          td.className = "weekend";
        tr.append(td);
      }
      body.append(tr);
    }
    if (!filas.length) {
      const tr = el("tr", ""),
        td = el("td", "Sin personal para esta selección.");
      td.colSpan = planilla.dias + 1;
      tr.append(td);
      body.append(tr);
    }
    $("as-filas").replaceChildren(body);
    const cards = document.createDocumentFragment();
    for (const [s, n] of Object.entries(siglas)) {
      const c = el("div", "");
      c.className = "attendance-stat";
      const chip = el("em", n);
      chip.dataset.state = s;
      c.append(chip, el("b", totales[s]), el("span", contexto.estados[s]));
      cards.append(c);
    }
    $("as-totales").replaceChildren(cards);
    $("as-estado").textContent =
      `${filas.length} personas · ${mesCargado} · Cada celda es un día. Pulsa una sigla para marcar. Sin marcar no es falta.`;
    botones();
  }
  async function cargar() {
    if (cambios.size) {
      $("as-estado").textContent =
        "Guarda o descarta los cambios antes de consultar otro período.";
      return;
    }
    const turno = ++carga,
      q = seleccion();
    $("as-estado").textContent = "Consultando…";
    try {
      const j = await api(`/api/asistencia/planilla?${q}`);
      if (turno !== carga) return;
      planilla = j;
      elegidos.clear();
      $("as-desde").max = j.dias;
      $("as-hasta").max = j.dias;
      mesCargado = j.mes;
      proyectoCargado = q.get("proyecto");
      dibujar();
    } catch (e) {
      if (turno === carga) $("as-estado").textContent = e.message;
    }
  }
  function ordenarBoton(campo, nombre) {
    const b = el(
      "button",
      orden.campo === campo ? (orden.direccion === 1 ? "↑" : "↓") : "↕",
    );
    b.type = "button";
    b.className = "attendance-sort";
    b.title = `Ordenar ${nombre} A–Z / Z–A`;
    b.setAttribute("aria-label", b.title);
    b.onclick = () => {
      orden =
        orden.campo === campo
          ? { campo, direccion: -orden.direccion }
          : { campo, direccion: 1 };
      dibujar();
    };
    return b;
  }
  function visibles() {
    return filtrarYOrdenar(
      planilla.registros,
      $("as-buscar").value,
      orden,
      contexto.estados,
      cambios,
    );
  }
  function vigente() {
    if (
      periodo() !== mesCargado ||
      $("as-proyecto").value !== proyectoCargado
    ) {
      $("as-estado").textContent = "Consulta la selección antes de marcar.";
      return false;
    }
    return !guardando;
  }
  function botones() {
    $("as-guardar").disabled = !cambios.size || guardando;
    $("as-guardar").textContent = cambios.size
      ? `Guardar ${cambios.size} marcas`
      : "Guardar cambios";
    $("as-pendientes").textContent = cambios.size
      ? `${cambios.size} cambios sin guardar (borde azul).`
      : "Elige un estado y pulsa las celdas. No se guarda hasta presionar Guardar.";
  }
  function marcar(p, d) {
    if (!p.editar || (!p.activo && !p.marcas[d])) return;
    const original = p.marcas[d] || {
        estado: "PENDIENTE",
        observacion: "",
        version: 0,
      },
      estado = $("as-pincel").value,
      key = clave(p, d);
    if (estado === original.estado) cambios.delete(key);
    else
      cambios.set(key, {
        ...original,
        estado,
        personal_id: p.personal_id,
        proyecto_id: p.proyecto_id,
        dia: d,
      });
  }
  $("as-aplicar").onclick = () => {
    if (!vigente()) return;
    const desde = Number($("as-desde").value),
      hasta = Number($("as-hasta").value);
    if (
      !Number.isInteger(desde) ||
      !Number.isInteger(hasta) ||
      desde < 1 ||
      hasta > planilla.dias ||
      hasta < desde
    ) {
      $("as-estado").textContent = "Revisa el rango de días del mes.";
      return;
    }
    const equipo = visibles().filter((p) => elegidos.has(clave(p)));
    if (!equipo.length) {
      $("as-estado").textContent =
        "Selecciona trabajadores con las casillas de la izquierda.";
      return;
    }
    for (const p of equipo) for (let d = desde; d <= hasta; d++) marcar(p, d);
    dibujar();
  };
  $("as-deshacer").onclick = () => {
    if (guardando) return;
    cambios.clear();
    dibujar();
  };
  $("as-guardar").onclick = async () => {
    if (!vigente() || !cambios.size) return;
    guardando = true;
    document.querySelector(".attendance").inert = true;
    botones();
    let guardados = 0;
    try {
      const dias = [...new Set([...cambios.values()].map((m) => m.dia))];
      for (const d of dias) {
        const marcas = [...cambios.values()].filter((m) => m.dia === d);
        for (let i = 0; i < marcas.length; i += 500) {
          const lote = marcas.slice(i, i + 500);
          await api(
            `/api/asistencia/dia?${new URLSearchParams({ proyecto: proyectoCargado })}`,
            {
              fecha: `${mesCargado}-${String(d).padStart(2, "0")}`,
              registros: lote,
            },
          );
          for (const m of lote) {
            const p = planilla.registros.find(
              (p) =>
                p.personal_id === m.personal_id &&
                p.proyecto_id === m.proyecto_id,
            );
            p.marcas[d] = { ...m, version: m.version + 1 };
            cambios.delete(clave(m, d));
            guardados++;
          }
        }
      }
      dibujar();
      $("as-estado").textContent =
        `${guardados} marcas guardadas con historial.`;
    } catch (e) {
      dibujar();
      $("as-estado").textContent =
        `${guardados} guardadas; ${cambios.size} pendientes. ${e.message}`;
    } finally {
      guardando = false;
      document.querySelector(".attendance").inert = false;
      botones();
    }
  };
  window.addEventListener("beforeunload", (e) => {
    if (cambios.size) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
  $("as-consultar").onclick = cargar;
  $("as-buscar").oninput = dibujar;
  for (const id of ["as-mes", "as-anio", "as-proyecto", "as-personal"])
    $(id).onchange = () => {
      $("as-estado").textContent =
        "Pulsa Consultar para cargar esta selección.";
    };
  $("as-exportar").onclick = () => {
    if (cambios.size) {
      $("as-estado").textContent =
        "Guarda o descarta los cambios antes de exportar.";
      return;
    }
    const q = seleccion();
    q.set("formato", "xlsx");
    location.assign(`/api/asistencia/mensual?${q}`);
  };
  (async () => {
    try {
      contexto = await api("/api/asistencia/contexto");
      const meses = [
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre",
      ];
      meses.forEach((m, i) =>
        $("as-mes").append(new Option(m, String(i + 1).padStart(2, "0"))),
      );
      $("as-mes").value = contexto.hoy.slice(5, 7);
      $("as-anio").value = contexto.hoy.slice(0, 4);
      if (contexto.proyectos.length > 1)
        $("as-proyecto").append(new Option("Todos mis proyectos", "todos"));
      contexto.proyectos.forEach((p) =>
        $("as-proyecto").append(new Option(p.nombre, p.id)),
      );
      Object.keys(siglas).forEach((s) =>
        $("as-pincel").append(
          new Option(`${siglas[s]} · ${contexto.estados[s]}`, s),
        ),
      );
      $("as-pincel").value = "PRESENTE";
      await cargar();
    } catch (e) {
      $("as-estado").textContent = e.message;
    }
  })();
})();
