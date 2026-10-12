(() => {
    'use strict';
    const norm = value => String(value || '').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]/g,'');
    const siteFields = new Set(['site','nombresite','nombredesite','nombredelsite','sitename']);
    function kind(field) { const name=norm(field); return name==='departamento' ? 'departamentos' : (siteFields.has(name) ? 'sites' : null); }
    window.nucleusTipoCatalogo = kind;
    // Cada página identifica su FLM: abrir otro proyecto en otra pestaña no
    // cambia el destino de los guardados del formulario que ya estaba abierto.
    const root=document.querySelector('.app-main');
    if (root?.dataset.flmOrigin) {
        const originalFetch=window.fetch.bind(window);
        window.fetch=(input, init={})=>{
            const url=new URL(input instanceof Request ? input.url : String(input),window.location.href);
            if(url.origin===window.location.origin && url.pathname.startsWith('/api/')) {
                const headers=new Headers(init.headers || (input instanceof Request ? input.headers : undefined));
                headers.set('X-Nucleus-Project',root.dataset.proyectoId);
                headers.set('X-FLM-Origin',root.dataset.flmOrigin);
                return originalFetch(input,{...init,headers});
            }
            return originalFetch(input,init);
        };
    }
    let loading;
    function load() {
        if (!loading) loading = fetch('/api/catalogos/autocompletar').then(r => nucleusLeerRespuestaJSON(r)).then(data => {
            window.nucleusDepartamentos = data.departamentos || [];
            for (const name of ['departamentos','sites']) {
                let list=document.getElementById('nucleus-catalogo-'+name);
                if (!list) {list=document.createElement('datalist');list.id='nucleus-catalogo-'+name;document.body.appendChild(list);}
                const fragment=document.createDocumentFragment();
                for (const value of data[name] || []) {const option=document.createElement('option');option.value=value;fragment.appendChild(option);}
                list.replaceChildren(fragment);
            }
        }).catch(() => { loading=null; });
        return loading;
    }
    function fieldOf(input) {
        if (input.dataset.field || input.dataset.key) return input.dataset.field || input.dataset.key;
        const column=input.closest('[tabulator-field]'); if (column) return column.getAttribute('tabulator-field');
        if (kind(input.name)) return input.name;
        if (input.id === 'wo-coti-site') return 'SITE';
        const label=input.labels?.[0] || input.closest('.wo-field,.form-group,.cot-form-field')?.querySelector('label');
        return label?.textContent || input.name || input.id;
    }
    window.nucleusAplicarAutocompletado = (input, field) => {
        if (!(input instanceof HTMLInputElement) || !['text','search'].includes(input.type)) return;
        const type=kind(field || fieldOf(input)); if (!type) return;
        input.setAttribute('list','nucleus-catalogo-'+type); input.autocomplete='off';
        load();
    };
    function contextualProject(element) {
        const origen=document.querySelector('.app-main')?.dataset.flmResource;
        if (!origen || norm(element.dataset.field || element.name)!=='proyecto') return;
        if (element instanceof HTMLSelectElement) {
            if (![...element.options].some(o=>o.value===origen)) {const option=document.createElement('option');option.value=origen;option.textContent=origen;element.appendChild(option);}
            element.value=origen;element.disabled=true;
        } else if (element instanceof HTMLInputElement) {element.value=origen;element.readOnly=true;}
    }
    function bind(root) {
        if (root.matches?.('input,select')) {window.nucleusAplicarAutocompletado(root);contextualProject(root);}
        root.querySelectorAll?.('input,select').forEach(input=>{window.nucleusAplicarAutocompletado(input);contextualProject(input);});
    }
    window.nucleusCatalogEditor = (cell,onRendered,success,cancel) => {
        const input=document.createElement('input');input.type='text';input.value=cell.getValue() ?? '';
        Object.assign(input.style,{width:'100%',height:'100%',boxSizing:'border-box',padding:'4px 8px'});
        window.nucleusAplicarAutocompletado(input,cell.getField());
        let finished=false;const finish=()=>{if(!finished){finished=true;success(input.value);}};
        input.addEventListener('blur',finish);input.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();finish();}else if(event.key==='Escape'){finished=true;cancel();}});
        onRendered(()=>{input.focus();input.select();});return input;
    };
    // Los editores de la grilla se enlazan al recibir foco. Recorrer cada celda
    // añadida por Tabulator repetía búsquedas DOM durante cada cambio de pestaña.
    const start=()=>{bind(document);new MutationObserver(records=>{for(const record of records) for(const node of record.addedNodes) if(node.nodeType===1 && !node.closest('.tabulator')) bind(node);}).observe(document.body,{childList:true,subtree:true});};
    document.addEventListener('focusin',event=>{window.nucleusAplicarAutocompletado(event.target);contextualProject(event.target);});
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
    document.addEventListener('click',event=>{document.querySelectorAll('.flm-resource-menu[open]').forEach(menu=>{if(!menu.contains(event.target))menu.open=false;});});
})();
