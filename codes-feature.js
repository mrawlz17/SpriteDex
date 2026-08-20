/* SpriteDex Codes feature — add with <script src="codes-feature.js"></script> before </body>. */
(()=>{
const CODE_CACHE_KEY='spritedex-code-data-v1';
const CODE_SYNC_KEY='spritedex-code-last-sync';
let codeData=null,codeFilter='available',codeCategory='all',codeSyncState='idle';

function codeMeta(){
 const m=meta();
 m.usedCodes=m.usedCodes||{};
 m.seenCodes=m.seenCodes||{};
 return m;
}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]))}
function lastCodeSync(){
 const raw=localStorage.getItem(CODE_SYNC_KEY);
 if(!raw)return 'Not yet checked';
 const d=new Date(raw);
 return Number.isNaN(d.getTime())?'Unknown':d.toLocaleDateString()+' '+d.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});
}
function isNewCode(id){return !codeMeta().seenCodes[id]}
function markFeedSeen(){
 if(!codeData?.codes?.length)return;
 const m=codeMeta();
 codeData.codes.forEach(c=>m.seenCodes[c.id]=true);
 persist();
}
function codeCounts(){
 const list=codeData?.codes||[],m=codeMeta();
 return {
  total:list.length,
  used:list.filter(c=>m.usedCodes[c.id]).length,
  available:list.filter(c=>!m.usedCodes[c.id]).length,
  fresh:list.filter(c=>!m.seenCodes[c.id]).length
 };
}
async function copyCode(code){
 try{
  await navigator.clipboard.writeText(code);
  toast(`${code} copied`);
 }catch{
  const area=document.createElement('textarea');area.value=code;document.body.appendChild(area);area.select();
  document.execCommand('copy');area.remove();toast(`${code} copied`);
 }
}
function toggleCodeUsed(id){
 const m=codeMeta();
 m.usedCodes[id]=!m.usedCodes[id];
 persist();
 renderCodes();
}
function setCodeFilter(value){codeFilter=value;renderCodes()}
function setCodeCategory(value){codeCategory=value;renderCodes()}

function injectCodesUi(){
 if(document.getElementById('codes'))return;

 const style=document.createElement('style');
 style.textContent=`
  .navInner{grid-template-columns:repeat(6,1fr)}
  .codeHero{border:3px solid var(--line);background:var(--panel);border-radius:9px;padding:16px;margin-bottom:14px;box-shadow:inset 0 0 0 2px rgba(255,255,255,.08),3px 3px 0 #17161a}
  .codeHero h2{margin:4px 0 4px;text-transform:uppercase}
  .codeStats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px}
  .codeStat{background:var(--card);border:2px solid var(--line);border-radius:6px;padding:10px;text-align:center}
  .codeStat b{display:block;font-size:20px}.codeStat span{font-size:9px;color:var(--muted);text-transform:uppercase}
  .codeFilters{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:12px 0 9px}
  .codeFilter.active{background:#715c85;color:#fff}
  .codeList{display:grid;gap:9px}
  .codeCard{background:var(--card);border:3px solid var(--line);border-radius:8px;padding:13px;box-shadow:inset 0 0 0 2px #68784d,3px 3px 0 #17161a}
  .codeCard.used{opacity:.62}
  .codeCard.used .codeValue,.codeCard.used .codeReward{text-decoration:line-through}
  .codeCard.unverified{border-color:#8b6b35}
  .codeTop{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
  .codeValue{font-size:18px;font-weight:950;letter-spacing:.02em;word-break:break-word}
  .codeReward{margin-top:5px;color:var(--text);font-size:12px;line-height:1.35}
  .codeMeta{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
  .codeBadge{display:inline-flex;padding:4px 6px;border:2px solid var(--line);border-radius:4px;background:var(--card2);font-size:8px;font-weight:900;text-transform:uppercase}
  .codeBadge.new{background:#76538f}.codeBadge.unverified{background:#7b6537}
  .codeActions{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:10px}
  .codeSync{display:flex;justify-content:space-between;gap:10px;align-items:center;margin:10px 0 14px;color:var(--muted);font-size:10px}
  @media(max-width:390px){.codeValue{font-size:15px}.codeActions .btn{font-size:10px;padding:8px 5px}}
 `;
 document.head.appendChild(style);

 const section=document.createElement('section');
 section.id='codes';section.className='view';
 section.innerHTML=`
  <div class="codeHero">
   <div class="kicker">Override admin panel</div>
   <h2>Cheat Codes</h2>
   <div class="subtle">Automatically checked. Redeemed codes stay saved to this collector.</div>
   <div class="codeStats">
    <div class="codeStat"><b id="codesAvailable">0</b><span>Available</span></div>
    <div class="codeStat"><b id="codesUsed">0</b><span>Used</span></div>
    <div class="codeStat"><b id="codesNew">0</b><span>New</span></div>
   </div>
  </div>
  <div class="codeFilters">
   <button class="btn codeFilter" data-code-filter="available">Available</button>
   <button class="btn codeFilter" data-code-filter="used">Used</button>
   <button class="btn codeFilter" data-code-filter="all">All</button>
  </div>
  <select id="codeCategoryFilter" aria-label="Code category"><option value="all">All categories</option></select>
  <div class="codeSync"><span id="codeSyncText">Checking codes…</span><button id="checkCodesNow" class="btn">Check Now</button></div>
  <div id="codeList" class="codeList"></div>`;
 document.querySelector('main').appendChild(section);

 const nav=document.createElement('button');
 nav.className='navBtn';nav.dataset.view='codes';
 nav.innerHTML=`<span class="updateDot codeUpdateDot" aria-hidden="true"></span><i><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v4H4zm2 6h12v8H6zm3 2v2H7v2h2v2h2v-2h2v-2h-2v-2zm6 1h2v2h-2z"/></svg></i>Codes`;
 const settings=document.querySelector('[data-view="settings"]');
 settings?.parentNode?.insertBefore(nav,settings);

 nav.addEventListener('click',()=>showView('codes'));
 section.querySelectorAll('[data-code-filter]').forEach(b=>b.addEventListener('click',()=>setCodeFilter(b.dataset.codeFilter)));
 section.querySelector('#codeCategoryFilter').addEventListener('change',e=>setCodeCategory(e.target.value));
 section.querySelector('#checkCodesNow').addEventListener('click',()=>syncCodes({manual:true}));
}

function renderCodes(){
 if(!document.getElementById('codes'))return;
 const list=codeData?.codes||[],m=codeMeta(),counts=codeCounts();
 $('codesAvailable').textContent=counts.available;
 $('codesUsed').textContent=counts.used;
 $('codesNew').textContent=counts.fresh;

 document.querySelectorAll('[data-code-filter]').forEach(b=>b.classList.toggle('active',b.dataset.codeFilter===codeFilter));
 const categories=[...new Set(list.map(c=>c.category||'Unknown'))].sort();
 const select=$('codeCategoryFilter');
 const old=select.value||codeCategory;
 select.innerHTML='<option value="all">All categories</option>'+categories.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('');
 select.value=categories.includes(old)?old:'all';codeCategory=select.value;

 const shown=list.filter(c=>{
  const used=!!m.usedCodes[c.id];
  if(codeFilter==='available'&&used)return false;
  if(codeFilter==='used'&&!used)return false;
  if(codeCategory!=='all'&&(c.category||'Unknown')!==codeCategory)return false;
  return true;
 });
 $('codeSyncText').textContent=codeSyncState==='checking'
  ? 'Checking hosted code list…'
  : codeSyncState==='error'
   ? `Offline · saved list · Last checked ${lastCodeSync()}`
   : `Automatic · Last checked ${lastCodeSync()}`;

 $('codeList').innerHTML=shown.map(c=>{
  const used=!!m.usedCodes[c.id],fresh=isNewCode(c.id),unverified=c.status==='unverified';
  return `<div class="codeCard ${used?'used':''} ${unverified?'unverified':''}">
   <div class="codeTop"><div>
    <div class="codeValue">${esc(c.code)}</div>
    <div class="codeReward">${esc(c.reward||'Reward not yet identified')}</div>
    <div class="codeMeta">
     <span class="codeBadge">${esc(c.category||'Unknown')}</span>
     ${fresh?'<span class="codeBadge new">New</span>':''}
     ${unverified?'<span class="codeBadge unverified">Unverified</span>':'<span class="codeBadge">Confirmed</span>'}
    </div>
   </div></div>
   <div class="codeActions">
    <button class="btn" data-copy-code="${esc(c.code)}">Copy Code</button>
    <button class="btn ${used?'':'primary'}" data-used-code="${esc(c.id)}">${used?'Mark Available':'Mark Used'}</button>
   </div>
  </div>`;
 }).join('')||'<div class="empty">No codes in this filter.</div>';

 $('codeList').querySelectorAll('[data-copy-code]').forEach(b=>b.addEventListener('click',()=>copyCode(b.dataset.copyCode)));
 $('codeList').querySelectorAll('[data-used-code]').forEach(b=>b.addEventListener('click',()=>toggleCodeUsed(b.dataset.usedCode)));

 const nav=document.querySelector('[data-view="codes"]');
 nav?.classList.toggle('hasUpdate',counts.fresh>0);
}

async function syncCodes({manual=false}={}){
 codeSyncState='checking';renderCodes();
 try{
  const r=await fetch(`codes.json?codeSync=${Date.now()}`,{cache:'no-store'});
  if(!r.ok)throw new Error(`Code database returned ${r.status}`);
  const remote=await r.json();
  if(!remote||!Array.isArray(remote.codes))throw new Error('Invalid code database');
  const firstLoad=!localStorage.getItem(CODE_CACHE_KEY);
  codeData=remote;
  localStorage.setItem(CODE_CACHE_KEY,JSON.stringify(remote));
  localStorage.setItem(CODE_SYNC_KEY,new Date().toISOString());
  codeSyncState='current';
  if(firstLoad){
   // Baseline current codes so the initial install does not label the whole catalog NEW.
   markFeedSeen();
  }
  renderCodes();
  if(manual)toast('Code list is current');
 }catch(err){
  console.warn('Code sync unavailable',err);
  codeSyncState='error';
  renderCodes();
  if(manual)toast('Code check unavailable');
 }
}

function bootCodes(){
 injectCodesUi();
 try{codeData=JSON.parse(localStorage.getItem(CODE_CACHE_KEY)||'null')}catch{}
 renderCodes();

 // Wrap normal render so collector switches/state changes stay reflected.
 const originalRender=render;
 render=function(){originalRender();renderCodes()};

 // Mark codes seen only after the user actually opens the Codes tab.
 const codesNav=document.querySelector('[data-view="codes"]');
 codesNav.addEventListener('click',()=>{
  setTimeout(()=>{renderCodes();markFeedSeen();renderCodes()},50);
 });
 setTimeout(()=>syncCodes(),450);
}
bootCodes();

Object.assign(window,{syncCodes,toggleCodeUsed,copyCode});
})();
