/* Etiquetas de presentación; los códigos del flujo se conservan. */
(function(root){
 'use strict';
 const labels=Object.freeze({
  'PENDIENTE':'1.PENDIENTE','VALIDADO':'2.VALIDADO','DEPOSITADO':'3.DEPOSITADO',
  'CON SUSTENTO':'4.CON SUSTENTO','SUSTENTADO':'5.SUSTENTADO','ANULADO':'0.ANULADO',
  'RECHAZADO':'*.RECHAZADO','TRANSITO':'*.TRANSITO'
 });
 function label(value){const raw=String(value??'').trim();return labels[raw.toUpperCase()]||raw;}
 root.NucleusRendicionStates=Object.freeze({labels,label});
})(typeof window==='undefined'?globalThis:window);
