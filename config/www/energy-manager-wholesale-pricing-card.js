/** Energy Manager Wholesale Pricing Strategy: native Home Assistant Lovelace custom card (v5). */
class EnergyManagerWholesalePricingCard extends HTMLElement {
 constructor(){super();this.attachShadow({mode:'open'});this._values={};this._pending=new Map();this._initialized=false;this._hass=null;this._config={};this._isDragging=false;}
 setConfig(config){this._config=config||{};this._ensureUI();}
 set hass(hass){
  this._hass=hass;
  this._ensureUI();
  if(!this._initialized)return;
  const active=this.shadowRoot.activeElement;
  const inModal=this.shadowRoot.getElementById('overlay')?.classList.contains('show');
  const dragging=!!this.shadowRoot.querySelector('.dragging');
  if(!dragging && !inModal){
   for(const [key,entity] of Object.entries(ENTITY_MAP)){
    const raw=hass.states?.[entity]?.state;
    if(raw!==undefined&&raw!=='unknown'&&raw!=='unavailable'){
     const n=Number(raw);if(Number.isFinite(n) && !this._pending.has(key))this._values[key]=n;
    }
   }
   this._redraw?.();
  }
  this._updateProfile();
  const light=!hass.themes?.darkMode;
  this.classList.toggle('light',light);
 }
 _ensureUI(){if(this._initialized)return;this._initialized=true;
  this.shadowRoot.innerHTML='<style>'+STYLES+'</style>'+MARKUP;
  this._values={...DEFAULTS};
  this._setup();
 }
 _range(key,pct,tier,money){const e=ENTITY_MAP[key],attrs=this._hass?.states?.[e]?.attributes||{};
  const fallback={min:pct.includes(key)||tier.includes(key)?0:key==='capacity'?1:0,max:pct.includes(key)||tier.includes(key)?100:key==='capacity'?100:key==='export'?50:money.includes(key)?10:key==='morningSpike'||key==='eveningSpike'?2500:key.startsWith('rain')?150:500,step:key==='capacity'||key==='export'?0.1:money.includes(key)?0.05:1};
  for(const name of ['min','max','step']){const n=Number(attrs[name]);if(attrs[name]!=null&&Number.isFinite(n))fallback[name]=n;}
  if(!fallback.step||fallback.step<=0)fallback.step=1;
  return fallback;
 }
 _tooltip(k){return TOOLTIPS[ENTITY_MAP[k]]||'Home Assistant entity: '+(ENTITY_MAP[k]||k);}
 async _commit(key){if(key==='capacity'||key==='export')return;const e=ENTITY_MAP[key];if(!e||!this._hass)return;
  const n=this._values[key];if(!Number.isFinite(n))return;
  const {min,max,step}=this._range(key,[],[],[]);
  const val=Math.max(min,Math.min(max,Math.round(n/step)*step));
  this._pending.set(key,val);
  try{await this._hass.callService('input_number','set_value',{entity_id:e,value:val});}
  catch(err){this._showToast?.('Update failed: '+(err?.message||err));}
  finally{this._pending.delete(key);}
 }
 async _selectProfile(value){if(!this._hass)return;
  try{await this._hass.callService('input_select','select_option',{entity_id:'input_select.energy_profile_slot',option:value});}
  catch(err){this._showToast?.('Profile selection failed: '+(err?.message||err));}
 }
 async _press(entity){if(!this._hass)return;
  try{await this._hass.callService('input_button','press',{entity_id:entity});}
  catch(err){this._showToast?.('Profile action failed: '+(err?.message||err));}
 }
 _updateProfile(){const select=this.shadowRoot.getElementById('profile');if(!select||!this._hass)return;
  const entity=this._hass.states?.['input_select.energy_profile_slot'];
  if(!entity)return;
  const opts=entity.attributes?.options||[];
  if(JSON.stringify(Array.from(select.options).map(o=>o.value))!==JSON.stringify(opts)){
   select.replaceChildren(...opts.map(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;return o}));
  }
  if(select!==this.shadowRoot.activeElement)select.value=entity.state;
 }
 _setup(){
const card=this;const root=this.shadowRoot;

'use strict';
const base={capacity:19.2,export:5,morningSpike:100,eveningSpike:200,morningBuy:15,eveningBuy:40,dayBuy:10,batteryUseCost:10,curtail:0,morningPrep:40,morningReserve:20,eveningPrep:100,highSell:50,highReserve:50,sellDiff:10,sellReserve:50,rainToday:12,rainTomorrow:20,battery_1:80,battery_2:65,battery_3:50,battery_4:40,battery_5:30,battery_6:10,price_1:.25,price_2:.35,price_3:.5,price_4:1,price_5:1.5,price_6:3};
const labels={capacity:'Total battery capacity',export:'Maximum export',morningSpike:'Morning spike definition',eveningSpike:'Evening spike definition',morningBuy:'Morning spike preparation: max buy price',eveningBuy:'Evening spike preparation: max buy price',dayBuy:'Normal daytime maximum charging price',batteryUseCost:'Import from grid when below',curtail:'Curtail when sell price is below',morningPrep:'Morning battery charge target',morningReserve:'Morning battery reserve',eveningPrep:'Evening battery charge target',highSell:'High Sell Mode minimum sell price',highReserve:'High Sell Mode reserve',sellDiff:'Sell-Buy Mode price difference',sellReserve:'Sell-Buy Mode reserve',rainToday:'Rain threshold for bad weather today',rainTomorrow:'Rain threshold for bad weather tomorrow'};
const state=this._values;const $=id=>root.getElementById(id);const fields=root.querySelectorAll('[data-key]');let active=null;let toastTimer;
const pctKeys=['morningPrep','morningReserve','eveningPrep','highReserve','sellReserve'];const moneyKeys=Array.from({length:6},(_,i)=>'price_'+(i+1));const tierKeys=Array.from({length:6},(_,i)=>'battery_'+(i+1));
const centsKeys=new Set(['morningSpike','eveningSpike','morningBuy','eveningBuy','dayBuy','batteryUseCost','curtail','highSell','sellDiff']);
const toDisplay=(k,v)=>centsKeys.has(k)?Number(v)/100:Number(v);
const toStored=(k,v)=>centsKeys.has(k)?Number(v)*100:Number(v);
const meta=k=>card._range(k, pctKeys, tierKeys, moneyKeys);
function format(k,v){if(pctKeys.includes(k)||tierKeys.includes(k))return Math.round(v)+'%';if(k==='capacity')return Number(v).toFixed(1);if(k==='export')return Number(v).toFixed(1);if(k.startsWith('rain'))return Number(v)+' mm';if(moneyKeys.includes(k))return '$'+Number(v).toFixed(2);return centsKeys.has(k)?'$'+(Number(v)/100).toFixed(2):Number(v)+' c'}
function batteryKwh(pct){const cap=Number(state.capacity)||0;return (cap*Math.max(0,pct)/100).toFixed(1)+' kWh'}
function setBattery(id,usable,reserve,usableLabel,reserveLabel){
 const b=$(id),u=b.querySelector('.usable'),r=b.querySelector('.reserve');
 b.style.setProperty('--reserve',reserve);b.style.setProperty('--charge',id==='morning-battery'?state.morningPrep:id==='evening-battery'?state.eveningPrep:100);
 u.style.height=usable+'%';r.style.height=reserve+'%';
 if(usableLabel){
  const node=$(usableLabel);
  const pct=id==='morning-battery'?state.morningPrep:usable;
  // Evening/morning charge percentage describes the total target SOC, not just the green band.
  const kwhPct=id==='morning-battery'?state.morningPrep:usable;
  node.innerHTML=usable<12?'':`<b>${Math.round(pct)}%</b><small>${batteryKwh(kwhPct)}</small>${node.classList.contains('usable-stack')?'<small>Usable</small>':''}`;
 }
 if(reserveLabel){const node=$(reserveLabel);node.innerHTML=reserve<12?'':`<b>${Math.round(reserve)}%</b><small>${batteryKwh(reserve)}</small>`}
}
function render(){fields.forEach(el=>{const k=el.dataset.key;if(!k)return;const child=el.querySelector('.value');(child||el).textContent=format(k,state[k]);});setBattery('highBattery',100-state.highReserve,state.highReserve,'highUsable','highReserve');setBattery('sellBattery',100-state.sellReserve,state.sellReserve,'sellUsable','sellReserve');setBattery('morning-battery',state.morningPrep-state.morningReserve,state.morningReserve,'morningusable','morningreserve');setBattery('evening-battery',state.eveningPrep,0,'eveningusable',null);for(const key of ['morningPrep','morningReserve','eveningPrep']){const el=root.querySelector('.preplabel [data-key="'+key+'"]');if(el)el.textContent=Math.round(state[key])+'% ('+batteryKwh(state[key])+')'}drawChart();drawTiers();attachBatteryHandles()}
// Separate visual axes: morning is deliberately shorter than evening.
// Evening uses a three-band, piecewise scale rather than a logarithmic axis.
// Graph position is independent of actual prices; the two spikes are not comparable.
function spikeMax(key){return Math.max(1,meta(key).max)}
const SPIKE_BOTTOM=247;
function evePriceToY(v){
 const x=Math.max(0,Math.min(2500,v));
 if(x<=300)return 247-(x/300)*122;
 if(x<=500)return 125-((x-300)/200)*35;
 return 90-((x-500)/2000)*66;
}
function eveYToPrice(y){
 const yy=Math.max(24,Math.min(247,y));
 if(yy>=125)return (247-yy)/122*300;
 if(yy>=90)return 300+(125-yy)/35*200;
 return 500+(90-yy)/66*2000;
}
function priceToY(price,key){
 if(key==='eveningSpike')return evePriceToY(price);
 const top=135,bottom=SPIKE_BOTTOM,max=spikeMax(key);
 return bottom-(bottom-top)*Math.log1p(Math.max(0,Math.min(max,price))/25)/Math.log1p(max/25);
}
function yToPrice(y,key){
 if(key==='eveningSpike')return eveYToPrice(y);
 const top=135,bottom=SPIKE_BOTTOM,max=spikeMax(key);
 const ratio=Math.max(0,Math.min(1,(bottom-y)/(bottom-top)));
 return 25*Math.expm1(ratio*Math.log1p(max/25));
}
function spikeDragStep(key,price){
 if(key==='eveningSpike')return price<300?Math.max(1,meta(key).step):price<500?50:100;
 return Math.max(1,meta(key).step);
}
function quantizeSpike(key,price){
 const info=meta(key),p=Math.max(info.min,Math.min(info.max,price));
 if(key==='eveningSpike'){
  if(p<=300)return Math.max(info.min,Math.min(300,Math.round(p/Math.max(1,info.step))*Math.max(1,info.step)));
  if(p<=500)return Math.max(300,Math.min(500,300+Math.round((p-300)/50)*50));
  return Math.max(500,Math.min(info.max,500+Math.round((p-500)/100)*100));
 }
 return Math.max(info.min,Math.min(info.max,Math.round(p/info.step)*info.step));
}
function chartShapes(){const a=priceToY(state.morningSpike,'morningSpike'),b=priceToY(state.eveningSpike,'eveningSpike');const y=247;const path=`M55 ${y} C120 ${y} 160 ${y} 225 ${y} C267 ${y} 281 ${a} 320 ${a} C357 ${a} 370 ${y} 422 ${y} C500 ${y} 617 ${y} 662 ${y} C720 ${y} 764 ${b} 820 ${b} C872 ${b} 905 ${y} 953 ${y} L1070 ${y}`;return {a,b,path}}
function drawChart(){const {a,b,path}=chartShapes();$('curve').setAttribute('d',path);$('area').setAttribute('d',path+' L1070 278 L55 278 Z');$('mpoint').setAttribute('cy',a);$('epoint').setAttribute('cy',b);$('morningChartValue').textContent=format('morningSpike',state.morningSpike);$('eveningChartValue').textContent=format('eveningSpike',state.eveningSpike);$('morningChartValue').setAttribute('y',Math.max(18,a-19));$('eveningChartValue').setAttribute('y',Math.max(18,b-19));$('morningTitle').classList.toggle('obscured',a<92);$('eveningTitle').classList.toggle('obscured',b<92)}
function drawTiers(){const t=$('tiers'),price=$('tierPrices');if(root.querySelector('.normal-battery.dragging'))return;t.innerHTML='';price.innerHTML='';for(let i=1;i<=6;i++){const upper=i===1?100:state['battery_'+(i-1)];const lower=state['battery_'+i];const next=i===6?0:state['battery_'+(i+1)];const span=Math.max(1,upper-lower);const el=document.createElement('div');el.className='normal-tier';el.style.flex=String(Math.max(1,span));const btn=document.createElement('button');btn.textContent=`${lower}% – ${i===1?'100':upper-1}%`;btn.title=card._tooltip('battery_'+i);btn.onclick=()=>edit('battery_'+i);el.appendChild(btn);if(i<6){const h=document.createElement('div');h.className='tier-handle';h.title=`Drag boundary of tier ${i} vertically`;h.dataset.boundary=i;el.appendChild(h)}t.appendChild(el);const p=document.createElement('button');p.className='normal-price';p.textContent=format('price_'+i,state['price_'+i]);p.title=card._tooltip('price_'+i);p.onclick=()=>edit('price_'+i);p.style.flex=String(span);price.appendChild(p)}updateBadWeather()}
function updateBadWeather(){const rows=$('tiers').querySelectorAll('.normal-tier');if(rows.length!==6)return;const top=rows[0].getBoundingClientRect().height+rows[1].getBoundingClientRect().height;const full=$('tiers').getBoundingClientRect().height;const bad=root.querySelector('.badweather');bad.style.marginTop=Math.round(top)+'px';bad.style.height=Math.max(0,Math.round(full-top))+'px'}
function attachBatteryHandles(){
 const configs=[['highBattery','highReserve','reserve'],['sellBattery','sellReserve','reserve'],['morning-battery','morningReserve','reserve'],['morning-battery','morningPrep','charge'],['evening-battery','eveningPrep','charge']];
 for(const [id,key,kind] of configs){const inner=$(id).querySelector('.inner');if(inner.querySelector(`[data-drag="${key}"]`))continue;
 const h=document.createElement('div');h.className='drag-divider'+(kind==='charge'?' drag-top':'');h.dataset.drag=key;h.title=card._tooltip(key);inner.appendChild(h);
 h.addEventListener('pointerdown',e=>{e.preventDefault();e.stopPropagation();h.setPointerCapture(e.pointerId);$(id).classList.add('dragging');const move=ev=>{const rect=inner.getBoundingClientRect();const v=Math.round((rect.bottom-ev.clientY)/rect.height*100);const low=key==='morningPrep'?state.morningReserve:0;const high=key==='morningReserve'?state.morningPrep:100;state[key]=Math.max(low,Math.min(high,v));render()};move(e);
 const stop=()=>{$(id).classList.remove('dragging');h.removeEventListener('pointermove',move);card._commit(key)};h.addEventListener('pointermove',move);h.addEventListener('pointerup',stop,{once:true});h.addEventListener('pointercancel',stop,{once:true})})
 }
}
function bindDirectDragging(){
 const chart=$('chart');
 // Last SVG children are transparent hit targets above labels and curve.
 for(const [pointId,key] of [['mpoint','morningSpike'],['epoint','eveningSpike']]){
  const point=$(pointId);
  const target=document.createElementNS('http://www.w3.org/2000/svg','circle');
  target.setAttribute('r','27');target.setAttribute('fill','transparent');
  target.setAttribute('stroke','transparent');target.style.cursor='ns-resize';
  target.style.touchAction='none';target.setAttribute('aria-label',card._tooltip(key));
  chart.appendChild(target);
  const sync=()=>{target.setAttribute('cx',point.getAttribute('cx'));target.setAttribute('cy',point.getAttribute('cy'))};
  sync();
  const observer=new MutationObserver(sync);
  observer.observe(point,{attributes:true,attributeFilter:['cy','cx']});
  target.addEventListener('pointerdown',e=>{
   if(e.button!==0)return;
   e.preventDefault();e.stopPropagation();
   const pointerId=e.pointerId,startX=e.clientX,startY=e.clientY;
   let moved=false;
   chart.classList.add('dragging');
   // Capture on the stable svg, not the moving point or text.
   chart.setPointerCapture(pointerId);
   const move=ev=>{
    if(ev.pointerId!==pointerId)return;
    if(Math.hypot(ev.clientX-startX,ev.clientY-startY)<3&&!moved)return;
    moved=true;
    const rect=chart.getBoundingClientRect();
    const y=(ev.clientY-rect.top)/rect.height*320;
    state[key]=quantizeSpike(key,yToPrice(y,key));render();
   };
   const finish=ev=>{
    if(ev.pointerId!==pointerId)return;
    chart.removeEventListener('pointermove',move);
    chart.removeEventListener('pointerup',finish);
    chart.removeEventListener('pointercancel',finish);
    chart.classList.remove('dragging');
    if(chart.hasPointerCapture(pointerId))chart.releasePointerCapture(pointerId);
    if(ev.type==='pointerup'){
     if(moved)card._commit(key);
     else edit(key);
    }
   };
   chart.addEventListener('pointermove',move);
   chart.addEventListener('pointerup',finish);
   chart.addEventListener('pointercancel',finish);
  });
 }
$('tiers').addEventListener('pointerdown',e=>{const h=e.target.closest('.tier-handle');if(!h)return;e.preventDefault();e.stopPropagation();const i=+h.dataset.boundary,key='battery_'+i,normal=$('normalBattery'),inner=$('tiers');h.setPointerCapture(e.pointerId);normal.classList.add('dragging');const move=ev=>{const r=inner.getBoundingClientRect();let v=Math.round((r.bottom-ev.clientY)/r.height*100);const upper=i===1?100:state['battery_'+(i-1)]-1;const lower=state['battery_'+(i+1)]+1;state[key]=Math.min(upper,Math.max(lower,v));render();const sections=inner.querySelectorAll('.normal-tier');sections.forEach((section,j)=>{const up=j===0?100:state['battery_'+j],lo=state['battery_'+(j+1)];section.style.flex=String(Math.max(1,up-lo));$('tierPrices').children[j].style.flex=String(Math.max(1,up-lo));section.querySelector('button').textContent=`${lo}% – ${j===0?100:up-1}%`});updateBadWeather()};move(e);h.addEventListener('pointermove',move);h.addEventListener('pointerup',()=>{normal.classList.remove('dragging');h.removeEventListener('pointermove',move);drawTiers();card._commit(key)},{once:true})});
}
function showToast(str){$('toast').textContent=str;$('toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('show'),2400)}
function edit(k){active=k;const {min,max,step}=meta(k);$('editTitle').textContent=labels[k]||'Normal Mode tier setting';$('editDesc').textContent=card._tooltip(k)||'Edit the Home Assistant setting and apply the change.';$('range').min=min;$('range').max=max;$('range').step=step;$('range').value=state[k];$('numedit').min=toDisplay(k,min);$('numedit').max=toDisplay(k,max);$('numedit').step=toDisplay(k,step);$('numedit').value=toDisplay(k,state[k]);$('preview').textContent=format(k,state[k]);$('minlabel').textContent=format(k,min);$('maxlabel').textContent=format(k,max);$('overlay').classList.add('show');$('range').focus();preview.original=state[k]}
function preview(v,{preserveTyped=false}={}){
 if(!active||v===''||v==='-'||v==='.'||v==='-.')return;
 const k=active;const {min,max}=meta(k);const parsed=toStored(k,v);if(!Number.isFinite(parsed))return;
 if(preserveTyped&&(parsed<min||parsed>max))return;const n=Math.min(max,Math.max(min,parsed));state[k]=n;$('range').value=n;
 // Never replace the input while the user is typing: 0.7 must not become 25 or 0 mid-entry.
 if(!preserveTyped)$('numedit').value=toDisplay(k,n);
 $('preview').textContent=format(k,n);render();
}
function close(apply){
 if(apply&&active){const raw=$('numedit').value;const {min,max}=meta(active);const n=toStored(active,raw);if(raw.trim()===''||!Number.isFinite(n)||n<min||n>max){$('numedit').focus();$('numedit').setCustomValidity(`Enter a value between ${toDisplay(active,min)} and ${toDisplay(active,max)}`);$('numedit').reportValidity();return} $('numedit').setCustomValidity('');state[active]=n;}
 else if(active)state[active]=preview.original;
 render();$('overlay').classList.remove('show');if(apply&&active)card._commit(active);active=null;
}
fields.forEach(el=>{const k=el.dataset.key;el.title=card._tooltip(k);if(k==='capacity'||k==='export'){el.disabled=true;return}el.addEventListener('click',()=>edit(k))});
$('range').addEventListener('input',e=>{const k=active;if(!k)return;const {min,max}=meta(k);const n=Math.max(min,Math.min(max,Number(e.target.value)));state[k]=n;$('numedit').value=toDisplay(k,n);$('preview').textContent=format(k,n);render()});
$('numedit').addEventListener('input',e=>{$('numedit').setCustomValidity('');preview(e.target.value,{preserveTyped:true})});
$('cancel').onclick=()=>close(false);$('apply').onclick=()=>close(true);
$('overlay').addEventListener('click',e=>{if(e.target===$('overlay'))close(false)});
$('overlay').addEventListener('keydown',e=>{if(e.key==='Escape'&&active)close(false);if(e.key==='Enter'&&e.target===$('numedit'))close(true)});
$('morningChartValue').addEventListener('click',()=>edit('morningSpike'));$('eveningChartValue').addEventListener('click',()=>edit('eveningSpike'));
$('mpoint').style.cursor='pointer';$('epoint').style.cursor='pointer';
for(const [id,key] of [['mpoint','morningSpike'],['epoint','eveningSpike'],['morningChartValue','morningSpike'],['eveningChartValue','eveningSpike']]) $(id).setAttribute('aria-label',card._tooltip(key));bindDirectDragging();
$('profile').addEventListener('change',async e=>{await this._selectProfile(e.target.value)});
$('save').onclick=()=>this._press('input_button.energy_profile_save');
$('load').onclick=()=>this._press('input_button.energy_profile_load');
render();
this._redraw=render;
this._hydrate=()=>{ for(const [k,v] of Object.entries(this._values)) state[k]=v; render(); };
this._showToast=showToast;

 }
 getCardSize(){return 16;}
 static getStubConfig(){return {type:'custom:energy-manager-wholesale-pricing-card'};}
}

const ENTITY_MAP={
  "capacity": "input_number.battery_capacity",
  "export": "input_number.inverter_export_limit",
  "morningSpike": "input_number.grid_sell_price_night",
  "eveningSpike": "input_number.grid_sell_price_day",
  "morningBuy": "input_number.grid_buy_price_night_spike_prep",
  "eveningBuy": "input_number.grid_buy_price_day_spike_prep",
  "dayBuy": "input_number.grid_buy_price_day",
  "batteryUseCost": "input_number.battery_use_cost",
  "curtail": "input_number.curtail_cents",
  "morningPrep": "input_number.battery_morning_prep",
  "morningReserve": "input_number.battery_morning_limit",
  "eveningPrep": "input_number.battery_evening_prep",
  "highSell": "input_number.high_sell_price",
  "highReserve": "input_number.high_sell_battery_reserve",
  "sellDiff": "input_number.sellbuy_mode_diff",
  "sellReserve": "input_number.sellbuy_mode_battery_reserve",
  "rainToday": "input_number.bad_weather_rain_today",
  "rainTomorrow": "input_number.bad_weather_rain_tomorrow",
  "battery_1": "input_number.battery_1",
  "battery_2": "input_number.battery_2",
  "battery_3": "input_number.battery_3",
  "battery_4": "input_number.battery_4",
  "battery_5": "input_number.battery_5",
  "battery_6": "input_number.battery_6",
  "price_1": "input_number.price_1_normal_mode",
  "price_2": "input_number.price_2_normal_mode",
  "price_3": "input_number.price_3_normal_mode",
  "price_4": "input_number.price_4_normal_mode",
  "price_5": "input_number.price_5_normal_mode",
  "price_6": "input_number.price_6_normal_mode"
};
const TOOLTIPS={
  "input_select.energy_profile_slot": "Energy profile slot.",
  "input_number.grid_sell_price_night": "Enter the definition of a price spike for the morning shoulder period. If the sell price exceeds this figure between the hours of 6-8am, export may occur.",
  "input_number.grid_sell_price_day": "Enter the definition of a day/evening price spike. If the sell price exceeds this figure (all hours outside of 6-8am), export may occur.",
  "input_number.grid_buy_price_night_spike_prep": "This is the price that you are willing to pay to charge your battery up if a morning shoulder price spike is detected (as defined).",
  "input_number.grid_buy_price_day_spike_prep": "This is the price that you are willing to pay to charge your battery up if a day/evening price spike is detected (as defined).",
  "input_number.grid_buy_price_day": "This is the price that you are willing to pay to buy electricity if EM has detected that you can't generate enough to charge your battery purely from solar. Note that if you have this set too low, charging may not occur.",
  "input_number.curtail_cents": "Curtailing of excess generation will occur when the sell price is under this amount, if curtailing has been enabled on the PV Settings tab.",
  "input_number.battery_use_cost": "If there is not enough solar generation, import from the grid when the buy price is under this figure. If the buy price is over this figure it will discharge from the battery instead.",
  "input_number.battery_morning_prep": "If an upcoming morning shoulder spike has been detected, and the buy price is under the maximum charging price, charge the battery up to this percentage.",
  "input_number.battery_morning_limit": "If a morning shoulder spike export is in progress, discharge the battery down to this percentage only.",
  "input_number.battery_evening_prep": "This is the maximum percentage that you want the battery to charge to during the day. Note that this is independent of any maximum SoC setting you may have configured and your maximum SoC will override this if set lower.",
  "input_number.battery_capacity": "The total battery capacity in kWh, as defined on the PV Settings tab.",
  "input_number.price_1_normal_mode": "The minimum price to sell at if the tier 1 battery SoC range to the left has been met.",
  "input_number.price_2_normal_mode": "The minimum price to sell at if the tier 2 battery SoC range to the left has been met.",
  "input_number.price_3_normal_mode": "The minimum price to sell at if the tier 3 battery SoC range to the left has been met.",
  "input_number.price_4_normal_mode": "The minimum price to sell at if the tier 4 battery SoC range to the left has been met.",
  "input_number.price_5_normal_mode": "The minimum price to sell at if the tier 5 battery SoC range to the left has been met.",
  "input_number.price_6_normal_mode": "The minimum price to sell at if the tier 6 battery SoC range to the left has been met.",
  "input_number.battery_1": "Tier 1: Battery percentage range that apply to the tier 1 sell pricing on the right.",
  "input_number.battery_2": "Tier 2: Battery percentage range that apply to the tier 2 sell pricing on the right.",
  "input_number.battery_3": "Tier 3: Battery percentage range that apply to the tier 3 sell pricing on the right.",
  "input_number.battery_4": "Tier 4: Battery percentage range that apply to the tier 4 sell pricing on the right.",
  "input_number.battery_5": "Tier 5: Battery percentage range that apply to the tier 5 sell pricing on the right.",
  "input_number.battery_6": "Tier 6: Battery percentage range that apply to the tier 6 sell pricing on the right.",
  "input_number.high_sell_price": "If in High Sell mode, this is the lowest price to sell at.",
  "input_number.high_sell_battery_reserve": "During an export period, only discharge the battery to this SoC percentage.",
  "number.battery_high_sell_mode_usable": "This is the maximum amount of usable battery capacity that can be exported, assuming your battery is at 100% charge.",
  "input_number.sellbuy_mode_battery_reserve": "During an export period, only discharge the battery to this SoC percentage.",
  "sensor.sell_buy_mode_usable": "This is the maximum amount of usable battery capacity that can be exported, assuming your battery is at 100% charge.",
  "input_number.sellbuy_mode_diff": "This is the price difference between selling now and buying later that you are willing to export at. Note that this is based off the forecast as per your energy provider and forecasts can change. Example, assuming this setting is 10c, if the current sell price is 30c and the price to buy later is predicted to be 12c, then the difference is 18c and export will occur as the difference is greater than 10c.",
  "input_number.bad_weather_rain_today": "This is the definition of what bad weather for today is. If today's rain forecast is higher than this, then bad weather mode will be used. This applies to Normal Mode only.",
  "input_number.bad_weather_rain_tomorrow": "This is the definition of what bad weather for tomorrow is. If tomorrow's rain forecast is higher than this, then bad weather mode will be used right now. This applies to Normal Mode only.",
  "input_number.inverter_export_limit": "The inverter export limit, as defined on the PV Settings tab.",
  "input_number.flowpower_peak_battery_reserve": "This is the minimum SOC that you are willing to allow exports to while during the Peak export period. Note that Energy Manager will still be limited by your configured kWh amount. This does not replace your overall minimum SOC set at your inverter.",
  "sensor.flowpower_peak_battery_usable": "This is the maximum amount of usable battery capacity that can be exported, assuming your battery is at 100% charge.",
  "input_select.flow_power_price_signal_charge_limit": "This is the PEA signal that you are willing to purchase electricity UP TO. Energy Manager will not restrict to purchasing AT this price, but will still purchase at the cheapest period UP UNTIL (and including) this price, IF REQUIRED. Note that the PEA here is estimated, it may not reflect exactly what Flow Power define.",
  "input_number.flowpower_max_grid_soc": "This is the maximum SOC that you are willing to charge your battery up to if electricity is required to be purchased from the grid. It will not affect the maximum SOC that natural solar generation will take your battery to. Your inverter-configured maximum SOC will override this if it is set lower than here.",
  "input_number.globird_super_battery_reserve": "This is the minimum SOC that you are willing to allow exports to while during the Super export period. Note that Energy Manager will still be limited by your configured kWh amount. This does not replace your overall minimum SOC set at your inverter.",
  "sensor.globird_super_battery_usable": "This is the maximum amount of usable battery capacity that can be exported during the Super export period, assuming your battery is at 100% charge. Note that this is still limited by your selected kWh export amount, so it will stop at the first met, either your kWh limit or your battery reserve.",
  "input_number.globird_std_battery_reserve": "This is the minimum SOC that you are willing to allow exports to while during the Standard (not Super) export period. Note that Energy Manager will still be limited by your configured kWh amount. This does not replace your overall minimum SOC set at your inverter.",
  "sensor.globird_std_battery_usable": "This is the maximum amount of usable battery capacity that can be exported during the Standard (not Super) export period, assuming your battery is at 100% charge. Note that this is still limited by your selected kWh export amount."
};
const DEFAULTS={"capacity": 0, "export": 0, "morningSpike": 0, "eveningSpike": 0, "morningBuy": 0, "eveningBuy": 0, "dayBuy": 0, "batteryUseCost": 0, "curtail": 0, "morningPrep": 0, "morningReserve": 0, "eveningPrep": 0, "highSell": 0, "highReserve": 0, "sellDiff": 0, "sellReserve": 0, "rainToday": 0, "rainTomorrow": 0, "battery_1": 0, "battery_2": 0, "battery_3": 0, "battery_4": 0, "battery_5": 0, "battery_6": 0, "price_1": 0, "price_2": 0, "price_3": 0, "price_4": 0, "price_5": 0, "price_6": 0};
const STYLES="\n :host{color-scheme:dark;--bg:var(--primary-background-color,#111111);--panel:var(--ha-card-background,var(--card-background-color,#1c1c1c));--edge:var(--divider-color,#434343);--text:var(--primary-text-color,#e1e1e1);--muted:var(--secondary-text-color,#a4a4a4);--accent:var(--info-color,#56b4e7);--green:#3dc18a;--orange:#f08c4d;--shade:#111111;--field:var(--secondary-background-color,#252525);--shadow:#00000040}\n:host(.light){color-scheme:light;--bg:#dce8ec;--panel:#f3f8fa;--edge:#829ba780;--text:#142d3a;--muted:#526a78;--accent:#087fbb;--green:#12a876;--orange:#bd6829;--shade:#b6cad2;--field:#e0edf3;--shadow:#627c8766}\n*{box-sizing:border-box}.app{margin:0;font:15px/1.45 Inter,'Segoe UI',system-ui,sans-serif;color:var(--text);background:var(--bg);transition:background .35s,color .35s}.shell{max-width:1420px;margin:auto;padding:24px 22px 60px}.topline{display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:18px}.branding{display:flex;align-items:center;gap:13px}.brandmark{width:48px;height:48px;border-radius:14px;background:linear-gradient(130deg,#23e8ae,#0b778e 70%,#104258);display:grid;place-items:center;box-shadow:inset 0 2px 4px #dffffe80,0 9px 20px #0005;color:white;font-size:27px;font-weight:900}.branding h1{font-size:24px;margin:0;line-height:1.12;letter-spacing:-.6px}.branding small{color:var(--muted)}button,input,select{font:inherit}button{cursor:pointer;color:inherit}.toolbar{display:flex;gap:9px;flex-wrap:wrap}.btn{padding:9px 14px;border:1px solid var(--edge);border-radius:11px;background:linear-gradient(160deg,#ffffff14,#00000010),var(--panel);box-shadow:inset 0 1px 0 #ffffff2c,0 5px 12px #0002}.btn:hover,.field:hover{border-color:var(--accent)}.btn.primary{background:var(--primary-color,#247ba5);color:white;border-color:#6ddaf87c}.card{position:relative;border:1px solid var(--edge);border-radius:20px;background:var(--panel);box-shadow:inset 0 1px 0 #ffffff2a,0 18px 36px var(--shadow);overflow:hidden}.card:before{content:\"\";position:absolute;inset:0;pointer-events:none;background:linear-gradient(105deg,transparent 10%,#ffffff08 32%,transparent 44%);opacity:.8}.cardhead{position:relative;display:flex;justify-content:space-between;align-items:center;gap:12px;padding:19px 23px;border-bottom:1px solid var(--edge)}.cardhead h2{font-size:20px;letter-spacing:-.5px;margin:0}.cardhead h3{font-size:18px;margin:0}.premium{font-size:10px;letter-spacing:2px;border:1px solid var(--edge);padding:4px 7px;border-radius:6px;color:var(--muted)}.hero{padding-bottom:18px}.meta{display:flex;gap:12px;padding:16px 22px 0;flex-wrap:wrap;align-items:stretch}.stat{min-width:190px;flex:1;padding:11px 15px;border-radius:13px;background:var(--field);border:1px solid var(--edge)}.stat label{display:block;font-size:11px;letter-spacing:1px;text-transform:uppercase;color:var(--muted)}.stat strong{display:block;font-size:23px;letter-spacing:-.6px}.stat button{border:0;background:none;font-weight:700;color:var(--accent);padding:0}.profiles{display:flex;align-items:center;gap:8px;margin-left:auto}.profiles select{padding:12px 34px 12px 12px;border-radius:10px;background:var(--field);color:var(--text);border:1px solid var(--edge)}.visual{position:relative;margin:16px 22px 0;border:1px solid var(--edge);border-radius:15px;background:linear-gradient(180deg,#ffffff05,#0000000b),var(--panel);padding:18px 18px 14px;overflow:hidden}.prep{position:relative;z-index:2;display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;align-items:start}.prepgroup{display:flex;align-items:center;gap:15px}.prepgroup.evening{justify-content:end}.preplabel{font-size:12px;letter-spacing:.3px;color:var(--muted);text-transform:uppercase}.preplabel strong{display:block;font-size:16px;color:var(--text);font-weight:650;text-transform:none}.pill{border:1px solid var(--edge);border-radius:10px;background:var(--field);padding:9px 13px;display:inline-block;text-align:center;min-width:105px}.pill span{display:block;font-size:11px;color:var(--muted)}.pill button{border:0;background:none;color:var(--accent);font-weight:700;font-size:18px}.centerprep{justify-self:center}.battery{--fill:50;--reserve:50;position:relative;width:90px;height:161px;padding:8px;border:3px solid #7f9ca9;border-radius:16px;background:linear-gradient(90deg,#253c43,#80949b 8%,#344b53 15%,#233640 85%,#8da9ad 94%,#293e47);box-shadow:inset 0 1px 3px #ffffff38,0 7px 15px #0005;flex:none}.battery:before{content:\"\";position:absolute;left:29%;width:42%;height:9px;top:-12px;border:2px solid #9fc1cd;border-radius:5px 5px 0 0;background:linear-gradient(90deg,#516875,#d5e9e7,#607883)}.battery .inner{position:relative;height:100%;width:100%;border-radius:8px;overflow:hidden;background:linear-gradient(90deg,#0a151f,#1d2e36);box-shadow:inset 0 0 9px #000e;display:flex;flex-direction:column;justify-content:flex-end}.battery .inner:after{content:\"\";pointer-events:none;position:absolute;inset:0;background:linear-gradient(90deg,#ffffff24,transparent 24%,#ffffff0b 57%,#00000030 95%),linear-gradient(180deg,#ffffff22,transparent 15%,transparent 88%,#ffffff10);z-index:3}.battery .reserve{height:calc(var(--reserve)*1%);order:2;background:linear-gradient(90deg,#f26c30,#ffab61 52%,#bc451a);transition:height 1s cubic-bezier(.22,1,.36,1);display:grid;place-items:center;min-height:0}.battery .usable{height:calc((100 - var(--reserve))*1%);order:1;background:linear-gradient(90deg,#12965e,#4feb9b 56%,#008753);transition:height 1s cubic-bezier(.22,1,.36,1);display:grid;place-items:center;min-height:0}.battery .num{color:#fff;text-shadow:0 2px 4px #000b;font-weight:800;font-size:17px;white-space:nowrap}.battery .inner .num{position:relative;z-index:4}.battery.small{width:63px;height:114px;border-radius:12px;padding:5px}.battery.small:before{height:7px;top:-10px}.battery.small .num{font-size:13px}.chartbox{position:relative;z-index:1;margin-top:7px}.chartbox svg{width:100%;height:300px;display:block;overflow:visible}.chartgrid{stroke:var(--muted);opacity:.17;stroke-width:1;stroke-dasharray:4 8}.axis{stroke:var(--muted);opacity:.4}.curve{fill:none;stroke:#55c9f5;stroke-width:5;stroke-linecap:round;filter:drop-shadow(0 0 7px #31bdff88);transition:d .9s cubic-bezier(.22,1,.36,1)}.chartfill{fill:url(#areafill);transition:d .9s cubic-bezier(.22,1,.36,1)}.chartpoint{fill:#b1f3ff;stroke:#0d5b83;stroke-width:4;transition:cy .9s cubic-bezier(.22,1,.36,1)}.charttext{fill:var(--muted);font-size:13px}.charttext.title{fill:var(--text);font-weight:700;font-size:16px}.charttext.value{fill:var(--accent);font-size:24px;font-weight:800}.thresholds{display:grid;grid-template-columns:repeat(4,1fr);gap:11px;padding:3px 22px 0}.threshold{min-height:90px;border:1px solid var(--edge);background:var(--field);border-radius:12px;text-align:left;padding:12px}.threshold span{display:block;font-size:12px;color:var(--muted);min-height:34px}.threshold strong{color:var(--accent);font-size:23px}.modegrid{display:grid;grid-template-columns:1.35fr 1fr 1fr;gap:15px;margin-top:15px}.modecontent{display:flex;gap:18px;align-items:center;justify-content:space-around;padding:22px 16px 25px;min-height:325px}.modevalues{display:flex;flex-direction:column;gap:14px;flex:1;max-width:140px}.modevalues span{font-size:13px;color:var(--muted)}.modevalues strong{display:block;font-size:25px;color:var(--accent)}.modevalues button{border:0;background:transparent;padding:0;text-align:left}.tiers{display:grid;grid-template-columns:1.15fr .8fr;gap:8px;flex:1}.tierrow{display:contents}.tier{padding:6px 5px;border:1px solid #8debc766;background:linear-gradient(90deg,#14855e,#30a977 65%,#116542);border-radius:7px;color:#fff;font-size:13px;font-weight:700;text-align:center}.tier.price{background:var(--field);border-color:var(--edge);color:var(--accent)}.modebattery{height:245px;width:116px}.modebattery .num{font-size:19px}.rainrow{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:21px}.rainitem{display:flex;align-items:center;gap:14px;padding:17px 19px;background:var(--field);border:1px solid var(--edge);border-radius:13px}.rainicon{font-size:46px;filter:drop-shadow(0 6px 7px #0005)}.rainitem small{display:block;color:var(--muted)}.rainitem button{background:none;border:none;padding:0;font-size:25px;color:var(--accent);font-weight:800}.weather{margin-top:15px}.note{font-size:12px;color:var(--muted);margin:18px 5px}.modalback{position:fixed;inset:0;background:#020d17cc;backdrop-filter:blur(7px);z-index:99;display:none;place-items:center;padding:16px}.modalback.show{display:grid}.modal{width:min(440px,100%);border-radius:20px;border:1px solid #7995a8;background:linear-gradient(160deg,#203e4a,#10232e);box-shadow:0 30px 100px #000d;padding:23px;color:white}.modal h3{font-size:21px;margin:0 0 5px}.modal p{color:#b8cbd4;margin:0 0 17px;font-size:13px}.modal input[type=range]{width:100%;accent-color:#44ccee;margin:19px 0}.modal input[type=number]{width:130px;background:#0c1b25;color:white;border:1px solid #667e91;border-radius:10px;padding:10px 12px;font-size:24px;font-weight:700}.modal .actions{display:flex;justify-content:end;gap:9px;margin-top:22px}.previewvalue{font-size:40px;color:#7ee7fa;font-weight:750}.minmax{display:flex;justify-content:space-between;color:#a3bdc7;font-size:12px}.kbdnote{color:var(--muted);font-size:12px}.toast{position:fixed;right:20px;bottom:20px;background:#113d46;border:1px solid #52c0bc;color:#e7fffe;padding:12px 18px;border-radius:12px;box-shadow:0 12px 35px #0008;opacity:0;transform:translateY(12px);transition:all .25s;z-index:105;pointer-events:none}.toast.show{opacity:1;transform:translateY(0)}\n@media(max-width:1000px){.modegrid{grid-template-columns:1fr 1fr}.modegrid .card:first-child{grid-column:span 2}.thresholds{grid-template-columns:1fr 1fr}.prepgroup{gap:7px}.preplabel strong{font-size:14px}}@media(max-width:650px){.shell{padding:13px 10px 30px}.branding h1{font-size:19px}.meta{padding:12px}.profiles{margin:0;width:100%}.visual{margin:12px 10px;padding:12px 5px}.prep{grid-template-columns:1fr 1fr}.centerprep{grid-column:span 2;grid-row:1}.prepgroup{flex-direction:column}.prepgroup.evening{justify-content:center}.chartbox svg{height:220px}.thresholds{padding:9px;gap:7px}.threshold{padding:9px;min-height:85px}.threshold span{font-size:11px}.threshold strong{font-size:20px}.modegrid{grid-template-columns:1fr;gap:11px}.modegrid .card:first-child{grid-column:span 1}.rainrow{grid-template-columns:1fr}.cardhead{padding:12px 15px}.cardhead h2{font-size:18px}.prep .pill{min-width:0}.charttext{font-size:14px}.stat{min-width:140px}.modecontent{min-height:0}}\n\n/* Direct-manipulation edition */\n.chartpoint{cursor:ns-resize;touch-action:none;stroke-width:5;filter:drop-shadow(0 0 5px #48cfff)}\n#chart.dragging .curve,#chart.dragging .chartfill,#chart.dragging .chartpoint{transition:none!important}\n.chartbox svg{touch-action:pan-x}\n.battery{touch-action:none}\n.battery .inner{overflow:hidden}\n.battery .inner .drag-divider{position:absolute;left:0;right:0;bottom:calc(var(--reserve)*1%);height:20px;transform:translateY(50%);z-index:10;cursor:ns-resize;touch-action:none;display:flex;justify-content:center;align-items:center}\n.battery .inner .drag-divider:before{content:'';display:block;width:100%;height:3px;background:#f5ffff;box-shadow:0 0 8px #00232a,0 0 4px #fff}\n.battery .inner .drag-top{bottom:calc(var(--charge)*1%)!important}.battery .inner .drag-top:before{background:#c9fff5}.battery .inner .drag-top:after{content:\"\u2195\";background:#a9f6cb}.battery .inner .drag-divider:after{content:'\u22ee\u22ee';color:#073442;position:absolute;background:#d6faff;border-radius:7px;padding:0 4px;font-size:11px;line-height:13px;box-shadow:0 1px 5px #0008}\n.battery.dragging .usable,.battery.dragging .reserve{transition:none}\n.normal-layout{display:grid;grid-template-columns: minmax(105px,145px) minmax(84px,1fr) 25px;gap:11px;width:100%;height:280px;align-items:stretch;justify-content:center}\n.normal-battery{width:100%;height:100%;padding:9px;min-width:0}\n.normal-battery .normal-inner{position:relative;height:100%;border-radius:8px;overflow:hidden;display:flex;flex-direction:column;background:#061920;box-shadow:inset 0 1px 8px #000}\n.normal-tier{position:relative;display:grid;place-items:center;min-height:0;background:linear-gradient(105deg,#137e57,#37cf8d 55%,#087c53);border-bottom:2px solid #dcfff89c;font-size:clamp(10px,1.2vw,14px);font-weight:800;color:#fff;text-shadow:0 1px 2px #003b32;transition:flex .55s cubic-bezier(.22,1,.36,1);white-space:nowrap}\n.normal-tier:after{content:'';pointer-events:none;position:absolute;inset:0;background:linear-gradient(90deg,#ffffff45,transparent 22%,#ffffff17 59%,#0007)}\n.normal-tier button{border:0;background:none;color:inherit;position:relative;z-index:2;cursor:pointer;padding:1px 2px;font-size:inherit;font-weight:inherit}\n.normal-tier .tier-handle{position:absolute;z-index:9;left:0;right:0;bottom:-10px;height:20px;cursor:ns-resize;touch-action:none;display:grid;place-items:center}\n.normal-tier .tier-handle:before{content:'\u22ee\u22ee';color:#063d46;background:#d8ffff;border-radius:5px;padding:0 4px;font-size:10px;line-height:13px;box-shadow:0 1px 4px #0009}\n.normal-battery.dragging .normal-tier{transition:none}\n.normal-prices{display:flex;flex-direction:column;justify-content:stretch;gap:0;padding:9px 0;height:100%;min-height:0}\n.normal-price{border:1px solid var(--edge);border-radius:6px;background:var(--field);color:var(--accent);font-size:13px;font-weight:800;padding:0 2px;min-width:0;min-height:0;cursor:pointer;transition:flex .55s cubic-bezier(.22,1,.36,1)}.normal-battery.dragging + .normal-prices .normal-price{transition:none}\n.badweather{display:flex;flex-direction:column;justify-content:end;align-items:center;gap:3px;color:#6ecfff;position:relative;border-left:3px solid #4daaff;margin:0;min-width:0;align-self:stretch;justify-content:center}\n.badweather strong{writing-mode:vertical-rl;transform:rotate(180deg);letter-spacing:1px;font-size:10px;white-space:nowrap}\n.badweather small{display:none}.badweather span{font-size:15px}\n@media(max-width:650px){.normal-layout{height:310px;grid-template-columns:minmax(95px,135px) minmax(70px,1fr) 24px}.normal-tier{font-size:12px}}\n.battery .num.usable-stack{display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1.15;gap:3px;text-align:center;white-space:normal}.battery .num.usable-stack small{font-size:12px;font-weight:600;white-space:nowrap}.battery.small .inner .drag-divider{height:17px}.charttext.title{transition:opacity .2s ease}.charttext.title.obscured{opacity:0}.battery .inner .drag-divider{transform:translateY(50%)}\n/* Desktop: place morning preparation immediately inside the chart's Y-axis. */\n@media(min-width:651px){.prepgroup:not(.evening){transform:translateX(76px)}}\n@media(max-width:650px){.prepgroup:not(.evening){transform:none}}\n\n.battery .num{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;line-height:1.08;text-align:center}.battery .num b{font-size:inherit}.battery .num small{font-size:10px;font-weight:600;white-space:nowrap}.battery.small .num small{font-size:8px}.battery.small .num{gap:1px}.battery .num.usable-stack small{font-size:10px}.battery.small .inner .num{max-width:100%}\n:host{display:block;min-width:0} .app{border-radius:18px;min-width:0} .shell{padding:15px 10px 24px} .modalback{position:fixed} .note{display:none} .toolbar #reset{display:none} .chartpoint{touch-action:none;cursor:ns-resize} .drag-divider,.tier-handle{touch-action:none} .app.readonly [data-key],.app.readonly .tier-handle,.app.readonly .drag-divider{cursor:default;pointer-events:none} .warning{padding:8px 14px;color:#eaa35f;font-size:12px} .stat button[disabled]{opacity:.85;cursor:default}\n";
const MARKUP="<div class=\"app\">\n<div class=\"shell\"><div class=\"topline\"><div class=\"branding\"><div><h1>Wholesale Pricing Strategy</h1><small>Interactive Home Assistant controls</small></div></div><div class=\"toolbar\"></div></div>\n<section class=\"card hero\"><header class=\"cardhead\"><h2>Spike Preparation &amp; Buy Pricing</h2><span class=\"premium\">PREMIUM</span></header><div class=\"meta\"><div class=\"stat\"><label>Total battery capacity</label><strong><button data-key=\"capacity\"></button> kWh</strong></div><div class=\"stat\"><label>Maximum export</label><strong><button data-key=\"export\"></button> kW</strong></div><div class=\"profiles\"><select id=\"profile\"><option>Profile 1</option><option>Profile 2</option><option>Profile 3</option></select><button class=\"btn primary\" id=\"save\" title=\"Save profile\">\u25a3 Save</button><button class=\"btn\" id=\"load\" title=\"Load profile\">\u21bb Load</button></div></div>\n<div class=\"visual\"><div class=\"prep\"><div class=\"prepgroup\"><div class=\"battery small\" id=\"morning-battery\"><div class=\"inner\"><div class=\"usable\"><span class=\"num\" id=\"morningusable\">40%</span></div><div class=\"reserve\"><span class=\"num\" id=\"morningreserve\">20%</span></div></div></div><div class=\"preplabel\">Morning battery preparation<strong>Charge to <a class=\"clickval\" data-key=\"morningPrep\"></a></strong><strong>Reserve <a class=\"clickval\" data-key=\"morningReserve\"></a></strong></div></div><div class=\"centerprep pill\"><span>Curtail if sell price below</span><button data-key=\"curtail\"></button></div><div class=\"prepgroup evening\"><div class=\"battery small\" id=\"evening-battery\"><div class=\"inner\"><div class=\"usable\"><span class=\"num\" id=\"eveningusable\">100%</span></div><div class=\"reserve\" style=\"display:none\"></div></div></div><div class=\"preplabel\">Evening battery preparation<strong>Charge to <a class=\"clickval\" data-key=\"eveningPrep\"></a></strong></div></div></div>\n<div class=\"chartbox\"><svg id=\"chart\" viewBox=\"0 0 1100 320\" preserveAspectRatio=\"none\" aria-label=\"Animated morning and evening spike definition curve\"><defs><linearGradient id=\"areafill\" x1=\"0\" y1=\"0\" x2=\"0\" y2=\"1\"><stop offset=\"0\" stop-color=\"#4ddfff\" stop-opacity=\".39\"/><stop offset=\"1\" stop-color=\"#4ddfff\" stop-opacity=\"0\"/></linearGradient></defs><path class=\"axis\" d=\"M55 24V278H1070\" fill=\"none\"/><path class=\"chartgrid\" d=\"M55 78H1070M55 148H1070M55 218H1070M260 25V278M540 25V278M815 25V278\" fill=\"none\"/><path id=\"area\" class=\"chartfill\"/><path id=\"curve\" class=\"curve\"/><circle class=\"chartpoint\" id=\"mpoint\" r=\"11\" cx=\"320\"/><circle class=\"chartpoint\" id=\"epoint\" r=\"11\" cx=\"820\"/><text class=\"charttext title\" id=\"morningTitle\" x=\"210\" y=\"35\">MORNING SPIKE</text><text class=\"charttext title\" id=\"eveningTitle\" x=\"772\" y=\"35\">EVENING SPIKE</text><text class=\"charttext\" x=\"9\" y=\"165\" transform=\"rotate(-90 20 165)\">SELL PRICE</text><text class=\"charttext\" x=\"190\" y=\"310\">AM</text><text class=\"charttext\" x=\"530\" y=\"310\">TIME OF DAY</text><text class=\"charttext\" x=\"920\" y=\"310\">PM</text><g class=\"charttext value\" style=\"cursor:pointer\"><text x=\"320\" y=\"70\" id=\"morningChartValue\" text-anchor=\"middle\">100 c</text><text x=\"820\" y=\"70\" id=\"eveningChartValue\" text-anchor=\"middle\">200 c</text></g></svg></div>\n</div><div class=\"thresholds\"><button class=\"threshold\" data-key=\"morningBuy\"><span>Max charging price<br>if morning spike detected</span><strong class=\"value\"></strong></button><button class=\"threshold\" data-key=\"dayBuy\"><span>Normal daytime maximum<br>charging price</span><strong class=\"value\"></strong></button><button class=\"threshold\" data-key=\"batteryUseCost\"><span>Import from grid<br>when under</span><strong class=\"value\"></strong></button><button class=\"threshold\" data-key=\"eveningBuy\"><span>Max charging price<br>if evening spike detected</span><strong class=\"value\"></strong></button></div></section>\n<div class=\"modegrid\"><section class=\"card\"><header class=\"cardhead\"><h3>\u25eb Normal Mode</h3><span class=\"premium\">PREMIUM</span></header><div class=\"modecontent\"><div class=\"normal-layout\"><div class=\"normal-battery battery\" id=\"normalBattery\"><div class=\"normal-inner\" id=\"tiers\"></div></div><div class=\"normal-prices\" id=\"tierPrices\"></div><div class=\"badweather\"><span>\u2602</span><strong>BAD WEATHER MODE</strong><small>Bottom four tiers</small></div></div></div></section><section class=\"card\"><header class=\"cardhead\"><h3>\u2197 High Sell Mode</h3><span class=\"premium\">PREMIUM</span></header><div class=\"modecontent\"><div class=\"battery modebattery\" id=\"highBattery\"><div class=\"inner\"><div class=\"usable\"><span class=\"num usable-stack\" id=\"highUsable\"><b>50%</b><small>Usable</small></span></div><div class=\"reserve\"><span class=\"num\" id=\"highReserve\">50%</span></div></div></div><div class=\"modevalues\"><button data-key=\"highSell\"><span>Minimum sell price</span><strong class=\"value\"></strong></button><button data-key=\"highReserve\"><span>Battery reserve</span><strong class=\"value\"></strong></button></div></div></section><section class=\"card\"><header class=\"cardhead\"><h3>\u21c4 Sell-Buy Mode</h3><span class=\"premium\">PREMIUM</span></header><div class=\"modecontent\"><div class=\"battery modebattery\" id=\"sellBattery\"><div class=\"inner\"><div class=\"usable\"><span class=\"num usable-stack\" id=\"sellUsable\"><b>50%</b><small>Usable</small></span></div><div class=\"reserve\"><span class=\"num\" id=\"sellReserve\">50%</span></div></div></div><div class=\"modevalues\"><button data-key=\"sellDiff\"><span>Sell / buy price difference</span><strong class=\"value\"></strong></button><button data-key=\"sellReserve\"><span>Battery reserve</span><strong class=\"value\"></strong></button></div></div></section></div>\n<section class=\"card weather\"><header class=\"cardhead\"><h3>\u2601 Weather Settings</h3><span class=\"premium\">PREMIUM</span></header><div class=\"rainrow\"><div class=\"rainitem\"><span class=\"rainicon\">\ud83c\udf27\ufe0f</span><div><small>Bad-weather rain threshold \u2014 today</small><button data-key=\"rainToday\"></button></div></div><div class=\"rainitem\"><span class=\"rainicon\">\ud83c\udf27\ufe0f</span><div><small>Bad-weather rain threshold \u2014 tomorrow</small><button data-key=\"rainTomorrow\"></button></div></div></div></section></div>\n<div class=\"modalback\" id=\"overlay\"><div class=\"modal\" role=\"dialog\" aria-modal=\"true\" aria-labelledby=\"editTitle\"><h3 id=\"editTitle\">Edit setting</h3><p id=\"editDesc\"></p><div class=\"previewvalue\" id=\"preview\"></div><input id=\"range\" type=\"range\" min=\"0\" max=\"100\" step=\"1\"><div class=\"minmax\"><span id=\"minlabel\"></span><span id=\"maxlabel\"></span></div><div style=\"margin-top:16px\"><label for=\"numedit\" style=\"display:block;font-size:12px;color:#b8cbd4;margin-bottom:5px\">Exact value</label><input id=\"numedit\" type=\"number\" step=\"1\"></div><div class=\"actions\"><button class=\"btn\" id=\"cancel\">Cancel</button><button class=\"btn primary\" id=\"apply\">Apply change</button></div></div></div><div class=\"toast\" id=\"toast\"></div>\n</div>";
if(!customElements.get('energy-manager-wholesale-pricing-card'))customElements.define('energy-manager-wholesale-pricing-card',EnergyManagerWholesalePricingCard);
