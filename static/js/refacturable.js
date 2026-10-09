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
    const manualFields = new Set(['fecha_fin', 'estatus', 'monto_cobra', 'numero_expense', 'estado_expense', 'observacion', 'mes_cierre', 'numero_po']);
    function headerFormatter(cell) {
        const definition = cell.getColumn().getDefinition();
        const header = document.createElement('span'); header.className = 'ref-column-title';
        const filter = document.createElement('button'); filter.type = 'button'; filter.className = 'ref-filter-icon';
        filter.title = `Filtrar ${definition.title}`; filter.setAttribute('aria-label', filter.title);
        filter.innerHTML = '<i class="fa-solid fa-filter" aria-hidden="true"></i>';
        filter.addEventListener('click', event => {
            event.stopPropagation(); cell.getColumn().getElement().querySelector('.tabulator-header-filter input')?.focus();
        });
        header.appendChild(filter);
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
    const table = new Tabulator('#ref-grid', {
        height: '100%', layout: 'fitData', rowHeight: 44,
        pagination: true, paginationMode: 'local', paginationSize: 200,
        paginationSizeSelector: [100, 200, 500, 1000], paginationButtonCount: 1,
        paginationElement: document.getElementById('ref-pagination'),
        placeholder: 'No hay cotizaciones aprobadas para mostrar.',
        columnDefaults: {vertAlign: 'middle'},
        columns: [
            column('COTIZACIÓN', 'cotizacion', {frozen: true, width: 185}),
            column('ESTADO DE COTIZACIÓN', 'estado_cotizacion', {width: 185, formatter: statusFormatter}),
            column('GESTOR OPERATIVO', 'gestor'),
            column('NÚMERO DE WO', 'numero_wo', {width: 205}),
            column('FECHA DE FIN', 'fecha_fin', {width: 145}),
            column('ESTATUS', 'estatus', {width: 135, formatter: statusFormatter}),
            column('MONTO COBRA', 'monto_cobra', {hozAlign: 'right', formatter: moneyFormatter, width: 150}),
            column('MARGEN', 'margen', {hozAlign: 'right', formatter: moneyFormatter, width: 150}),
            column('MONTO HW', 'monto_hw', {hozAlign: 'right', formatter: moneyFormatter, width: 150}),
            column('NÚMERO EXPENSE', 'numero_expense'),
            column('ESTADO EXPENSE', 'estado_expense', {formatter: statusFormatter}),
            column('OBSERVACIÓN', 'observacion', {width: 260}),
            column('MES DE CIERRE', 'mes_cierre', {width: 150}),
            column('NÚMERO DE PO', 'numero_po'),
            {title: 'ACCIONES', width: 110, headerSort: false, formatter: () => {
                const button = document.createElement('button');
                button.type = 'button'; button.className = 'action-pill pill-blue';
                button.textContent = 'Editar'; button.title = 'Editar seguimiento refacturable';
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
            const response = await fetch('/refacturable/api/registros');
            const data = await nucleusLeerRespuestaJSON(response);
            if (!response.ok) throw new Error(data.error || 'No se pudieron cargar las cotizaciones.');
            total = data.registros.length;
            await table.replaceData(data.registros);
            updateCount(); message.textContent = '';
        } catch (error) { message.textContent = error.message; }
    }
    function parseMoney(value) {
        let text = String(value ?? '').trim().replace(/^(S\/\.?|PEN)\s*/i, '').replace(/\s/g, '');
        if (!text) return null;
        if (text.includes(',') && text.includes('.')) text = text.lastIndexOf('.') > text.lastIndexOf(',') ? text.replace(/,/g, '') : text.replace(/\./g, '').replace(',', '.');
        else text = text.replace(',', '.');
        const number = Number(text);
        return Number.isFinite(number) ? number : null;
    }
    function previewMargin() {
        const cobra = parseMoney(form.elements.monto_cobra.value);
        const hw = parseMoney(editing?.monto_hw);
        document.getElementById('ref-margin').textContent = cobra !== null && hw !== null ? money.format(cobra - hw) : '—';
    }
    function openEditor(row) {
        editing = row; form.reset();
        document.getElementById('ref-cotizacion').textContent = row.cotizacion;
        for (const element of form.elements) if (element.name) element.value = row[element.name] || '';
        document.getElementById('ref-hw').value = row.monto_hw === '' ? 'Pendiente de importe' : money.format(Number(row.monto_hw));
        document.getElementById('ref-form-error').textContent = '';
        previewMargin(); dialog.showModal();
    }
    form.elements.monto_cobra.addEventListener('input', previewMargin);
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (!editing) return;
        const button = document.getElementById('ref-save');
        const errorLabel = document.getElementById('ref-form-error');
        button.disabled = true; errorLabel.textContent = '';
        try {
            const changes = Object.fromEntries(new FormData(form));
            const response = await fetch(`/refacturable/api/registros/${editing.id}`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(changes)});
            const data = await nucleusLeerRespuestaJSON(response);
            if (!response.ok) throw new Error(data.error || 'No se pudieron guardar los cambios.');
            await table.updateData([data.registro]);
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
        const book = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(book, sheet, 'Refacturable');
        XLSX.writeFile(book, 'Refacturable.xlsx');
    });
    table.on('dataFiltered', updateCount); table.on('pageLoaded', updateCount);
    table.on('tableBuilt', load);
})();
