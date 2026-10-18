(() => {
    'use strict';
    const $ = id => document.getElementById(id);
    let contexto, modulo, pagina = 1, total = 0, abierto, administracion, mapa, capaMapa, carga = 0;
    const consulta = new URLSearchParams(location.search);
    const csrf = document.querySelector('meta[name="espacios-csrf"]').content;
    const norm = v => String(v).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');
    const protegidos = new Set(['estado','estadocotizacion','codigodeposito','proyecto','nombredelproyecto','cliente','tipoproyecto','tipodeproyecto','marcatemporal','fechapago','montopago','fotopago','generada','bloqueada','numerowo','numerodewo','wonumber']);
    ['interaccion','codigointerno','norden','fechasustento','fecharechazo','rechazadopor','fechavalidacion','validadopor','depositadopor','sustentadopor','editadopor','rechazadodesde','vecesrechazado','devueltopor','fechadevolucion','observadopor','fechaobservacion','archivadopor','fechaarchivo','desarchivadopor','fechadesarchivo','anuladodesde','anuladopor','fechaanulacion'].forEach(k => protegidos.add(k));
    const nombresAccion = {consultar:'Consultar',exportar:'Exportar',editar:'Editar',validar:'Validar',rechazar:'Rechazar',anular:'Anular',depositar:'Registrar depósito',sustentar:'Conformar sustento',revertir:'Revertir',devolver:'Devolver',observar:'Observar',archivar:'Archivar',desarchivar:'Desarchivar'};
    const texto = valor => typeof valor === 'object' && valor !== null ? JSON.stringify(valor) : String(valor ?? '');
    function nodo(tag, contenido, clase) {
        const el = document.createElement(tag); el.textContent = contenido;
        if (clase) el.className = clase;
        return el;
    }
    function opciones(el, valores, vacio) {
        el.replaceChildren();
        if (vacio) el.append(new Option(vacio, ''));
        valores.forEach(v => el.append(new Option(v.nombre, v.id)));
    }
    async function api(url, metodo = 'GET', datos) {
        const r = await fetch(url, {method:metodo, credentials:'same-origin',
            headers:{'Content-Type':'application/json','X-Espacios-CSRF':csrf},
            ...(datos !== undefined ? {body:JSON.stringify(datos)} : {})});
        let j; try { j = await r.json(); } catch (_) { throw new Error('No se pudo leer la respuesta. Recarga la página.'); }
        if (!r.ok || j.error) throw new Error(j.error || 'No se pudo completar la operación.');
        return j;
    }
    function permisos(pid) { return contexto.proyectos.find(p => p.id === Number(pid))?.permisos[modulo] || []; }
    function tiene(accion) {
        return contexto.proyectos.some(p => ($('proyecto').value === 'todos' || p.id === Number($('proyecto').value)) && (p.permisos[modulo] || []).includes(accion));
    }
    function direccion(sufijo) {
        return `/api/espacios/${modulo}/${sufijo}?proyecto=${encodeURIComponent($('proyecto').value)}`;
    }
    function guardarVista() {
        const q = new URLSearchParams({proyecto:$('proyecto').value, modulo});
        if($('vista-admin') && !$('vista-admin').hidden)q.set('administrar','1');
        history.replaceState(null, '', `/espacios?${q}`);
    }
    function menu() {
        const permitidos = contexto.modulos.filter(m => contexto.proyectos.some(p => (p.permisos[m.id] || []).includes('consultar')));
        if (!permitidos.some(m => m.id === modulo)) modulo = permitidos[0]?.id;
        const anterior=$('proyecto').value;
        const proyectos=contexto.proyectos.filter(p=>(p.permisos[modulo] || []).includes('consultar'));
        opciones($('proyecto'), [...(proyectos.length>1 ? [{id:'todos',nombre:'Todos mis proyectos'}]:[]), ...proyectos]);
        $('proyecto').value=[...$('proyecto').options].some(o=>o.value===anterior) ? anterior : (proyectos.length===1 ? String(proyectos[0].id) : 'todos');
        if(!proyectos.length)opciones($('proyecto'),[{id:'todos',nombre:'Sin proyectos asignados'}]);
        opciones($('proyecto-movil'), [...$('proyecto').options].map(o=>({id:o.value,nombre:o.textContent})));
        $('proyecto-movil').value=$('proyecto').value;
        const iconos={operacion:'briefcase',personal:'users',materiales:'boxes-stacked',sites:'location-dot',mapa_sites:'map-location-dot',generadores:'bolt',combustible:'gas-pump',cotizaciones:'file-invoice-dollar',rendicion:'wallet',liquidaciones:'file-invoice'};
        for(const id of ['modulos','modulos-movil']) {
            $(id).replaceChildren();
            permitidos.forEach(m => {
                const link=nodo('a','', 'sidebar-link'+(m.id===modulo?' active':''));
                link.href=`/espacios?proyecto=${encodeURIComponent($('proyecto').value)}&modulo=${m.id}`;
                link.dataset.modulo=m.id;
                const icon=document.createElement('i'); icon.className=`fa-solid fa-${iconos[m.id] || 'folder-open'}`;
                link.append(icon,nodo('span',m.nombre,'sidebar-link-text'));
                if(m.id===modulo)link.setAttribute('aria-current','page');
                link.onclick=e=>{e.preventDefault();modulo=m.id;pagina=1;$('buscar').value='';$('vista-datos').hidden=false;if($('vista-admin'))$('vista-admin').hidden=true;menu();cargar();$('modulos-movil').hidden=true;$('menu-movil').setAttribute('aria-expanded','false');};
                $(id).append(link);
            });
        }
    }
    async function cargarMapa(turno) {
        const j=await api(direccion('mapa')+`&buscar=${encodeURIComponent($('buscar').value)}`);
        if(turno!==carga)return;
        if(!mapa){mapa=L.map('workspace-map').setView([-9.2,-75],5);capaMapa=L.layerGroup().addTo(mapa);L.control.scale({imperial:false}).addTo(mapa);}
        capaMapa.clearLayers();const puntos=[];
        j.puntos.forEach(p=>{const tip=document.createElement('div');tip.append(nodo('strong',p.nombre),nodo('p',p.proyecto));const b=nodo('button','Ver detalle');b.onclick=()=>abrir(p.id);tip.append(b);L.circleMarker([p.lat,p.lng],{radius:5,color:'#1757a6',weight:1,fillOpacity:.7}).bindPopup(tip).addTo(capaMapa);puntos.push([p.lat,p.lng]);});
        mapa.invalidateSize();if(puntos.length)mapa.fitBounds(puntos,{padding:[25,25],maxZoom:14});
        $('conteo').textContent=`${j.puntos.length} sites con coordenadas · ${j.sin_coordenadas} sin coordenadas`;
        $('ayuda').textContent='Ubicación de los sites autorizados. Usa los controles para acercar y abre un punto para consultar su detalle. La copia de pruebas muestra coordenadas sin descargar mapas externos.';
    }
    async function cargar() {
        const turno = ++carga;
        $('estado').textContent = '';
        $('filas').replaceChildren();
        if (!modulo) {
            $('titulo').textContent = 'Sin módulos asignados';
            $('ayuda').textContent = 'Solicita a administración la asignación de un proyecto y perfil.';
            $('exportar').hidden = true; return;
        }
        guardarVista();
        $('herramienta-asistencia').hidden=modulo!=='personal';
        const esMapa=modulo==='mapa_sites';
        $('workspace-map').hidden=!esMapa;
        document.querySelector('.table-wrap').hidden=esMapa;
        document.querySelector('.pagination').hidden=esMapa;
        $('titulo').textContent = contexto.modulos.find(m => m.id === modulo).nombre;
        $('contexto').textContent = $('proyecto').selectedOptions[0]?.textContent || '';
        $('ayuda').textContent = 'Registros de los proyectos autorizados. Abre un detalle para consultar sus datos.';
        $('exportar').hidden = !tiene('exportar');
        try {
            if(esMapa){await cargarMapa(turno);return;}
            const j = await api(direccion('registros') + `&pagina=${pagina}&buscar=${encodeURIComponent($('buscar').value)}`);
            if (turno !== carga) return;
            total = j.total; pagina = j.pagina;
            $('conteo').textContent = `${total} registros`;
            $('pagina').textContent = `Página ${pagina} de ${Math.max(1, Math.ceil(total / j.limite))}`;
            $('anterior').disabled = pagina <= 1; $('siguiente').disabled = pagina * j.limite >= total;
            if (!j.registros.length) {
                const tr = document.createElement('tr'), td = nodo('td','No hay registros para esta selección.','empty'); td.colSpan = 6; tr.append(td); $('filas').append(tr);
            }
            const preferidos=['Marca temporal','ESTADO','ESTADO COTIZACION','TECNICO','Técnico beneficiario','Nombre del proyecto','PROYECTO','NOMBRE DE SITE','Nombre de Site','NUMERO WO'];
            const claves=[...new Set(j.registros.flatMap(f=>Object.keys(f.datos)))];
            const campos=[...preferidos.filter(k=>claves.includes(k)),...claves.filter(k=>!preferidos.includes(k))];
            document.querySelector('.table-wrap table').style.width=`${(campos.length+3)*155}px`;
            const cabeza=document.querySelector('.table-wrap thead tr');cabeza.replaceChildren();
            ['Proyecto','Registro',...campos,'Detalle'].forEach(c=>cabeza.append(nodo('th',c)));
            j.registros.forEach(f => {
                const tr = document.createElement('tr');
                [f.proyecto,f.clave,...campos.map(k=>f.datos[k]??'—')].forEach(v=>{const td=nodo('td',texto(v));td.title=texto(v);tr.append(td);});
                const td=document.createElement('td'),b=nodo('button','Ver detalle');b.onclick=()=>abrir(f.id);td.append(b);tr.append(td);$('filas').append(tr);
            });
        } catch (e) { if (turno === carga) $('estado').textContent = e.message; }
    }
    async function abrir(id) {
        try {
            const f = await api(`/api/espacios/${modulo}/registros/${id}`); abierto = f;
            $('detalle-titulo').textContent = f.clave; $('detalle-proyecto').textContent = f.proyecto;
            $('detalle-campos').replaceChildren(); $('detalle-estado').textContent = '';
            Object.entries(f.datos).forEach(([k,v]) => $('detalle-campos').append(nodo('dt', k), nodo('dd', texto(v))));
            const editables = Object.keys(f.datos).filter(k => !protegidos.has(norm(k)) && !k.startsWith('_'));
            opciones($('campo-editar'), editables.map(k => ({id:k,nombre:k})));
            $('editar-form').hidden = !permisos(f.proyecto_id).includes('editar') || !editables.length || modulo === 'liquidaciones';
            $('campo-editar').onchange = () => { $('valor-editar').value = texto(f.datos[$('campo-editar').value]); };
            $('campo-editar').onchange();
            const acciones = permisos(f.proyecto_id).filter(a => !['consultar','exportar','editar'].includes(a));
            $('accion-form').hidden = modulo !== 'rendicion' || !acciones.length;
            opciones($('accion'), acciones.map(a => ({id:a,nombre:nombresAccion[a]})));
            $('accion-form').reset();
            if (!$('detalle').open) $('detalle').showModal();
        } catch (e) { $('estado').textContent = e.message; }
    }
    $('cerrar-detalle').onclick = () => $('detalle').close();
    $('editar-form').onsubmit = async e => {
        e.preventDefault();
        try {
            await api(`/api/espacios/${modulo}/registros/${abierto.id}`, 'PATCH', {key:abierto.clave, field:$('campo-editar').value, value:$('valor-editar').value, revision:abierto.revision});
            await abrir(abierto.id); $('detalle-estado').textContent = 'Cambio guardado.'; cargar();
        } catch (error) { $('detalle-estado').textContent = error.message; }
    };
    $('accion-form').onsubmit = async e => {
        e.preventDefault();
        try {
            await api(`/api/espacios/rendicion/registros/${abierto.id}/accion`, 'POST', {
                key:abierto.clave, accion:$('accion').value, tiempo:$('tiempo').value,
                fecha_pago:$('fecha-pago').value, monto_pago:$('monto-pago').value,
                foto_pago:$('foto-pago').value, comentario:$('comentario').value, observaciones:$('comentario').value});
            await abrir(abierto.id); $('detalle-estado').textContent = 'Acción registrada.'; cargar();
        } catch (error) { $('detalle-estado').textContent = error.message; }
    };
    $('proyecto').onchange = () => { pagina = 1; menu(); cargar(); };
    $('actualizar').onclick = () => cargar();
    $('anterior').onclick = () => { pagina--; cargar(); };
    $('siguiente').onclick = () => { pagina++; cargar(); };
    let busqueda;
    $('proyecto-movil').onchange=()=>{$('proyecto').value=$('proyecto-movil').value;$('proyecto').onchange();};
    $('menu-movil').onclick=()=>{$('modulos-movil').hidden=!$('modulos-movil').hidden;$('menu-movil').setAttribute('aria-expanded',String(!$('modulos-movil').hidden));};
    $('buscar').oninput = () => { clearTimeout(busqueda); busqueda = setTimeout(() => { pagina = 1; cargar(); }, 250); };
    $('exportar').onclick = () => { location.href = direccion('exportar'); };

    (async () => {
        try {
            contexto = await api('/api/espacios/contexto');
            opciones($('proyecto'), [{id:'todos',nombre:'Todos mis proyectos'}, ...contexto.proyectos]);
            const inicial = consulta.get('proyecto');
            if ([...$('proyecto').options].some(o => o.value === inicial)) $('proyecto').value = inicial;
            else if (contexto.proyectos.length === 1) $('proyecto').value = contexto.proyectos[0].id;
            modulo = consulta.get('modulo'); menu();
            await cargar();
        } catch(e) { $('estado').textContent = e.message; }
    })();
})();
