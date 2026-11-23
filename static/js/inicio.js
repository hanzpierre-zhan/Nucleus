(() => {
  const $ = id => document.getElementById(id);
  const frases = JSON.parse($('inicio-frases').textContent);
  const hoy = new Date().toISOString().slice(0, 10);
  let indice = 0;

  // Guarda en este navegador lo traído de Wikipedia, una vez al día.
  const memoria = {
    leer(clave) { try { const v = JSON.parse(localStorage.getItem('inicio:' + clave) || 'null'); return v && v.dia === hoy ? v.datos : null; } catch (_) { return null; } },
    guardar(clave, datos) { try { localStorage.setItem('inicio:' + clave, JSON.stringify({dia: hoy, datos})); } catch (_) {} },
  };
  async function wikipedia(ruta, clave) {
    const guardado = memoria.leer(clave);
    if (guardado) return guardado;
    const r = await fetch('https://es.wikipedia.org/api/rest_v1/' + ruta, {headers: {Accept: 'application/json'}});
    if (!r.ok) throw Error('Wikipedia no respondió');
    const datos = await r.json();
    memoria.guardar(clave, datos);
    return datos;
  }

  // ── Frase del día con la foto del autor ──
  const iniciales = nombre => nombre.replace(/^(San|Santa|Papa)\s+/i, '').split(/\s+/).filter(p => /^[A-ZÁÉÍÓÚÑ]/.test(p)).slice(0, 2).map(p => p[0]).join('');
  let pedido = 0;
  async function foto(frase) {
    const img = $('inicio-foto'), turno = ++pedido;
    img.hidden = true;
    $('inicio-iniciales').textContent = iniciales(frase.autor);
    try {
      const datos = await wikipedia('page/summary/' + encodeURIComponent(frase.wiki), 'autor:' + frase.wiki);
      // La original si no es muy pesada; si no, la miniatura que da Wikipedia.
      const url = (datos.originalimage && datos.originalimage.width <= 2000 ? datos.originalimage.source : null) || datos.thumbnail?.source;
      if (!url || turno !== pedido) return;
      img.onload = () => { if (turno === pedido) img.hidden = false; };
      img.src = url;
    } catch (_) { /* quedan las iniciales */ }
  }
  function mostrar() {
    const frase = frases[indice];
    $('inicio-fecha').textContent = frase.fecha + ' · Frase del día';
    $('inicio-frase').textContent = '«' + frase.texto + '»';
    $('inicio-autor').textContent = frase.autor;
    $('inicio-autor').href = frase.fuente;
    $('inicio-descripcion').textContent = frase.descripcion;
    $('inicio-anterior').disabled = indice === frases.length - 1;
    $('inicio-siguiente').disabled = indice === 0;
    foto(frase);
  }
  $('inicio-anterior').onclick = () => { indice++; mostrar(); };
  $('inicio-siguiente').onclick = () => { indice--; mostrar(); };
  mostrar();

  // ── Un día como hoy: se dejan fuera los hechos trágicos ──
  const TRAGICO = /secuestr|estrell|accidente|atentado|masacre|asesin|bomba|terremoto|sismo|explosi|naufrag|guerra|batalla|incendio|genocid|ataque|invasi|muertos|víctimas|tiroteo|golpe de estado|ejecutad|huracán|tsunami|epidemia/i;
  (async () => {
    const caja = $('inicio-historia');
    try {
      const datos = await wikipedia('feed/onthisday/selected/' + caja.dataset.fecha, 'hoy:' + caja.dataset.fecha);
      const hechos = (datos.selected || []).filter(e => e.text && !TRAGICO.test(e.text));
      if (!hechos.length) return;
      // Principal: un acontecimiento con imagen; si no hay, cualquiera con imagen (nacimientos y fallecimientos al final).
      const conImagen = e => e.pages?.some(p => p.thumbnail);
      const principal = hechos.find(e => conImagen(e) && !/^(muere|fallece|nace)\b/i.test(e.text)) || hechos.find(conImagen) || hechos[0];
      const pagina = principal.pages?.find(p => p.thumbnail) || principal.pages?.[0];
      $('inicio-hecho-anio').textContent = principal.year;
      $('inicio-hecho-texto').textContent = principal.text.replace(/\s*\(en la imagen\)/i, '');
      if (pagina?.thumbnail) {
        $('inicio-hecho-img').src = pagina.thumbnail.source;
        $('inicio-hecho-img').alt = pagina.normalizedtitle || '';
        $('inicio-hecho-enlace').href = pagina.content_urls?.desktop?.page || '#';
      } else $('inicio-hecho-enlace').hidden = true;
      const lista = $('inicio-hechos');
      hechos.filter(e => e !== principal).slice(0, 2).forEach(e => {
        const li = document.createElement('li'), b = document.createElement('b');
        b.textContent = e.year;
        li.append(b, document.createTextNode(e.text.replace(/\s*\(en la imagen\)/i, '')));
        lista.append(li);
      });
      caja.hidden = false;
    } catch (_) { /* sin conexión con Wikipedia: no se muestra */ }
  })();
})();
