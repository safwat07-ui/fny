/* Shared by every public page. __T__ and __CAT__ are filled in by build.py. */
const LANG = document.documentElement.lang === 'ar' ? 'ar' : 'en';
const T = __T__;
const CAT0 = __CAT__;           // fallback catalog, both languages
let FEE = 25;
const AR = LANG === 'ar';
const PAGE = { book: AR ? 'book-ar.html' : 'book.html', services: AR ? 'services-ar.html' : 'services.html',
               home: AR ? 'index-ar.html' : 'index.html', track: 'track.html?lang=' + LANG };

function esc(x){const d=document.createElement('div');d.textContent=x==null?'':String(x);return d.innerHTML}
function n2(n){return Number(n||0).toLocaleString('en-US')}
function money(n){return AR ? n2(n)+' جنيه' : 'EGP '+n2(n)}
function moneyHTML(n){return AR ? `<span class="num">${n2(n)}</span><small>جنيه</small>` : `<small>EGP</small><span class="num">${n2(n)}</span>`}

/* Normalise a catalog into [{slug,name,short,blurb,jobs:[{id,title,detail,price,insp}]}] in the page language. */
function fromFallback(){
  return CAT0.map(s=>({slug:s.slug,name:AR?s.ar:s.en,short:AR?s.short_ar:s.short_en,blurb:AR?s.blurb_ar:s.blurb_en,
    jobs:s.jobs.map(j=>({id:j.id,title:AR?j.ar:j.en,detail:AR?j.dar:j.den,price:j.price,insp:!!j.insp}))}));
}
let CAT = fromFallback();
async function loadCatalog(){
  try{
    const r = await fetch('/api/services',{headers:{'Accept':'application/json'}});
    const d = await r.json();
    if(!d.ok) return CAT;
    if(typeof d.service_fee_egp==='number') FEE = d.service_fee_egp;
    const byId = {}; CAT0.forEach(s=>s.jobs.forEach(j=>byId[j.id]=j));
    CAT = d.services.map(s=>{
      const base = CAT0.find(x=>x.slug===s.slug) || {};
      return {slug:s.slug, name:AR?(s.name_ar||base.ar):(base.en||s.name_en), short:AR?(base.short_ar||s.name_ar):(base.short_en||s.name_en),
        blurb:AR?(base.blurb_ar||''):(base.blurb_en||''),
        jobs:(s.jobs||[]).map(j=>{
          const f = byId[j.id];
          // Arabic: prefer the admin's Arabic title, then our translation if the English title is unchanged
          const same = f && f.en === j.title;
          const title = AR ? (j.title_ar || (same ? f.ar : j.title)) : j.title;
          const detail = AR ? (j.detail_ar || (same ? f.dar : (j.detail||''))) : (j.detail||'');
          return {id:j.id, title, detail, price:j.price_egp, insp:!!j.is_inspection};
        })};
    }).filter(s=>s.jobs.length);
    applyLivePrices();
  }catch(e){ /* keep fallback prices */ }
  return CAT;
}
function findJob(id){for(const s of CAT)for(const j of s.jobs)if(j.id===+id)return {svc:s,job:j};return null}

/* Server-rendered rows carry data-job; refresh them from live data, hide retired jobs. */
function applyLivePrices(){
  document.querySelectorAll('[data-job]').forEach(el=>{
    const hit = findJob(el.dataset.job);
    if(!hit){ el.hidden = true; return; }
    el.hidden = false;
    el.querySelectorAll('[data-f=price]').forEach(p=>p.textContent=money(hit.job.price));
    el.querySelectorAll('[data-f=title]').forEach(p=>p.textContent=hit.job.title);
    el.querySelectorAll('[data-f=detail]').forEach(p=>p.textContent=hit.job.detail);
  });
  document.querySelectorAll('[data-from]').forEach(el=>{
    const s = CAT.find(x=>x.slug===el.dataset.from);
    if(s) el.textContent = money(Math.min(...s.jobs.map(j=>j.price)));
  });
}

/* Count a number up/down — answers the visitor's choice, skipped for reduced motion. */
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
function countTo(el, to){
  const from = +el.dataset.v || 0; el.dataset.v = to;
  if(REDUCED || from===to){ el.textContent = n2(to); return; }
  const t0 = performance.now(), dur = 380;
  const step = t=>{const k=Math.min(1,(t-t0)/dur), e=1-Math.pow(1-k,3);
    el.textContent = n2(Math.round(from+(to-from)*e)); if(k<1) requestAnimationFrame(step)};
  requestAnimationFrame(step);
}
document.querySelectorAll('[data-cta]').forEach(a=>a.addEventListener('click',()=>track('cta_click',{cta:a.dataset.cta,page:location.pathname,lang:LANG})));
