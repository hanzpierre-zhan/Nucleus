/* Evidencia por ítem de la cotización: una imagen inicial y ampliación libre. */
(function(){
 const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
 window.cotLeerDatosItems=()=>Object.fromEntries([...document.querySelectorAll('#cot-sustento-items .cot-item-card')].map(card=>[card.dataset.itemKey,Object.fromEntries([...card.querySelectorAll('[data-item-field]')].map(input=>[input.dataset.itemField,input.value]))]));
 window.cotMontarFotosItems=function(parent,ctx,entry,editable){
  const root=el('section','cot-items-evidence');root.id='cot-sustento-items';
  root.append(el('h3',null,'Evidencia de los ítems de la cotización'));
  if(!ctx.items?.length){root.append(el('p','cot-ficha-status','Esta cotización todavía no tiene ítems registrados. Agrégalos en el editor de cotización.'));parent.append(root);return;}
  const photos=entry.wo_data._SUSTENTO_MANUAL?.item_photos||{};
  for(const item of ctx.items){
   const card=el('details','cot-item-card');card.dataset.itemKey=item.key;
   const head=el('summary','cot-item-heading');head.append(el('span','cot-item-number','Ítem '+item.numero),el('h4',null,item.texto));card.append(head);
   const manual=entry.wo_data._SUSTENTO_MANUAL?.item_details?.[item.key]||{};
   const fields=el('div','cot-item-fields');
   const selectedCode=manual.unique_code||item.unique_code||'8828126757',catalogue=ctx.lpu||[],selected=catalogue.find(row=>row.code===selectedCode);
   const defaults={remarks:manual.remarks===item.texto?'':(manual.remarks||''),unique_code:selectedCode,unit:selected?.unit??item.und??'',description_es:selected?.description_es??item.texto??'',description_en:selected?.description_en??'',activity:selected?.activity||selected?.description_es||''};
   for(const [key,title,long] of [['unique_code','Código único',false],['unit','Unidad',false],['remarks','Descripción de la actividad | Description of the activity',false],['description_es','Descripción de la partida (Esp)',true],['description_en','LPU description (Eng)',true],['activity','Descripción de la actividad | Description of the activity',true]]){
    const label=el('label','cot-item-field'+(long?' cot-item-field-long':'')),input=el(key==='unique_code'?'select':long?'textarea':'input');input.dataset.itemField=key;label.classList.add('cot-item-field-'+key);
    if(key==='unique_code'){catalogue.forEach(row=>{const option=el('option',null,row.code);option.value=row.code;input.append(option);});if(!catalogue.some(row=>row.code===selectedCode)){const option=el('option',null,selectedCode);option.value=selectedCode;input.append(option);}}
    input.value=key==='remarks'?defaults.remarks:key==='unique_code'?selectedCode:(manual.unique_code?manual[key]:undefined)??defaults[key];input.disabled=!editable;
    input.maxLength=(key==='activity'||key==='remarks')?10000:long?5000:key==='unique_code'?300:100;
    if(long){input.rows=2;}else if(key!=='unique_code'){input.type='text';}
    label.append(el('span',null,title),input);fields.append(label);
   }
   card.append(fields);
   fields.querySelector('[data-item-field=unique_code]').addEventListener('change',event=>{const row=catalogue.find(v=>v.code===event.target.value);if(!row)return;for(const key of ['unit','description_es','description_en','activity'])fields.querySelector('[data-item-field='+key+']').value=row[key]||((key==='activity')?row.description_es:'');});
   const grid=el('div','cot-item-phases'),status=el('p','cot-ficha-status');status.setAttribute('role','status');card.append(grid,status);root.append(card);
   async function upload(files,phase,index){
    if(!editable||!files.length)return;
    if(ctx.uploads){status.textContent='Espera a que termine la carga actual.';return;}
    ctx.uploads++;card.setAttribute('aria-busy','true');status.textContent='Guardando fotos…';render();
    try{
     for(const file of files){
      if(file.size>20*1024*1024)throw Error('La imagen '+file.name+' supera los 20 MB.');
      const body=new FormData();body.append('key',ctx.key);body.append('wo',entry.wo);body.append('item_key',item.key);body.append('phase',phase);body.append('foto',file);if(index!==undefined)body.append('photo_index',String(index));
      const response=await fetch('/api/cotizacion/sustento/item-foto',{method:'POST',body});const result=await nucleusLeerRespuestaJSON(response);
      if(!response.ok||!result.success)throw Error(result.error||'No se pudo guardar la foto.');
      photos[item.key]=result.photos;entry.wo_data._SUSTENTO_MANUAL={...(entry.wo_data._SUSTENTO_MANUAL||{}),item_photos:photos};
     }
     status.textContent='Fotos guardadas.';
    }catch(error){status.textContent=error.message;}
    finally{ctx.uploads--;card.removeAttribute('aria-busy');render();}
   }
   function picker(text,phase,index,multiple=false){const label=el('label','cot-item-upload',text),input=el('input');input.type='file';input.accept='image/jpeg,image/png,image/webp,image/heic,image/heif';input.multiple=multiple;input.hidden=true;input.disabled=!editable||ctx.uploads>0;input.setAttribute('aria-label',text+' · '+phase+' · ítem '+item.numero);label.tabIndex=input.disabled?-1:0;label.setAttribute('role','button');label.addEventListener('keydown',event=>{if(!input.disabled&&(event.key==='Enter'||event.key===' ')){event.preventDefault();input.click();}});input.addEventListener('change',()=>upload([...input.files],phase,index));label.append(input);if(input.disabled)label.classList.add('is-disabled');return label;}
   function render(){
    grid.replaceChildren();const images=photos[item.key]||[];
    for(const [phase,title] of [['before','Antes | Before'],['during','Durante | During'],['after','Después | After']]){
     const section=el('section','cot-item-phase');section.dataset.phase=phase;section.append(el('h5',null,title));
     const list=el('div','cot-item-photos');section.append(list);grid.append(section);
     const selected=images.map((photo,i)=>({photo,i})).filter(({photo})=>(photo.phase||'before')===phase);
     selected.forEach(({photo,i})=>{const figure=el('figure','cot-item-photo'),link=el('a'),img=el('img');link.href=photo.url;link.target='_blank';link.rel='noopener';img.src=photo.url;img.alt=title+' · foto '+(i+1)+' del ítem '+item.numero;img.loading='lazy';link.append(img);figure.append(link);if(editable)figure.append(picker('Reemplazar foto',phase,i));list.append(figure);});
     if(editable)list.append(picker(selected.length?'+ Agregar foto':'+ Subir foto',phase,undefined,true));
     else if(!selected.length)list.append(el('p','cot-ficha-status','Sin fotos registradas.'));
    }
   }
   render();
  }
  parent.append(root);
 };
})();
