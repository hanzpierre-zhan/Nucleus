(() => {
    'use strict';
    const dialog = document.getElementById('ref-editor');
    const form = document.getElementById('ref-form');
    const message = document.getElementById('ref-message');
    const settings = document.getElementById('ref-settings');
    const settingsButton = document.getElementById('ref-settings-toggle');
    const money = new Intl.NumberFormat('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    let editing = null;
    let total = 0;
    function moneyFormatter(cell) {
        const value = cell.getValue();
        return value === '' || value == null ? '—' : money.format(Number(value));
    }
    const manualFields = new Set(['codigo_ajb_ejb', 'numero_expense', 'estado_liquidacion', 'observacion', 'mes_cierre', 'numero_po']);
    function headerFormatter(cell) {
        const definition = cell.getColumn().getDefinition();
        const header = document.createElement('span'); header.className = 'ref-column-title';
        const filter = document.createElement('button'); filter.type = 'button'; filter.className = 'ref-filter-icon';
        filter.title = `Filtrar ${definition.title}`; filter.setAttribute('aria-label', filter.title);
        filter.innerHTML = '<i class="fa-solid fa-filter" aria-hidden="true"></i>';
        filter.addEventListener('click', event => {
            event.stopPropagation(); cell.getColumn().getElement().querySelector('.tabulator-header-filter input')?.focus();
        });
        if (definition.headerFilter !== false) header.appendChild(filter);
        if (manualFields.has(definition.field)) {
            const edit = document.createElement('i'); edit.className = 'fa-solid fa-pen-to-square ref-edit-icon';
            edit.title = 'Campo manual: editar desde Acciones'; header.appendChild(edit);
        }
        const label = document.createElement('span'); label.textContent = definition.title; header.appendChild(label);
        return header;
    }
    function statusFormatter(cell) {
        const text = String(cell.getValue() || '');
        if (!text) return '';
        const pill = document.createElement('span'); pill.className = 'ref-status'; pill.textContent = text;
        const colors = {'Aprobado': 'success', 'Atendido': 'success', 'Validado': 'success', 'Culminado': 'success', 'En Aprobación': 'warning', 'Pendiente': 'warning', 'Stand by': 'warning', 'Rechazado': 'danger', 'Observado': 'danger'};
        pill.classList.add('ref-status-' + (colors[text] || 'neutral')); return pill;
    }
    function column(title, field, extra = {}) {
        return {title, field, width: 170, minWidth: 110, headerFilter: 'input', titleFormatter: headerFormatter, formatter: 'plaintext', ...extra};
    }
    function showSustento(row) {
        const body = document.getElementById('liq-sustento-body'); body.replaceChildren();
        document.getElementById('liq-sustento-title').textContent = 'Sustento de obra · ' + row.cotizacion;
        const dates = document.createElement('p'); dates.textContent = `Inicio: ${row.fecha_inicio || 'Pendiente'} · Fin: ${row.fecha_fin || 'Pendiente'}`; body.appendChild(dates);
        for (const phase of ['inicio', 'proceso', 'cierre']) {
            const section = document.createElement('section'); section.className = 'ref-section';
            const title = document.createElement('h3'); title.textContent = phase.charAt(0).toUpperCase() + phase.slice(1); section.appendChild(title);
            const comment = document.createElement('p'); comment.className = 'liq-comment'; comment.textContent = row.comentarios?.[phase] || 'Sin comentarios'; section.appendChild(comment);
            const gallery = document.createElement('div'); gallery.className = 'liq-gallery';
            for (const url of row.fotos?.[phase] || []) {
                if (!safeUrl(url)) continue;
                const link = document.createElement('a'); link.href = url; link.target = '_blank'; link.rel = 'noopener';
                const image = document.createElement('img'); image.src = url; image.alt = 'Evidencia de ' + phase; image.loading = 'lazy'; link.appendChild(image); gallery.appendChild(link);
            }
            section.appendChild(gallery); body.appendChild(section);
        }
        document.getElementById('liq-sustento').showModal();
    }
    function safeUrl(url) { return typeof url === 'string' && (/^\/(?!\/)/.test(url) || /^https?:\/\//i.test(url)); }
    function documentButton(cell, kind) {
        const row = cell.getRow().getData(); const state = row.documentos?.[kind] || 'Pendiente';
        if (state !== 'Completo' && !(kind === 'sustento' && state !== 'No aplica' && Object.values(row.fotos || {}).some(fotos => fotos.length))) { const label = document.createElement('span'); label.textContent = state; label.className = 'ref-status ref-status-neutral'; return label; }
        const button = document.createElement(kind === 'sustento' ? 'button' : 'a'); button.className = 'action-pill pill-blue'; button.textContent = kind === 'sustento' ? 'Ver sustento' : 'Descargar';
        if (kind === 'sustento') {button.type = 'button'; button.addEventListener('click', () => showSustento(row));}
        else { const url = kind === 'cotizacion' ? `/liquidaciones/api/registros/${row.id}/pdf` : (kind === 'factura' ? row.factura_proveedor : row.correo_cliente); if (safeUrl(url)) {button.href = url; button.target = '_blank'; button.rel = 'noopener';} }
        return button;
    }
    document.getElementById('liq-sustento-close').addEventListener('click', () => document.getElementById('liq-sustento').close());
    const table = new Tabulator('#ref-grid', {
        height: '100%', layout: 'fitData', rowHeight: 44,
        pagination: true, paginationMode: 'local', paginationSize: 200,
        paginationSizeSelector: [100, 200, 500, 1000], paginationButtonCount: 1,
        paginationElement: document.getElementById('ref-pagination'),
        placeholder: 'No hay cotizaciones aprobadas para mostrar.',
        columnDefaults: {vertAlign: 'middle'},
        columns: [
            column('N', 'correlativo', {frozen: true, width: 85, minWidth: 65}),
            column('N° COTIZACIÓN', 'cotizacion', {width: 185}),
            column('ESTADO DE COTIZACIÓN', 'estado_cotizacion', {width: 185, formatter: statusFormatter}),
            column('GESTOR OPERATIVO', 'gestor'),
            column('FECHA INICIO DE OBRA', 'fecha_inicio', {width: 155}),
            column('FECHA FIN DE OBRA', 'fecha_fin', {width: 155}),
            column('ESTADO DE EJECUCIÓN', 'estatus', {width: 170, formatter: statusFormatter}),
            column('SUSTENTO DE OBRA', 'sustento', {headerFilter: false, formatter: cell => documentButton(cell, 'sustento')}),
            column('FACTURA DEL PROVEEDOR', 'factura_proveedor', {headerFilter: false, formatter: cell => documentButton(cell, 'factura')}),
            column('CORREO DEL CLIENTE', 'correo_cliente', {headerFilter: false, formatter: cell => documentButton(cell, 'correo')}),
            column('COTIZACIÓN GENERADA', 'cotizacion_generada', {headerFilter: false, formatter: cell => documentButton(cell, 'cotizacion')}),
            column('AVANCE', 'avance', {width: 140, formatter: cell => {
                const value = Number(cell.getValue()); const el = document.createElement('span');
                el.className = 'ref-status ref-status-' + (value === 100 ? 'success' : 'warning');
                el.textContent = value + '%'; el.title = 'Respaldos completos / respaldos aplicables'; return el;
            }}),
            column('MONTO FACTURA PROVEEDOR', 'monto_factura_proveedor', {hozAlign: 'right', formatter: moneyFormatter, width: 190}),
            column('MONTO DE COTIZACIÓN', 'monto_hw', {hozAlign: 'right', formatter: moneyFormatter, width: 185}),
            column('CÓDIGO AJB / EJB', 'codigo_ajb_ejb'),
            column('NÚMERO EXPENSE', 'numero_expense'),
            column('ESTADO DE LIQUIDACIÓN', 'estado_liquidacion', {width: 190, formatter: statusFormatter}),
            column('OBSERVACIÓN', 'observacion', {width: 260}),
            column('MES DE CIERRE', 'mes_cierre', {width: 150, formatter: cell => {
                const value = String(cell.getValue() || ''); if (!/^\d{4}-\d{2}$/.test(value)) return '—';
                const meses = ['ENE','FEB','MAR','ABR','MAY','JUN','JUL','AGO','SEP','OCT','NOV','DIC'];
                return meses[Number(value.slice(5)) - 1] + '-' + value.slice(0, 4);
            }}),
            column('NÚMERO DE PO', 'numero_po'),
            column('NOMBRE DEL PROYECTO', 'nombre_proyecto', {width: 185}),
            {title: 'ACCIONES', width: 110, headerSort: false, formatter: () => {
                const button = document.createElement('button');
                button.type = 'button'; button.className = 'action-pill pill-blue';
                button.textContent = 'Editar'; button.title = 'Editar liquidación';
                return button;
            }, cellClick: (event, cell) => openEditor(cell.getRow().getData())}
        ]
    });
    function updateCount() {
        const count = table.getDataCount('active');
        const badge = document.getElementById('ref-count');
        badge.textContent = `${count} / ${total}`;
        badge.title = `${count} registros visibles de ${total} en total`;
        const labels = {first: ['«', 'Primera página'], prev: ['‹', 'Página anterior'], next: ['›', 'Página siguiente'], last: ['»', 'Última página']};
        document.querySelectorAll('#ref-pagination .tabulator-page').forEach(button => {
            const key = button.dataset.page || (button.textContent || '').trim().toLowerCase();
            if (labels[key]) {
                button.textContent = labels[key][0];
                button.title = labels[key][1]; button.setAttribute('aria-label', labels[key][1]);
            }
        });
    }
    async function load() {
        message.textContent = 'Cargando cotizaciones aprobadas…';
        try {
            const response = await fetch('/liquidaciones/api/registros');
            const data = await nucleusLeerRespuestaJSON(response);
            if (!response.ok) throw new Error(data.error || 'No se pudieron cargar las cotizaciones.');
            total = data.registros.length;
            await table.replaceData(data.registros);
            updateCount(); message.textContent = '';
        } catch (error) { message.textContent = error.message; }
    }
    function openEditor(row) {
        editing = row; form.reset();
        document.getElementById('ref-cotizacion').textContent = row.cotizacion;
        for (const element of form.elements) if (element.name) element.value = row[element.name] || (element.name.startsWith('no_aplica_') ? '0' : '');
        document.getElementById('ref-form-error').textContent = '';
        dialog.showModal();
    }
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (!editing) return;
        const button = document.getElementById('ref-save');
        const errorLabel = document.getElementById('ref-form-error');
        button.disabled = true; errorLabel.textContent = '';
        try {
            const changes = Object.fromEntries(new FormData(form));
            const response = await fetch(`/liquidaciones/api/registros/${editing.id}`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(changes)});
            const data = await nucleusLeerRespuestaJSON(response);
            if (!response.ok) throw new Error(data.error || 'No se pudieron guardar los cambios.');
            await table.updateData([data.registro]);
            table.getRow(data.registro.id)?.reformat();
            dialog.close(); message.textContent = 'Cambios guardados.';
        } catch (error) { errorLabel.textContent = error.message; }
        finally { button.disabled = false; }
    });
    document.querySelectorAll('.ref-close').forEach(button => button.addEventListener('click', () => dialog.close()));
    function closeSettings() { settings.classList.remove('show'); settingsButton.setAttribute('aria-expanded', 'false'); }
    settingsButton.addEventListener('click', () => settingsButton.setAttribute('aria-expanded', String(settings.classList.toggle('show'))));
    document.addEventListener('click', event => { if (!event.target.closest('.ref-settings-wrap')) closeSettings(); });
    document.addEventListener('keydown', event => { if (event.key === 'Escape') closeSettings(); });
    document.getElementById('ref-export').addEventListener('click', () => {
        closeSettings();
        const columns = table.getColumns().map(col => col.getDefinition()).filter(col => col.field);
        const rows = table.getData('active').map(row => Object.fromEntries(columns.map(col => [col.title, row[col.field] ?? ''])));
        const sheet = rows.length ? XLSX.utils.json_to_sheet(rows) : XLSX.utils.aoa_to_sheet([columns.map(col => col.title)]);
        const book = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(book, sheet, 'Liquidaciones');
        XLSX.writeFile(book, 'Liquidaciones.xlsx');
    });
    table.on('dataFiltered', updateCount); table.on('pageLoaded', updateCount);
    table.on('tableBuilt', load);
})();
