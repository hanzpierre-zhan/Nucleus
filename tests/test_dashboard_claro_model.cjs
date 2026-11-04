const assert=require('node:assert/strict');
const {snapshot}=require('../static/js/dashboard-claro-model.js');
const rows=[{id:'1',creacion:'2026-09-30T10:00:00',cierre:'2026-10-02T10:00:00',completado:true,sla:true},{id:'2',creacion:'2026-10-01T10:00:00',cierre:null,completado:false,sla:null},{id:'3',creacion:'2026-10-01T10:00:00',cierre:'2026-10-02T12:00:00',completado:true,sla:false}];
let s=snapshot(rows,{desde:'2026-10-01',hasta:'2026-10-02',escala:'dia'});
assert.equal(s.creados,2);assert.equal(s.completados,2);assert.equal(s.abiertos,1);assert.equal(s.sla,50);assert.deepEqual(s.velocidad,[0,2,0]);assert.equal(s.series[0].backlog,3);assert.equal(s.series[1].backlog,1);
s=snapshot([],{desde:'2026-10-01',hasta:'2026-10-02',escala:'dia'});assert.equal(s.sla,null);assert.equal(s.promedio,null);
console.log('Modelo Claro: cálculos verificados');
