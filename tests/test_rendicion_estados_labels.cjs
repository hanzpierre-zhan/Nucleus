const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
const root=path.join(__dirname,'..');
const context=vm.createContext({window:{}});
vm.runInContext(fs.readFileSync(path.join(root,'static/js/rendicion-estados-labels.js'),'utf8'),context);
const expected={'PENDIENTE':'1.PENDIENTE','VALIDADO':'2.VALIDADO','DEPOSITADO':'3.DEPOSITADO','CON SUSTENTO':'4.CON SUSTENTO','SUSTENTADO':'5.SUSTENTADO','ANULADO':'0.ANULADO','RECHAZADO':'*.RECHAZADO','TRANSITO':'*.TRANSITO'};
for(const [raw,label] of Object.entries(expected))assert.equal(context.window.NucleusRendicionStates.label(raw),label);
assert.equal(context.window.NucleusRendicionStates.label('OBSERVADO'),'OBSERVADO');
const controller=fs.readFileSync(path.join(root,'templates/index/table-controller.html'),'utf8');
context.IS_RENDICION=true;context.fieldName='ESTADO';context.colDef={};
context.REND_ESTADO_COLORS=Object.fromEntries(Object.keys(expected).map(k=>[k,{bg:'#000',fg:'#fff'}]));
context.rendEstadoDe=row=>row.ESTADO;
context.listaHeaderFilter=(options,label)=>options.map(value=>({value,label:label(value)}));
const begin=controller.indexOf("if (IS_RENDICION && fieldName === 'ESTADO')");
const end=controller.indexOf("if (IS_RENDICION && fieldName === 'MOTIVO RECHAZO')",begin);
vm.runInContext(controller.slice(begin,end),context);
for(const [raw,label] of Object.entries(expected)){
 assert.equal(context.colDef.headerFilter.find(o=>o.value===raw).label,label);
 const row={ESTADO:raw};assert.ok(context.colDef.formatter({getValue:()=>row.ESTADO}).includes(label));
 assert.equal(row.ESTADO,raw);
}
console.log('OK: ocho etiquetas numeradas, filtros con códigos originales y flujo conservado');
