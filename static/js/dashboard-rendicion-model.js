/* Agregaciones puras del panel de solicitudes sin sustento. */
(function(){
 'use strict';
 const base=window.NucleusFinanceModel;
 const budget=row=>{const n=base.normalize(row.presupuesto);return ['COSTO COBRA','GASTO COBRA'].includes(n)?'GASTO COBRA':['REFACTURABLE','REFRACTURABLE'].includes(n)?'REFACTURABLE':row.presupuesto||'Sin presupuesto';};
 const client=row=>{const n=base.normalize(row.proyecto);return n.includes('PEXT')?'PEXT':n.includes('INTEGRATEL')||n.includes('MOVISTAR')?'INTEGRATEL':n.includes('CLARO')?'CLARO':n.includes('ENTEL')?'ENTEL':row.proyecto||'Sin cliente';};
 const applicant=row=>row.responsable_validacion&&row.responsable_validacion!=='Sin responsable'?row.responsable_validacion:'Sin responsable';
 const amount=row=>base.amount(row,'rendicion');
 function grouped(rows,key,label){
  const map=new Map();
  rows.forEach(row=>{const k=key(row),item=map.get(k)||{key:k,label:label(row),count:0,amount:0,budgets:{},counts:{}};const b=budget(row);item.count++;item.amount+=amount(row);item.budgets[b]=(item.budgets[b]||0)+amount(row);item.counts[b]=(item.counts[b]||0)+1;map.set(k,item);});
  return [...map.values()].sort((a,b)=>b.amount-a.amount||b.count-a.count||a.label.localeCompare(b.label));
 }
 function snapshot(rows,period='day'){
  const pending=rows.filter(row=>row.estado==='DEPOSITADO');
  const supportedRows=rows.filter(row=>['CON SUSTENTO','SUSTENTADO'].includes(row.estado));
  const archivedRows=supportedRows.filter(row=>base.normalize(row.subestado)==='ARCHIVADO');
  const awaitingRows=supportedRows.filter(row=>base.normalize(row.subestado)!=='ARCHIVADO');
  const clients=grouped(pending,client,client);
  const budgets=base.group(pending,budget,amount);
  const people=grouped(pending,row=>base.person(row,'rendicion'),row=>row.beneficiario||'Sin beneficiario');
  const byClient=Object.fromEntries(['ENTEL','CLARO','INTEGRATEL'].map(c=>[c,grouped(pending.filter(row=>client(row)===c),row=>base.person(row,'rendicion'),row=>row.beneficiario||'Sin beneficiario')]));
  const dated=pending.filter(row=>/^\d{4}-\d{2}-\d{2}$/.test(row.dia_solicitud||row.dia||''));
  const dateOf=row=>(row.dia_solicitud||row.dia).slice(0,period==='month'?7:10);
  const periods=[...new Set(dated.map(dateOf))].sort();
  const budgetNames=[...new Set(pending.map(budget))].sort();
  const trend=budgetNames.map(label=>{const map=new Map();dated.filter(row=>budget(row)===label).forEach(row=>map.set(dateOf(row),(map.get(dateOf(row))||0)+amount(row)));return {label,values:periods.map(p=>map.get(p)||0)};});
  return {pending,count:pending.length,amount:base.sum(pending,amount),peopleCount:people.filter(p=>!p.key.startsWith('sin-dni:')).length,
   invalidDocuments:pending.filter(row=>row.documento_valido===false).length,
   unpaid:pending.filter(row=>!row.pago_registrado).length,
   supported:base.sum(supportedRows,amount),
   awaitingValidation:base.sum(awaitingRows,amount),awaitingCount:awaitingRows.length,
   awaitingClients:grouped(awaitingRows,client,client),awaitingBudgetNames:[...new Set(awaitingRows.map(budget))].sort(),
   archived:base.sum(archivedRows,amount),archivedCount:archivedRows.length,
   archivedClients:grouped(archivedRows,client,client),archivedBudgetNames:[...new Set(archivedRows.map(budget))].sort(),
   supportedClients:grouped(supportedRows,client,client),supportedCount:supportedRows.length,
   supportedBudgetNames:[...new Set(supportedRows.map(budget))].sort(),
   clients,budgets,people,byClient,applicants:grouped(pending,applicant,applicant),budgetNames,periods,trend,undated:pending.length-dated.length};
 }
 window.NucleusRendicionExecutive={snapshot,budget,client,applicant};
}());
