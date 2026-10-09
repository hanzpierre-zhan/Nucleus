const assert=require('assert');
class Element {constructor(tag){this.tag=tag;this.style={};this.children=[];}appendChild(x){this.children.push(x);}querySelectorAll(selector){let nodes=this.children.flatMap(x=>[x,...(x.querySelectorAll?x.querySelectorAll(selector):[])]);return nodes.filter(x=>x.tag==='input'&&x.type==='checkbox'&&(!selector.includes(':checked')||x.checked));}}
global.document={createElement:t=>new Element(t),createTextNode:t=>({text:t}),body:{click(){}}};
    function customHeaderPopup(e, column) {

        e.stopPropagation();



        var container = document.createElement("div");

        container.style.padding = "15px";

        container.style.background = "var(--ios-card-bg)";

        container.style.color = "var(--ios-label)";

        container.style.border = "1px solid var(--ios-hairline)";

        container.style.boxShadow = "var(--shadow-soft)";

        container.style.width = "280px";
        container.style.maxWidth = "calc(100vw - 32px)";
        container.style.boxSizing = "border-box";

        container.style.maxHeight = "400px";

        container.style.overflowY = "auto";

        container.style.fontSize = "12px";

        container.style.borderRadius = "12px";



        // --- TOP: ACTIONS ---

        var headerActions = document.createElement("div");

        headerActions.style.marginBottom = "15px";

        headerActions.style.display = "flex";

        headerActions.style.gap = "8px";

        headerActions.style.borderBottom = "1px solid var(--excel-border)";

        headerActions.style.paddingBottom = "12px";



        var applyBtn = document.createElement("button");

        applyBtn.innerHTML = "<i class='fa-solid fa-check'></i> Aplicar";

        applyBtn.style.flex = "1";

        applyBtn.style.padding = "10px";

        applyBtn.style.cursor = "pointer";

        applyBtn.style.border = "none";

        applyBtn.style.background = "var(--ios-accent)"; // blue

        applyBtn.style.color = "white";

        applyBtn.style.borderRadius = "4px";

        applyBtn.style.fontWeight = "bold";

        applyBtn.style.fontSize = "12px";

        applyBtn.onclick = function () {

            runApply();

            document.body.click();

        };



        var clearBtn = document.createElement("button");

        clearBtn.innerHTML = "<i class='fa-solid fa-eraser'></i> Limpiar";

        clearBtn.style.flex = "1";

        clearBtn.style.padding = "10px";

        clearBtn.style.cursor = "pointer";

        clearBtn.style.border = "none";

        clearBtn.style.background = "#d13438"; // red

        clearBtn.style.color = "white";

        clearBtn.style.borderRadius = "4px";

        clearBtn.style.fontWeight = "bold";

        clearBtn.style.fontSize = "12px";

        clearBtn.onclick = function (ex) {

            ex.preventDefault();

            const grid = column.getTable();
            grid.getFilters().forEach(f => {
                if (f.field === column.getField() && f.type === 'in') grid.removeFilter(f.field, f.type, f.value);
            });
            grid.setHeaderFilterValue(column.getField(), '');
            document.body.click();

        };



        headerActions.appendChild(applyBtn);

        headerActions.appendChild(clearBtn);

        container.appendChild(headerActions);



        // --- DATA PREP ---

        var rowData = column.getTable().getData();

        var vals = [];

        rowData.forEach(r => {

            let v = r[column.getField()];

            if (v !== undefined && v !== null && v !== "") vals.push(v);

        });

        var unique = [...new Set(vals)];
        var originalValues = new Map(unique.map(value => [String(value), value]));

        unique.sort();



        var filters = column.getTable().getFilters();

        var myFilter = filters.find(f => f.field === column.getField() && f.type === "in");

        var activeVals = myFilter ? myFilter.value.map(v => String(v)) : [];



        function runApply() {

            var allChecked = listContainer ? Array.from(listContainer.querySelectorAll("input[type='checkbox']:checked")).map(i => originalValues.get(i.value)) : [];

            var totalCheckboxes = listContainer ? listContainer.querySelectorAll("input[type='checkbox']").length : 0;



            var currentFilters = column.getTable().getFilters();

            currentFilters.forEach(f => {

                if (f.field === column.getField() && f.type === "in") {

                    column.getTable().removeFilter(f.field, f.type, f.value);

                }

            });



            if (totalCheckboxes > 0 && allChecked.length < totalCheckboxes) {

                column.getTable().addFilter(column.getField(), "in", allChecked);

            }

        }



        if (unique.length === 0) {

            var empty = document.createElement("div");

            empty.style.color = "#999";

            empty.style.textAlign = "center";

            empty.style.padding = "20px 0";

            empty.textContent = "(Sin valores)";

            container.appendChild(empty);

            return container;

        }



        // --- MIDDLE: CHECKBOX LIST ---

        var listContainer = document.createElement("div");

        listContainer.style.marginBottom = "15px";

        unique.forEach(val => {

            var rowDiv = document.createElement("div");

            rowDiv.style.marginBottom = "8px";

            rowDiv.style.display = "flex";

            rowDiv.style.alignItems = "center";

            rowDiv.style.gap = "10px";



            var chk = document.createElement("input");

            chk.type = "checkbox";

            chk.value = String(val);

            chk.style.cursor = "pointer";

            chk.checked = activeVals.length === 0 || activeVals.includes(String(val));



            var lbl = document.createElement("label");

            lbl.style.cursor = "pointer";

            lbl.style.flex = "1";

            lbl.style.whiteSpace = "normal";
            lbl.style.overflowWrap = "anywhere";
            lbl.style.minWidth = "0";

            lbl.appendChild(document.createTextNode(val));

            lbl.onclick = (ex) => { ex.preventDefault(); chk.checked = !chk.checked; };



            rowDiv.appendChild(chk);

            rowDiv.appendChild(lbl);

            listContainer.appendChild(rowDiv);

        });

        container.appendChild(listContainer);



        return container;

    }




let filters=[], added;
const grid={getData:()=>[{g:15},{g:20},{g:'Una descripción larga'}],getFilters:()=>filters,addFilter:(field,type,value)=>{added=value;filters.push({field,type,value})},removeFilter:()=>{filters=[]},setHeaderFilterValue:()=>{}};
const popup=customHeaderPopup({stopPropagation(){}},{getTable:()=>grid,getField:()=>'g'});
assert.equal(popup.style.width,'280px');const checks=popup.querySelectorAll("input[type='checkbox']");checks.forEach(c=>c.checked=c.value==='15');popup.children[0].children[0].onclick();assert.deepEqual(added,[15]);popup.children[0].children[1].onclick({preventDefault(){}});assert.deepEqual(filters,[]);checks.forEach(c=>c.checked=false);popup.children[0].children[0].onclick();assert.deepEqual(added,[]);console.log('Filtro: ancho limitado, números, limpiar y selección vacía correctos');
