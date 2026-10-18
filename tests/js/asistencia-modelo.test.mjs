import test from "node:test";
import assert from "node:assert/strict";
import { clave, filtrarYOrdenar } from "../../static/js/asistencia/modelo.mjs";
import { crearApi } from "../../static/js/asistencia/api.mjs";

const personas = [
  {personal_id:1,proyecto_id:2,nombre:"Zulema",documento:"001",proyecto:"Claro",marcas:{1:{estado:"FALTA"}}},
  {personal_id:2,proyecto_id:2,nombre:"Ana",documento:"002",proyecto:"Claro",marcas:{1:{estado:"PRESENTE"}}},
];
const estados={FALTA:"Falta",PRESENTE:"Presente",PENDIENTE:"Sin marcar"};
test("identidad independiente por persona, proyecto y día",()=>{
  assert.equal(clave(personas[0],5),"1:2:5");
  assert.notEqual(clave(personas[0],5),clave({...personas[0],proyecto_id:3},5));
});
test("orden A–Z y Z–A sin modificar el catálogo original",()=>{
  const ordenar=d=>filtrarYOrdenar(personas,"",{campo:"nombre",direccion:d},estados,new Map()).map(p=>p.nombre);
  assert.deepEqual(ordenar(1),["Ana","Zulema"]);
  assert.deepEqual(ordenar(-1),["Zulema","Ana"]);
  assert.equal(personas[0].nombre,"Zulema");
});
test("búsqueda por documento y proyecto, conservando ceros",()=>{
  assert.equal(filtrarYOrdenar(personas,"001",{campo:"nombre",direccion:1},estados,new Map()).length,1);
  assert.equal(filtrarYOrdenar(personas,"CLARO",{campo:"nombre",direccion:1},estados,new Map()).length,2);
});
test("orden del día considera marcas pendientes antes de guardar",()=>{
  const cambios=new Map([[clave(personas[1],1),{estado:"FALTA"}],[clave(personas[0],1),{estado:"PRESENTE"}]]);
  assert.deepEqual(filtrarYOrdenar(personas,"",{campo:1,direccion:1},estados,cambios).map(p=>p.nombre),["Ana","Zulema"]);
});
test("transporte conserva CSRF y cuerpo de las marcas",async()=>{
  const original=globalThis.fetch;
  try {
    globalThis.fetch=async(url,opciones)=>{
      assert.equal(url,"/api/asistencia/dia");
      assert.equal(opciones.headers["X-Asistencia-CSRF"],"prueba");
      assert.deepEqual(JSON.parse(opciones.body),{fecha:"2026-10-17"});
      return {ok:true,json:async()=>({success:true})};
    };
    assert.deepEqual(await crearApi("prueba")("/api/asistencia/dia",{fecha:"2026-10-17"}),{success:true});
  } finally {globalThis.fetch=original;}
});
test("un conflicto del servidor conserva su mensaje",async()=>{
  const original=globalThis.fetch;
  try {
    globalThis.fetch=async()=>({ok:false,json:async()=>({error:"Versión desactualizada"})});
    await assert.rejects(crearApi("x")("/api/asistencia/dia"),/Versión desactualizada/);
  } finally {globalThis.fetch=original;}
});
