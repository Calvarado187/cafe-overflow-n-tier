'use strict';
// Presentation only: render data, capture inputs and call application use cases.
// No totals, loyalty percentages, thresholds or stock decisions are computed here.
const $ = (selector) => document.querySelector(selector);
let snapshot = {products: [], clients: [], orders: []};
let cart = new Map();
let quoteVersion = 0;
let requestKey = crypto.randomUUID();
let placing = false;
const money = (cents) => new Intl.NumberFormat('es-CO', {style:'currency',currency:'COP',maximumFractionDigits:2}).format(cents / 100);
const esc = (value) => String(value).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function notify(message, error=false) { const node=$('#message'); node.textContent=message;node.className=error?'error':'';node.hidden=false; }
async function api(path, body) {
  const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await response.json();if(!response.ok) throw new Error(data.error||'No se pudo completar la operación.');return data;
}
const descriptions={espresso:'Intenso, corto y directo al punto.',combo:'Tu café y un antojo: el mejor equipo.',te:'Una pausa suave para bajar el ritmo.',latte:'Espresso y leche, en perfecto equilibrio.',brownie:'Chocolate intenso para ideas brillantes.',sandwich:'Una pausa completa, capa por capa.'};
const symbols={espresso:'☕',combo:'{ + }',te:'∿',latte:'☕',brownie:'▦',sandwich:'≋'};
function renderProducts(){
  $('#product-count').textContent=`${snapshot.products.length} opciones para tu pausa`;
  $('#products').innerHTML=snapshot.products.map(p=>`<article class="product"><div class="product-art"><small>OVERFLOW / COFFEE & MORE</small><span class="symbol" aria-hidden="true">${symbols[p.id]||'☕'}</span></div><div class="product-body"><h3>${esc(p.name)}</h3><div class="product-description">${descriptions[p.id]||'Un nuevo favorito para acompañar tu pausa.'}</div><div class="product-bottom"><div><span class="price">${money(p.price_cents)}</span><span class="stock">${p.stock} unidades disponibles</span></div><button class="add" data-add="${esc(p.id)}" aria-label="Agregar ${esc(p.name)}">+</button></div></div></article>`).join('');
  $('#menu-table').innerHTML=snapshot.products.map(p=>`<tr><td>${esc(p.name)}</td><td>${money(p.price_cents)}</td><td>${p.stock}</td><td><button class="secondary" data-edit="${esc(p.id)}">Editar</button></td></tr>`).join('');
}
function renderProfile(){
  const client=snapshot.clients.find(c=>c.id===$('#client').value);$('#loyalty').hidden=!client;
  if(client) $('#loyalty').innerHTML=`<strong>${esc(client.level)}</strong> · ${client.points} DevPoints disponibles<br><span class="muted">Compras completadas: ${money(client.accumulated_cents)}</span>`;
}
function renderCart(){
  $('#cart').innerHTML=cart.size?[...cart].map(([id,quantity])=>{const p=snapshot.products.find(p=>p.id===id);return `<div class="cart-line"><span>${esc(p?.name||id)}</span><input aria-label="Cantidad de ${esc(p?.name||id)}" type="number" min="1" step="1" value="${quantity}" data-qty="${esc(id)}"><button class="remove" data-remove="${esc(id)}" aria-label="Quitar ${esc(p?.name||id)}">×</button></div>`;}).join(''):'<p class="empty">Tu pausa empieza con algo rico.<br>Elige un producto del menú.</p>';
}
function payload(){return {client_id:$('#client').value,items:[...cart].map(([product_id,quantity])=>({product_id,quantity})),redeem_points:Number($('#points').value),mode:$('#mode').value,table:$('#mode').value==='Mesa'?$('#table').value:'',request_key:requestKey};}
function invalidate(){requestKey=crypto.randomUUID();refreshQuote();}
async function refreshQuote(){
  const version=++quoteVersion;$('#confirm').disabled=true;
  if(!cart.size||!$('#client').value){$('#quote').innerHTML='<p class="muted">Selecciona tu perfil y tus productos para consultar el total.</p>';return;}
  $('#quote').textContent='Consultando tu pedido…';
  try{const q=await api('/api/quote',payload());if(version!==quoteVersion)return;
    $('#quote').innerHTML=`<div class="quote-row"><span>Subtotal</span><span>${money(q.subtotal_cents)}</span></div><div class="quote-row"><span>Beneficio ${esc(q.level)} (${q.discount_percent}%)</span><span>− ${money(q.level_discount_cents)}</span></div><div class="quote-row"><span>DevPoints redimidos</span><span>− ${money(q.points_discount_cents)}</span></div><div class="quote-row quote-total"><span>Total</span><span>${money(q.total_cents)}</span></div><p class="fine">Ganarás ${q.points_to_earn} DevPoints al recibir este pedido.</p>`;$('#confirm').disabled=placing;
  }catch(error){if(version===quoteVersion){$('#quote').innerHTML=`<p class="quote-error">${esc(error.message)}</p>`;}}
}
function orderCard(order, operation){
  const client=snapshot.clients.find(c=>c.id===order.client_id);
  return `<article class="order-card"><span class="pill">${esc(order.state)}</span><h3>Pedido ${esc(order.id.slice(0,8))}</h3><div class="order-meta">${esc(client?.name||'Cliente')} · ${esc(order.mode)} ${esc(order.table)}<br>${esc(new Date(order.created_at).toLocaleString('es-CO'))}</div><ul>${order.items.map(i=>`<li>${i.quantity} × ${esc(i.name)}</li>`).join('')}</ul><div class="order-price">${money(order.total_cents)}</div><div class="order-meta">${esc(order.level)} · ${order.discount_percent}% · ${order.redeemed_points} puntos redimidos</div>${operation&&order.next_state?`<button class="primary" data-state="${esc(order.next_state)}" data-order="${esc(order.id)}">${order.next_state==='En Preparación'?'Confirmar pago y preparar':`Marcar ${esc(order.next_state)}`}</button>`:''}</article>`;
}
function renderOrders(){
  const own=snapshot.orders.filter(o=>o.client_id===$('#client').value);
  $('#my-orders').innerHTML=own.length?own.map(o=>orderCard(o,false)).join(''):'<p class="muted">Aquí aparecerán los pedidos del perfil seleccionado.</p>';
  $('#operations').innerHTML=snapshot.orders.length?snapshot.orders.map(o=>orderCard(o,true)).join(''):'<p class="muted">Los pedidos aparecerán aquí cuando tus clientes los confirmen.</p>';
}
async function load(){
  const selected=$('#client').value;snapshot=await api('/api/bootstrap');
  $('#client').innerHTML='<option value="">Selecciona tu perfil</option>'+snapshot.clients.map(c=>`<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('');$('#client').value=selected;
  renderProducts();renderProfile();renderOrders();renderCart();await refreshQuote();
}
document.addEventListener('click',async(event)=>{
  const tab=event.target.closest('[data-tab]');if(tab){document.querySelectorAll('.tab').forEach(n=>n.hidden=n.id!==tab.dataset.tab);document.querySelectorAll('.nav').forEach(n=>{n.classList.toggle('active',n===tab);n.setAttribute('aria-pressed',n===tab?'true':'false');});}
  const add=event.target.closest('[data-add]');if(add){cart.set(add.dataset.add,(cart.get(add.dataset.add)||0)+1);renderCart();invalidate();}
  const remove=event.target.closest('[data-remove]');if(remove){cart.delete(remove.dataset.remove);renderCart();invalidate();}
  const edit=event.target.closest('[data-edit]');if(edit){const p=snapshot.products.find(p=>p.id===edit.dataset.edit);const f=$('#product-form');f.elements.id.value=p.id;f.elements.name.value=p.name;f.elements.price.value=(p.price_cents/100).toFixed(2);f.elements.stock.value=p.stock;f.elements.name.focus();}
  const state=event.target.closest('[data-state]');if(state){state.disabled=true;try{await api(`/api/orders/${state.dataset.order}/state`,{state:state.dataset.state});notify('Estado actualizado.');await load();}catch(error){notify(error.message,true);state.disabled=false;}}
});
$('#cart').addEventListener('change',event=>{if(event.target.dataset.qty){const value=Number(event.target.value);if(!Number.isInteger(value)||value<1){notify('La cantidad debe ser un entero positivo.',true);renderCart();return;}cart.set(event.target.dataset.qty,value);invalidate();}});
$('#client').addEventListener('change',()=>{renderProfile();renderOrders();invalidate();});
$('#mode').addEventListener('change',()=>{$('#table-field').hidden=$('#mode').value!=='Mesa';invalidate();});
$('#table').addEventListener('input',invalidate);$('#points').addEventListener('input',invalidate);
$('#client-form').addEventListener('submit',async(event)=>{event.preventDefault();const form=event.target;try{const client=await api('/api/clients',{name:form.elements.name.value,email:form.elements.email.value});await load();$('#client').value=client.id;form.reset();$('#new-client').open=false;renderProfile();renderOrders();invalidate();notify('Tu perfil Junior está listo. ¡Bienvenido a Overflow!');}catch(error){notify(error.message,true);}});
$('#product-form').addEventListener('submit',async(event)=>{event.preventDefault();const form=event.target;const raw=form.elements.price.value;if(!/^\d+(\.\d{1,2})?$/.test(raw)){notify('Usa un precio con máximo dos decimales.',true);return;}const [whole,decimal='']=raw.split('.');const price_cents=Number(whole)*100+Number(decimal.padEnd(2,'0'));try{await api('/api/products'+(form.elements.id.value?'/'+form.elements.id.value:''),{name:form.elements.name.value,price_cents,stock:Number(form.elements.stock.value)});form.reset();form.elements.id.value='';await load();notify('Menú actualizado.');}catch(error){notify(error.message,true);}});
$('#cancel-edit').addEventListener('click',()=>{$('#product-form').reset();$('#product-form').elements.id.value='';});
$('#confirm').addEventListener('click',async()=>{if(placing)return;placing=true;$('#confirm').disabled=true;try{const order=await api('/api/orders',payload());cart.clear();requestKey=crypto.randomUUID();$('#points').value='0';notify(`Pedido ${order.id.slice(0,8)} registrado. Confirma el pago en caja.`);await load();}catch(error){notify(error.message,true);}finally{placing=false;await refreshQuote();}});
for(const id of ['#refresh','#refresh-ops'])$(id).addEventListener('click',()=>load().catch(error=>notify(error.message,true)));
load().catch(error=>notify('No se pudo cargar el café: '+error.message,true));
