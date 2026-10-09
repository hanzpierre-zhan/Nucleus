const assert = require('assert');
const build = () => { const IS_FLM_CLARO_INTEGRATEL = true; const fieldName = 'CODIGO INTERNO'; const colDef = {}; const restColumns = []; let opened; const abrirWoModal = row => opened = row; const escapeHtml = v => v; const collect = () => {        if (IS_FLM_CLARO_INTEGRATEL && fieldName === 'CODIGO INTERNO') {
            colDef.title = 'CÓDIGO INTERNO';
            colDef.editor = false;
            colDef.formatter = cell => `<span class="wo-link">${escapeHtml(cell.getValue() || '')}</span>`;
            colDef.cellClick = (event, cell) => abrirWoModal(cell.getRow());
            restColumns.push(colDef);
            return;
        }

}; collect(); const tableColumns = [...restColumns]; assert.equal(tableColumns.length, 1); assert.equal(tableColumns[0].title, 'CÓDIGO INTERNO'); const row={getData:()=>({_WO_PENDIENTE:true})}; tableColumns[0].cellClick(null,{getRow:()=>row}); assert.equal(opened,row); }; build();