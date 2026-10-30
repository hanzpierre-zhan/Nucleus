/* Ficha de sustento exclusiva de Cotizaciones; reutiliza las bitácoras existentes. */
(function(){
 'use strict';
 let cleanup=()=>{};
 const fields=[['wo','Número WO'],['ajb_ejb','AJB / EJB'],['expense','Expense'],['site_name','Nombre del sitio | Site name'],['site_id','Código del sitio | Site ID'],['site_type','Tipo de site | Site type'],['site_address','Ubicación del sitio | Site address'],['district','Distrito | District'],['province','Provincia | Province'],['region','Región | Region'],['work_responsible','Responsable del trabajo | Work Responsible']];
 const fallback={site_name:['NOMBRE SITE','Nombre del sitio | Site name','Nombre','SITE NAME'],site_id:['CODIGO SITE','Código del sitio | Site ID','Site ID','Código'],site_address:['DIRECCION','Ubicación del sitio | Site address','Dirección'],site_type:['TIPO SITE','Tipo de site | Site type'],district:['DISTRITO','Distrito'],province:['PROVINCIA','Provincia'],region:['REGION','DEPARTAMENTO','Región']};
 const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
 window.cotSustentoUsaFicha=(ctx,entry)=>![entry.proyecto_nombre,ctx.cotData?.CLIENTE].some(value=>String(value||'').toUpperCase().includes('PEXT'));
 window.cotMontarSustentoAnterior=function(ctx,entry){
  const tabs=el('div','cot-wo-sustento-tabs');tabs.id='cot-sustento-wo-tabs';ctx.lista.forEach((w,i)=>{const b=el('button','action-pill'+(i===ctx.index?' pill-blue':''),w.wo||'Sustento sin WO');b.type='button';b.onclick=()=>cotSeleccionarSustentoWo(i);tabs.append(b);});document.getElementById('wo-panel-evidencia').prepend(tabs);
  if(!ctx.aprobado&&!entry.legacy&&cotPuedeGestionar()){const button=el('button','mar-btn-primary','Validar sustento');button.id='cot-btn-guardar-sustento';button.type='button';button.style.cssText='width:auto;padding:0 12px;';button.onclick=async()=>{button.disabled=true;try{await cotGuardarSustentoSeleccionado(true);cerrarWoModal();}catch(error){nucleusAlert(error.message);}finally{button.disabled=false;}};document.getElementById('btn-wo-copiar').before(button);}
 };
 window.cotLimpiarFichaSustento=()=>cleanup();
 window.cotLeerFichaSustento=()=>({...Object.fromEntries(fields.map(([key])=>[key,document.getElementById('cot-ficha-'+key)?.value||''])),item_details:cotLeerDatosItems()});
 window.cotMontarFichaSustento=function(ctx,entry,data,editable){
  cleanup();const moves=[],events=new AbortController();let timer;let request;
  const modal=document.getElementById('modal-wo');modal.classList.add('cot-sustento-amplio');
  document.querySelectorAll('#wo-panel-evidencia>.wo-section>.wo-section-title').forEach(title=>{[...title.childNodes].filter(n=>n.nodeType===3&&n.textContent.includes('Evidencia')).forEach(n=>{const old=n.textContent;n.textContent=' Sustento de la cotización ';moves.push(()=>n.textContent=old);});});
  const headerTitle=el('h2','cot-sustento-title','Sustento de la cotización');document.querySelector('#modal-wo .wo-head-left').prepend(headerTitle);moves.push(()=>headerTitle.remove());
  const form=el('div','cot-ficha');form.id='cot-sustento-ficha';
  const card=el('section','cot-ficha-card'),heading=el('div','cot-ficha-heading');heading.append(el('h3',null,'Datos del trabajo y del sitio'),el('span',null,'Ficha de sustento'));card.append(heading);
  const grid=el('div','cot-ficha-grid');const manual=data._SUSTENTO_MANUAL||{};
  const quoteLabel=el('label','cot-ficha-field cot-ficha-quotation_number'),quoteInput=el('input');quoteInput.type='text';quoteInput.id='cot-ficha-quotation_number';quoteInput.readOnly=true;quoteInput.value=ctx.cotData?.['N° COTIZACION']||ctx.key;quoteLabel.append(el('span',null,'N° Presupuesto o Trabajo | Quotation or Work number'),quoteInput);grid.append(quoteLabel);
  fields.forEach(([key,title])=>{const label=el('label','cot-ficha-field cot-ficha-'+key),input=el('input');input.type='text';input.id='cot-ficha-'+key;input.autocomplete='off';input.maxLength=key==='site_address'?2000:key==='wo'?100:300;input.disabled=!editable;input.value=manual[key]??(key==='wo'?entry.wo:(fallback[key]||[key.toUpperCase()]).map(k=>data[k]||ctx.cotData?.[k]).find(Boolean)||'');label.append(el('span',null,title),input);grid.append(label);});card.append(grid);form.append(card);
  function move(n,parent){const mark=document.createComment('ficha-original');n.before(mark);moves.push(()=>{mark.replaceWith(n);});parent.append(n);}
  const dates=document.getElementById('wo-ejecucion-fechas');dates.before(form);move(dates,card);
  const responsible=grid.querySelector('.cot-ficha-work_responsible');dates.prepend(responsible);moves.push(()=>responsible.remove());
  dates.querySelectorAll('.wo-field label').forEach((label,i)=>{const old=label.textContent;label.textContent=i===0?'Fecha de inicio | Start date':'Fecha de fin | End date';moves.push(()=>label.textContent=old);});
  const responsibleInput=responsible.querySelector('input'),responsibleList=el('datalist');responsibleList.id='cot-work-responsibles';responsibleInput.setAttribute('list',responsibleList.id);responsible.append(responsibleList);
  const control=el('div','select-options-control');responsibleInput.before(control);control.append(responsibleInput);
  let responsibleOptions=[];
  const fillResponsibleOptions=values=>{responsibleOptions=values;responsibleList.replaceChildren(...values.map(value=>{const option=el('option');option.value=value;return option;}));};
  fetch('/api/cotizacion/sustento/responsables',{signal:events.signal}).then(r=>nucleusLeerRespuestaJSON(r)).then(j=>{if(form.isConnected)fillResponsibleOptions(j.opciones||[]);}).catch(()=>{});
  if(['zeno','suport','supervisor'].includes(document.body.dataset.optionsRole)){
   const manage=el('button','action-pill pill-neutral select-options-button');manage.type='button';manage.innerHTML='<i class="fa-solid fa-sliders" aria-hidden="true"></i>';manage.title='Agregar o quitar responsables del trabajo';manage.setAttribute('aria-label',manage.title);control.append(manage);
   manage.addEventListener('click',async()=>{const result=await nucleusOptionsDialog('Opciones · Responsable del trabajo',responsibleOptions);if(result===null)return;manage.disabled=true;try{const r=await fetch('/api/cotizacion/sustento/responsables',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({opciones:result.split('\n').map(v=>v.trim()).filter(Boolean)})});const j=await nucleusLeerRespuestaJSON(r);if(!r.ok)throw Error(j.error||'No se guardaron las opciones.');fillResponsibleOptions(j.opciones);}catch(e){nucleusAlert(e.message);}finally{manage.disabled=false;}},{signal:events.signal});
  }

  const location=el('section','cot-ficha-card cot-ficha-location');location.append(el('h3',null,'Foto de la ubicación del sitio | Site location picture'));
  const upload=el('label','cot-ficha-picture'),image=el('img'),hint=el('span',null,'Seleccionar foto de ubicación'),input=el('input'),remove=el('button','cot-ficha-picture-remove');input.type='file';input.accept='image/jpeg,image/png,image/webp,image/heic,image/heif';input.hidden=true;input.disabled=!editable;image.alt='Ubicación del sitio';image.hidden=!manual.location_picture;if(manual.location_picture)image.src=manual.location_picture;hint.hidden=!!manual.location_picture;remove.type='button';remove.title='Eliminar foto de ubicación';remove.setAttribute('aria-label','Eliminar foto de ubicación');remove.innerHTML='<i class="fa-solid fa-xmark" aria-hidden="true"></i>';remove.hidden=!manual.location_picture||!editable;upload.append(image,hint,input,remove);location.append(upload);const status=el('p','cot-ficha-status',editable?'Imagen rectangular · JPG, PNG o WebP · máximo 20 MB':'Ficha de solo lectura');status.setAttribute('role','status');location.append(status);form.append(location);
  input.addEventListener('change',async()=>{const file=input.files[0];if(!file)return;if(file.size>20*1024*1024){status.textContent='La imagen supera los 20 MB.';input.value='';return;}ctx.uploads++;input.disabled=true;status.textContent='Guardando foto de ubicación…';try{const body=new FormData();body.append('key',ctx.key);body.append('wo',entry.wo);body.append('foto',file);const r=await fetch('/api/cotizacion/sustento/ubicacion',{method:'POST',body});const j=await nucleusLeerRespuestaJSON(r);if(!r.ok||!j.success)throw Error(j.error||'No se pudo subir la foto.');entry.wo_data._SUSTENTO_MANUAL={...(entry.wo_data._SUSTENTO_MANUAL||{}),location_picture:j.url};manual.location_picture=j.url;image.src=j.url;image.hidden=false;hint.hidden=true;remove.hidden=false;status.textContent='Foto guardada. Pulsa sobre la imagen para reemplazarla.';}catch(e){status.textContent=e.message;}finally{ctx.uploads--;input.disabled=!editable;input.value='';}},{signal:events.signal});
  remove.addEventListener('click',async event=>{event.preventDefault();event.stopPropagation();if(!editable||ctx.uploads||!manual.location_picture||!await nucleusConfirm('¿Eliminar la foto de ubicación del sitio?'))return;ctx.uploads++;remove.disabled=true;status.textContent='Eliminando foto…';try{const r=await fetch('/api/cotizacion/sustento/foto/eliminar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:ctx.key,wo:entry.wo,url:manual.location_picture})});const j=await nucleusLeerRespuestaJSON(r);if(!r.ok||!j.success)throw Error(j.error||'No se pudo eliminar la foto.');const actual={...(entry.wo_data._SUSTENTO_MANUAL||{})};delete actual.location_picture;entry.wo_data._SUSTENTO_MANUAL=actual;delete manual.location_picture;image.removeAttribute('src');image.hidden=true;hint.hidden=false;remove.hidden=true;status.textContent='Foto eliminada.';}catch(e){status.textContent=e.message;}finally{ctx.uploads--;remove.disabled=false;}},{signal:events.signal});
  const description=el('section','cot-ficha-card');description.append(el('h3',null,'Descripción del trabajo'));const texts=el('div','cot-ficha-texts');
  const names=['Antecedentes | Background','Objetivos | Objectives','Detalles del trabajo realizado | Details of the work performed'];
  ['inicio','proceso','cierre'].forEach((phase,i)=>{const textarea=document.getElementById('evidencia-bitacora-'+phase),wrap=textarea.closest('.wo-field'),label=wrap.querySelector('label'),oldLabel=label.innerHTML,oldPlaceholder=textarea.placeholder;move(wrap,texts);label.textContent=names[i];textarea.placeholder=names[i];textarea.rows=2;moves.push(()=>{label.innerHTML=oldLabel;textarea.placeholder=oldPlaceholder;textarea.removeAttribute('rows');});});description.append(texts);form.append(description);
  const gallery=document.getElementById('evidencia-inicio-proceso-cierre'),oldDisplay=gallery.style.display;gallery.style.display='none';moves.push(()=>gallery.style.display=oldDisplay);
  cotMontarFotosItems(form,ctx,entry,editable);
  const legacy=[];['INICIO','PROCESO','CIERRE'].forEach(phase=>{let urls=[];try{urls=JSON.parse(data['_EVIDENCIA_'+phase]||'[]');}catch(e){}if(Array.isArray(urls))urls.filter(Boolean).forEach(url=>legacy.push(url));});
  if(legacy.length){const previous=el('details','cot-ficha-photos');previous.append(el('summary',null,'Evidencias anteriores sin ítem asignado'));const images=el('div','cot-item-photos');legacy.forEach(url=>{const link=el('a','cot-item-photo'),img=el('img');link.href=url;link.target='_blank';link.rel='noopener';img.src=url;img.alt='Evidencia anterior';link.append(img);images.append(link);});previous.append(images);form.append(previous);}
  const copyButton=document.getElementById('btn-wo-copiar'),copyDisplay=copyButton.style.display;copyButton.style.display='none';moves.push(()=>copyButton.style.display=copyDisplay);
  document.getElementById('cot-btn-guardar-sustento')?.remove();
  if(editable&&!ctx.aprobado&&!entry.legacy&&cotPuedeGestionar()){
   const finish=el('button','mar-btn-primary','Enviar a Atendido');finish.id='cot-btn-enviar-atendido';finish.type='button';finish.style.cssText='width:auto;padding:0 12px;white-space:nowrap;';
   document.getElementById('btn-wo-save').before(finish);moves.push(()=>finish.remove());
   finish.addEventListener('click',async()=>{finish.disabled=true;try{await cotGuardarSustentoSeleccionado(true);cerrarWoModal();}catch(error){nucleusAlert(error.message);}finally{finish.disabled=false;}},{signal:events.signal});
  }
  const dossier=el('button','mar-btn-ghost','Generar expediente');dossier.id='cot-btn-generar-expediente';dossier.type='button';dossier.disabled=!ctx.items?.length;dossier.title='Descargar expediente fotográfico en Excel';dossier.style.cssText='width:auto;padding:0 12px;white-space:nowrap;';document.getElementById('btn-wo-save').before(dossier);moves.push(()=>dossier.remove());
  dossier.addEventListener('click',async()=>{dossier.disabled=true;dossier.textContent='Generando…';try{
   if(editable)await cotGuardarSustentoSeleccionado(false);
   const params=new URLSearchParams({key:ctx.key,wo:entry.wo});const response=await fetch('/api/cotizacion/sustento/expediente?'+params);
   if(!response.ok){const error=await nucleusLeerRespuestaJSON(response);throw Error(error.error||'No se pudo generar el expediente.');}
   const blob=await response.blob(),url=URL.createObjectURL(blob),link=el('a');link.href=url;link.download='Expediente_'+ctx.key+'.xlsx';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);
  }catch(error){nucleusAlert(error.message);}finally{dossier.disabled=!ctx.items?.length;dossier.textContent='Generar expediente';}},{signal:events.signal});

  if(ctx.lista.length>1){const chooser=el('label','cot-ficha-wo-selector','WO del sustento '),select=el('select');select.setAttribute('aria-label','WO del sustento');ctx.lista.forEach((w,i)=>{const option=el('option',null,w.wo||'Sin WO');option.value=String(i);option.selected=i===ctx.index;select.append(option);});select.addEventListener('change',()=>cotSeleccionarSustentoWo(Number(select.value)),{signal:events.signal});chooser.append(select);heading.append(chooser);}

  const siteFields=['site_name','site_id','site_address','site_type','district','province','region'];
  const suggestions={};const timers={};const requests={};
  siteFields.forEach(key=>{
   const field=document.getElementById('cot-ficha-'+key),list=el('datalist');list.id='cot-ficha-options-'+key;form.append(list);field.setAttribute('list',list.id);
   async function search(complete=false){
    requests[key]?.abort();const controller=new AbortController();requests[key]=controller;
    try{
     const params=new URLSearchParams({q:field.value,field:key,proyecto:ctx.cotData?.CLIENTE||entry.proyecto_nombre||''});
     const r=await fetch('/api/cotizacion/sustento/sites?'+params,{signal:controller.signal});const j=await nucleusLeerRespuestaJSON(r);
     if(!form.isConnected||controller.signal.aborted)return;
     suggestions[key]=j.sites||[];list.replaceChildren(...suggestions[key].map(item=>{const option=el('option');option.value=item[key];if(key==='site_id'||key==='site_name')option.label=item.site_key||item.site_name;return option;}));
     if(complete)apply();
    }catch(e){if(e.name!=='AbortError')console.warn('No se pudo cargar el catálogo de sites.');}
   }
   function apply(){
    if(!['site_name','site_id'].includes(key))return;
    let matches=(suggestions[key]||[]).filter(item=>item[key].toLocaleLowerCase()===field.value.trim().toLocaleLowerCase());
    if(matches.length>1){const other=key==='site_id'?'site_name':'site_id',value=document.getElementById('cot-ficha-'+other).value.trim().toLocaleLowerCase();matches=matches.filter(item=>item[other].toLocaleLowerCase()===value||item.site_key.toLocaleLowerCase()===value);}
    if(matches.length!==1)return;
    siteFields.forEach(k=>{document.getElementById('cot-ficha-'+k).value=matches[0][k]||'';});
   }
   field.addEventListener('focus',()=>search(),{signal:events.signal});
   field.addEventListener('input',()=>{clearTimeout(timers[key]);timers[key]=setTimeout(()=>search(true),200);},{signal:events.signal});
   field.addEventListener('change',apply,{signal:events.signal});
  });
  cleanup=()=>{Object.values(timers).forEach(clearTimeout);Object.values(requests).forEach(r=>r.abort());clearTimeout(timer);request?.abort();events.abort();moves.reverse().forEach(restore=>restore());form.remove();modal.classList.remove('cot-sustento-amplio');cleanup=()=>{};};
 };
})();
