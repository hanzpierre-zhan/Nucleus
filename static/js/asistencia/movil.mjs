/** Ventana de una asistencia marcada en Nucleus Mobile: foto, alertas, recorrido en mapa y validación. */
const ESTADO = { PENDIENTE: "Falta validar", VALIDADA: "Validada", OBSERVADA: "Rechazada", RECHAZADA: "Rechazada" };

const el = (tag, clase, texto) => {
  const n = document.createElement(tag);
  if (clase) n.className = clase;
  if (texto !== undefined) n.textContent = texto;
  return n;
};
const fila = (titulo, valor) => {
  const d = el("div", "am-fila");
  d.append(el("span", null, titulo), el("strong", null, valor || "—"));
  return d;
};

export function abrirMovil(id, api, alTerminar) {
  const dlg = document.createElement("dialog");
  dlg.className = "am-ventana";
  dlg.addEventListener("close", () => { if (mapa) mapa.remove(); dlg.remove(); });
  document.body.append(dlg);
  dlg.append(el("p", "am-cargando", "Cargando…"));
  dlg.showModal();
  let mapa = null;

  const pintar = (d) => {
    dlg.replaceChildren();
    const cab = el("header", "am-cabeza");
    const titulo = el("div");
    titulo.append(
      el("strong", null, d.nombre),
      el("small", null, `${d.fecha.split("-").reverse().join("/")} · ${d.proyecto}`),
    );
    const chip = el("span", `am-chip am-${d.validacion.toLowerCase()}`, ESTADO[d.validacion] || d.validacion);
    const botones = el("div", "am-botones");
    const redondo = (clase, icono, texto, fn) => {
      const b = el("button", `am-redondo ${clase}`);
      b.type = "button";
      b.title = texto;
      b.setAttribute("aria-label", texto);
      b.append(el("i", `fa-solid ${icono}`));
      b.onclick = fn;
      botones.append(b);
      return b;
    };
    const motivo = el("textarea");
    motivo.rows = 2;
    motivo.maxLength = 500;
    motivo.placeholder = "Motivo (obligatorio para rechazar)";
    motivo.value = d.motivo || "";
    const error = el("p", "am-error");
    error.hidden = true;
    const enviar = async (accion) => {
      error.hidden = true;
      if (accion !== "validar" && !motivo.value.trim()) {
        error.textContent = "Escribe el motivo.";
        error.hidden = false;
        motivo.focus();
        return;
      }
      try {
        const r = await api(`/api/asistencia/movil/${id}`, { accion, motivo: motivo.value.trim() });
        alTerminar();
        pintar({ ...d, ...r });
      } catch (e) {
        error.textContent = e.message;
        error.hidden = false;
      }
    };
    if (d.editar) {
      redondo("am-verde", "fa-check", "Validar asistencia (queda como Asistió)", () => enviar("validar"));
      redondo("am-rojo", "fa-user-xmark", "Rechazar asistencia", () => enviar("rechazar"));
    }
    redondo("am-rojo", "fa-xmark", "Cerrar", () => dlg.close());
    cab.append(titulo, chip, botones);

    const izq = el("section", "am-panel");
    const foto = el("img", "am-foto");
    foto.src = d.foto_url;
    foto.alt = "Foto de la cuadrilla";
    const enlace = el("a");
    enlace.href = d.foto_url;
    enlace.target = "_blank";
    enlace.rel = "noopener";
    enlace.append(foto);
    izq.append(
      el("h4", null, "Marcación"),
      enlace,
      fila("Hora", d.hora),
      fila("Placa", d.placa),
      fila("Junior", d.junior),
      fila("Ubicación", `${d.latitud.toFixed(6)}, ${d.longitud.toFixed(6)}`),
      fila("Precisión", d.precision != null ? `±${Math.round(d.precision)} m` : ""),
    );
    if (d.validado_por)
      izq.append(fila(ESTADO[d.validacion] + " por", `${d.validado_por} · ${d.validado_en}`));
    const avisos = el("div", "am-alertas");
    if (d.alertas.length)
      d.alertas.forEach((a) => {
        const p = el("p", "am-alerta");
        p.append(el("i", "fa-solid fa-triangle-exclamation"), document.createTextNode(" " + a));
        avisos.append(p);
      });
    else avisos.append(el("p", "am-ok", "Sin alertas en el recorrido."));
    izq.append(avisos);
    if (d.editar) izq.append(el("label", "am-label", "Motivo"), motivo, error);
    else if (d.motivo) izq.append(fila("Motivo", d.motivo));

    const der = el("section", "am-panel");
    const caja = el("div", "am-mapa");
    const lista = el("ol", "am-recorrido");
    const cabMapa = el('div', 'am-mapa-cabecera');
    const abrirMapa = el('a', 'am-mapa-enlace', 'Abrir mapa ↗');
    abrirMapa.href = `https://www.openstreetmap.org/?mlat=${d.latitud}&mlon=${d.longitud}#map=17/${d.latitud}/${d.longitud}`;
    abrirMapa.target = '_blank'; abrirMapa.rel = 'noopener';
    cabMapa.append(el('h4', null, 'Recorrido del día'), abrirMapa);
    const avisoMapa = el('p', 'am-error', 'No se pudieron cargar las calles. Revisa tu conexión o usa «Abrir mapa».');
    avisoMapa.hidden = true;
    der.append(cabMapa, caja, avisoMapa, lista);
    const puntos = d.recorrido.length
      ? d.recorrido
      : [{ hora: d.hora, evento: "Asistencia", latitud: d.latitud, longitud: d.longitud, km: 0, quien: "Principal" }];
    puntos.forEach((p, i) => {
      const li = el("li");
      const punto = el('button', 'am-punto', `${p.hora} · ${p.evento}${p.quien === 'Junior' ? ' (junior)' : ''}`);
      punto.type = 'button'; punto.title = 'Ver este punto en el mapa';
      punto.onclick = () => { if (mapa) mapa.flyTo([p.latitud, p.longitud], 17); };
      li.append(
        el("b", null, `${i + 1}`),
        punto,
        el("small", null, p.km ? `${p.km} km de la marcación` : "punto de marcación"),
      );
      lista.append(li);
    });
    const cuerpo = el("div", "am-cuerpo");
    cuerpo.append(izq, der);
    dlg.append(cab, cuerpo);

    if (window.L) {
      if (mapa) mapa.remove();
      mapa = L.map(caja, { scrollWheelZoom: false });
      const calles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19,
      }).addTo(mapa);
      calles.on('tileerror', () => { avisoMapa.hidden = false; });
      calles.on('tileload', () => { avisoMapa.hidden = true; });
      const coords = puntos.map((p) => [p.latitud, p.longitud]);
      L.polyline(coords, { color: "#2563eb", weight: 3, dashArray: "6 6" }).addTo(mapa);
      puntos.forEach((p, i) =>
        L.marker([p.latitud, p.longitud], {
          icon: L.divIcon({
            className: `am-pin ${p.evento === "Asistencia" ? "am-pin-asis" : ""}`,
            html: String(i + 1),
            iconSize: [24, 24],
          }),
        })
          .bindTooltip(`${p.hora} · ${p.evento}`)
          .addTo(mapa),
      );
      mapa.fitBounds(L.latLngBounds(coords).pad(0.3), { maxZoom: 16 });
      setTimeout(() => mapa.invalidateSize(), 50);
    } else caja.append(el("p", "am-ok", "No se pudo cargar el mapa."));
  };

  api(`/api/asistencia/movil/${id}`)
    .then(pintar)
    .catch((e) => {
      dlg.replaceChildren(el("p", "am-error", e.message));
    });
}
