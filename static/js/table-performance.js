/* Una sola actualización visual por operación compuesta, incluso si se anida. */
(function(root){
    const depths=new WeakMap();
    function batch(table,operation){
        if(!table || typeof table.blockRedraw!=='function')return operation();
        const depth=depths.get(table)||0;
        if(!depth)table.blockRedraw();
        depths.set(table,depth+1);
        try{return operation();}
        finally{if(depth)depths.set(table,depth);else{depths.delete(table);table.restoreRedraw();}}
    }
    root.nucleusBatchTable=batch;
    function reorder(table,order){
        const current=table.getColumns().map(c=>c.getField());
        const existing=new Set(current);const desired=Array.from(new Set(order||[])).filter(f=>existing.has(f));
        const included=new Set(desired);const actual=current.filter(f=>included.has(f));
        desired.forEach((field,index)=>{
            if(actual[index]===field)return;
            const from=actual.indexOf(field);const before=actual[index];
            const column=table.getColumn(field);
            if(column&&before&&typeof column.move==='function'){
                column.move(before,false);actual.splice(from,1);actual.splice(index,0,field);
            }
        });
    }
    root.nucleusReorderColumns=reorder;
    batch.reorder=reorder;
    if(typeof module==='object'&&module.exports)module.exports=batch;
})(typeof window!=='undefined'?window:globalThis);
