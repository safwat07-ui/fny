"""Booking (book.html / book-ar.html) and tracking (track.html) pages."""
import json
import __main__ as B   # helpers from build.py
from data import S, SERVICES, AREAS, SLOTS


def book(lang):
    t = S[lang]; L = lang
    B.page_for_footer[0] = "book"
    tiles = "".join(
        f'<button type="button" class="tile" data-slug="{s["slug"]}" aria-pressed="false">{B.ic(s["slug"])}'
        f'<span><b>{B.e(s[L])}</b><br><small>{t["from"]} <span data-from="{s["slug"]}">{B.money(min(j[3] for j in s["jobs"]), L)}</span></small></span></button>'
        for s in SERVICES)
    steps = "".join(f'<li><button type="button" data-go="{i+1}">{B.e(x)}</button></li>' for i, x in enumerate(t["steps"]))
    areas = "".join(f'<option value="{B.e(a[1] if L=="ar" else a[0])}">{B.e(a[1] if L=="ar" else a[0])}</option>' for a in AREAS)
    slots = json.dumps([{"h": h, "label": (ar if L == "ar" else en)} for h, en, ar in SLOTS], ensure_ascii=False)
    icons = json.dumps({s["slug"]: B.ic(s["slug"]) for s in SERVICES})
    body = f"""{B.nav(L, 'book', minimal=True)}
<main class="wrap flow-in">
  <div>
    <ol class="stepper" id="stepper">{steps}</ol>

    <section class="panel" data-p="1" aria-labelledby="h1">
      <h1 id="h1">{t['s1_h']}</h1><p class="sub">{t['s1_p']}</p>
      <div class="tiles" id="tiles">{tiles}</div>
      <p class="ferr" id="e1">{t['err_svc']}</p>
    </section>

    <section class="panel" data-p="2" aria-labelledby="h2">
      <h1 id="h2">{t['s2_h']}</h1><p class="sub">{t['s2_p']}</p>
      <fieldset class="jobs" id="jobs"><legend class="sr">{t['s2_h']}</legend></fieldset>
      <p class="ferr" id="e2">{t['err_job']}</p>
    </section>

    <section class="panel" data-p="3" aria-labelledby="h3">
      <h1 id="h3">{t['s3_h']}</h1><p class="sub">{t['s3_p']}</p>
      <span class="lbl" id="dayLbl">{t['day']}</span>
      <div class="days" id="days" role="group" aria-labelledby="dayLbl"></div>
      <p class="ferr" id="eDay">{t['err_day']}</p>
      <span class="lbl" id="slotLbl">{t['window']}</span>
      <div class="slots" id="slots" role="group" aria-labelledby="slotLbl"></div>
      <p class="ferr" id="eTime">{t['err_time']}</p>
      <label class="lbl" for="area">{t['area']}</label>
      <select class="inp" id="area">{areas}</select>
      <label class="lbl" for="addr">{t['address']}</label>
      <input class="inp" id="addr" autocomplete="street-address" placeholder="{B.e(t['address_ph'])}">
      <p class="ferr" id="eAddr">{t['err_addr']}</p>
      <div class="grid2">
        <div><label class="lbl" for="mob">{t['mobile']}</label>
          <input class="inp" id="mob" type="tel" inputmode="tel" autocomplete="tel" placeholder="{t['mobile_ph']}">
          <p class="ferr" id="eMob">{t['err_mob']}</p></div>
        <div><label class="lbl" for="cname">{t['name']} <small>({t['optional']})</small></label>
          <input class="inp" id="cname" autocomplete="name"></div>
      </div>
      <label class="lbl" for="notes">{t['notes']} <small>({t['optional']})</small></label>
      <textarea class="inp" id="notes" placeholder="{B.e(t['notes_ph'])}"></textarea>
    </section>

    <section class="panel" data-p="4" aria-labelledby="h4">
      <h1 id="h4">{t['s4_h']}</h1><p class="sub">{t['s4_p']}</p>
      <div class="review" id="review"></div>
      <span class="lbl" style="margin-top:26px">{t['pay_h']}</span>
      <div class="pays">
        <label class="pay"><input type="radio" name="pay" value="cash" checked><span class="rd"></span>{t['pay_cash']}</label>
        <label class="pay"><input type="radio" name="pay" value="card"><span class="rd"></span>{t['pay_card']}</label>
      </div>
      <p class="hint" id="payHint" hidden>{t['pay_card_note']}</p>
      <div class="next-box"><b>{t['after_h']}</b>{t['after_p']}</div>
      <div class="alert" id="alert" role="alert"></div>
    </section>

    <div class="actions" id="actions">
      <div class="tot"><small>{t['tk_total']}</small><b id="barTotal">—</b></div>
      <button type="button" class="btn btn-line" id="backBtn">{t['back']}</button>
      <span class="sp"></span>
      <button type="button" class="btn btn-amber btn-lg" id="nextBtn">{t['continue']}</button>
    </div>
  </div>

  <aside class="aside" aria-label="{B.e(t['summary'])}">
    <div class="ticket">
      <div class="stamp" id="stamp">{t['stamp']}</div>
      <div class="ticket-head"><h2>{t['summary']}</h2></div>
      <div id="sumTop"><p class="sum-empty">{t['sum_empty']}</p></div>
      <div class="tear" aria-hidden="true"></div>
      <div class="rc">
        <div class="rc-row"><span class="k">{t['tk_labor']}</span><span class="v num" id="sLabor">—</span></div>
        <div class="rc-row"><span class="k">{t['tk_fee']}</span><span class="v num" id="sFee">{B.money(25, L)}</span></div>
        <div class="rc-total"><span class="k">{t['tk_total']}</span><span class="v" id="sTotal">—</span></div>
      </div>
      <p class="rc-note" id="sNote">{t['tk_parts']}</p>
    </div>
  </aside>
</main>
"""
    js = r"""
const SLOTS = __SLOTS__, ICONS = __ICONS__;
const st = {step:1, slug:null, job:null, day:null, time:null, pay:'cash'};
const $ = id => document.getElementById(id);
const LEGACY = {"AC":"ac","Satellite & TV":"satellite","CCTV":"cctv","WiFi":"wifi","Intercom":"intercom","Smart Home":"smart-home"};
const digits = s => (s||'').replace(/[٠-٩]/g,d=>'٠١٢٣٤٥٦٧٨٩'.indexOf(d)).replace(/[۰-۹]/g,d=>'۰۱۲۳۴۵۶۷۸۹'.indexOf(d)).replace(/\D/g,'');

/* days: today + 6, labelled with the real date so the booking stays unambiguous later */
const dayFmt = new Intl.DateTimeFormat(AR?'ar-EG-u-nu-latn':'en-GB',{weekday:'short',day:'numeric',month:'short'});
const wdFmt = new Intl.DateTimeFormat(AR?'ar-EG':'en-GB',{weekday:'short'});
const DAYS = [];
for(let i=0;i<7;i++){const d=new Date();d.setDate(d.getDate()+i);DAYS.push({i,d,value:dayFmt.format(d).replace('،',''),
  top:i===0?T.today:i===1?T.tomorrow:wdFmt.format(d)})}
function slotOpen(dayIdx,h){ if(dayIdx!==0) return true; return h > new Date().getHours()+1; }
function renderDays(){
  $('days').innerHTML = DAYS.map(x=>{
    const full = !SLOTS.some(s=>slotOpen(x.i,s.h));
    return `<button type="button" class="day" data-i="${x.i}" aria-pressed="${st.day===x.i}" ${full?'disabled':''} aria-label="${esc(x.value)}">
      <small>${esc(full?T.full:x.top)}</small><b>${x.d.getDate()}</b></button>`}).join('');
}
function renderSlots(){
  $('slots').innerHTML = SLOTS.map(s=>{
    const open = st.day===null || slotOpen(st.day,s.h);
    return `<button type="button" class="slot" data-t="${esc(s.label)}" aria-pressed="${st.time===s.label}" ${open?'':'disabled'}>${esc(s.label)}</button>`}).join('');
}
$('days').addEventListener('click',ev=>{const b=ev.target.closest('.day');if(!b||b.disabled)return;
  st.day=+b.dataset.i; const s=SLOTS.find(x=>x.label===st.time); if(s&&!slotOpen(st.day,s.h)) st.time=null;
  renderDays();renderSlots();$('eDay').classList.remove('show');summary()});
$('slots').addEventListener('click',ev=>{const b=ev.target.closest('.slot');if(!b||b.disabled)return;
  st.time=b.dataset.t;renderSlots();$('eTime').classList.remove('show');summary()});

/* services + jobs */
$('tiles').addEventListener('click',ev=>{const b=ev.target.closest('.tile');if(!b)return;
  if(st.slug!==b.dataset.slug){st.slug=b.dataset.slug;st.job=null}
  markTiles();$('e1').classList.remove('show');summary();go(2)});
function markTiles(){document.querySelectorAll('.tile').forEach(x=>x.setAttribute('aria-pressed',x.dataset.slug===st.slug))}
function renderJobs(){
  const s = CAT.find(x=>x.slug===st.slug); if(!s) return;
  $('jobs').innerHTML = `<legend class="sr">${esc(T.s2_h)}</legend>` + s.jobs.map(j=>`
    <label class="job-opt"><input type="radio" name="job" value="${j.id}" ${j.id===st.job?'checked':''}><span class="rd"></span>
      <span class="t">${esc(j.title)}<small>${esc(j.detail)}</small></span>
      <span class="p num">${money(j.price)}${j.insp?`<em>${esc(T.insp_short)}</em>`:''}</span></label>`).join('');
}
$('jobs').addEventListener('change',ev=>{st.job=+ev.target.value;$('e2').classList.remove('show');summary(true);setTimeout(()=>go(3),180)});

/* summary ticket + mobile bar */
function cur(){return st.job?findJob(st.job):null}
function summary(pop){
  const hit=cur(), s=CAT.find(x=>x.slug===st.slug);
  $('sumTop').innerHTML = s ? `<div class="sum-svc">${ICONS[s.slug]||''}<div><b>${esc(hit?hit.job.title:s.name)}</b><small>${esc(s.name)}</small></div></div>
    <div class="sum-meta">${st.day!==null?`<div><span>${esc(T.rv_when)}</span><span>${esc(DAYS[st.day].value)}${st.time?' — '+esc(st.time):''}</span></div>`:''}
    ${st.step>=3?`<div><span>${esc(T.area)}</span><span>${esc($('area').value)}</span></div>`:''}</div>` : `<p class="sum-empty">${esc(T.sum_empty)}</p>`;
  $('sLabor').textContent = hit?money(hit.job.price):'—';
  $('sFee').textContent = money(FEE);
  $('sTotal').innerHTML = hit?moneyHTML(hit.job.price+FEE):'—';
  $('barTotal').textContent = hit?money(hit.job.price+FEE):'—';
  $('sNote').textContent = hit&&hit.job.insp?T.tk_insp:T.tk_parts;
  if(pop){const x=$('stamp');x.classList.remove('pop');void x.offsetWidth;x.classList.add('pop')}
  // keep the language switch on the same booking
  const q=new URLSearchParams(); if(st.job)q.set('job',st.job); else if(st.slug)q.set('svc',st.slug);
  const ls=$('langSwitch'); ls.href=ls.href.split('?')[0]+(q.toString()?'?'+q:'');
}

/* validation */
function bad(id,errId,cond){$(id).setAttribute('aria-invalid',cond);$(errId).classList.toggle('show',cond);return cond}
function valid(n){
  if(n===1){ if(!st.slug){$('e1').classList.add('show');return false} }
  if(n===2){ if(!st.job){$('e2').classList.add('show');return false} }
  if(n===3){
    let ok=true;
    if(st.day===null){$('eDay').classList.add('show');ok=false}
    if(!st.time){$('eTime').classList.add('show');ok=false}
    if(!fieldOk('addr'))ok=false;
    if(!fieldOk('mob'))ok=false;
    if(!ok){const f=document.querySelector('.ferr.show');f&&f.scrollIntoView({block:'center',behavior:REDUCED?'auto':'smooth'})}
    return ok;
  }
  return true;
}
function fieldOk(id){
  return id==='addr' ? !bad('addr','eAddr',$('addr').value.trim().length<5)
                     : !bad('mob','eMob',!/^01[0-9]{9}$/.test(digits($('mob').value)));
}
['addr','mob'].forEach(id=>{
  $(id).addEventListener('input',()=>{if($(id).getAttribute('aria-invalid')==='true')fieldOk(id)});
  $(id).addEventListener('blur',()=>{if($(id).value.trim())fieldOk(id)});
});
$('area').addEventListener('change',()=>summary());

/* review */
function renderReview(){
  const hit=cur(), name=$('cname').value.trim();
  const row=(k,v,sub,step)=>`<div class="rv"><span class="k">${esc(k)}</span><span class="v">${esc(v)}${sub?`<small>${esc(sub)}</small>`:''}</span><button type="button" data-go="${step}">${esc(T.edit)}</button></div>`;
  $('review').innerHTML = row(T.rv_job,hit.job.title,hit.svc.name+' — '+money(hit.job.price),2)
    + row(T.rv_when,DAYS[st.day].value,st.time,3)
    + row(T.rv_where,$('area').value,$('addr').value.trim(),3)
    + row(T.rv_contact,digits($('mob').value),name,3);
}
document.addEventListener('click',ev=>{const b=ev.target.closest('[data-go]');if(!b)return;const n=+b.dataset.go;
  if(n<st.step||b.closest('.review'))go(n)});
document.querySelectorAll('input[name=pay]').forEach(r=>r.addEventListener('change',()=>{st.pay=r.value;$('payHint').hidden=st.pay!=='card'}));

/* navigation */
function go(n){
  for(let i=1;i<n;i++) if(!valid(i)){ n=i; break; }
  st.step=n;
  if(n===2) renderJobs();
  if(n===3){ if(st.day===null){const first=DAYS.find(x=>SLOTS.some(s=>slotOpen(x.i,s.h)));st.day=first?first.i:null} renderDays();renderSlots(); }
  if(n===4) renderReview();
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('on',+p.dataset.p===n));
  document.querySelectorAll('#stepper li').forEach((li,i)=>{li.className=i+1<n?'done':i+1===n?'on':'';
    li.querySelector('button').setAttribute('aria-current',i+1===n?'step':'false')});
  $('backBtn').style.visibility=n>1?'visible':'hidden';
  $('nextBtn').textContent=n===4?T.confirm:T.continue;
  $('nextBtn').hidden=(n===1);
  $('alert').classList.remove('show');
  summary();
  window.scrollTo({top:0,behavior:REDUCED?'auto':'smooth'});
  track('booking_step',{step:n,service:st.slug||'',lang:LANG});
}
$('backBtn').addEventListener('click',()=>go(Math.max(1,st.step-1)));
$('nextBtn').addEventListener('click',()=>{ if(st.step<4){ if(valid(st.step)) go(st.step+1); } else confirmBooking(); });

async function confirmBooking(){
  const btn=$('nextBtn'); if(btn.disabled) return;
  for(let i=1;i<=3;i++) if(!valid(i)){go(i);return}
  btn.disabled=true; btn.textContent=T.confirming;
  const hit=cur(), total=hit.job.price+FEE;
  try{
    const r=await fetch('/api/bookings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      job_catalog_id:hit.job.id, customer_name:$('cname').value.trim()||null, customer_mobile:digits($('mob').value),
      area:$('area').value, address:$('addr').value.trim(), notes:$('notes').value.trim(),
      day:DAYS[st.day].value, time_window:st.time, payment_method:st.pay})});
    const d=await r.json();
    if(d.ok){
      track('booking_completed',{value:d.total_egp||total,currency:'EGP',service:st.slug,job_id:hit.job.id,lang:LANG});
      setTimeout(()=>location.href='track.html?code='+encodeURIComponent(d.code)+'&lang='+LANG+'&new=1',200);
      return;
    }
    $('alert').textContent=d.error||T.err_net;
  }catch(e){ $('alert').textContent=T.err_net; }
  $('alert').classList.add('show'); btn.disabled=false; btn.textContent=T.confirm;
}

/* deep links: ?job=ID, ?svc=slug (or old service names), ?area=, ?mob= */
const P=new URLSearchParams(location.search);
if(P.get('mob'))$('mob').value=P.get('mob');
if(P.get('area'))[...$('area').options].forEach(o=>{if(o.value===P.get('area'))$('area').value=o.value});
function applyParams(){
  const hit=P.get('job')&&findJob(P.get('job'));
  const slug=P.get('svc')&&(LEGACY[P.get('svc')]||P.get('svc'));
  if(hit){st.slug=hit.svc.slug;st.job=hit.job.id;markTiles();return 3}
  if(slug&&CAT.find(s=>s.slug===slug)){st.slug=slug;markTiles();return 2}
  return 1;
}
go(applyParams());
loadCatalog().then(()=>{
  document.querySelectorAll('.tile').forEach(b=>b.hidden=!CAT.find(s=>s.slug===b.dataset.slug));
  if(st.job&&!findJob(st.job)){st.job=null; if(st.step>2) go(2);}
  if(st.step===2) renderJobs(); if(st.step===4) renderReview();
  summary();
});
""".replace("__SLOTS__", slots).replace("__ICONS__", icons)
    css = B.read("site.css") + "\n" + B.read("flow.css")
    html_out = B.head(L, t["bk_title"], t["meta_desc"], css).replace("<body>", '<body class="flow">') + body + B.script(L, js)
    return html_out


TR = {
 "en": {"luT": "Track your booking", "luS": "Enter the booking code from your confirmation, like FN-12345.", "luB": "Show my booking",
        "luE": "We couldn't find that code. Check it and try again.", "code": "Booking code",
        "newT": "Booking confirmed", "newS": "Save your code. This page updates by itself as your booking moves.",
        "copy": "Copy link", "copied": "Link copied", "wa": "Send to WhatsApp",
        "bill": "Your bill", "labor": "Labor, fixed", "fee": "Service fee", "parts": "Approved parts", "total": "Total",
        "paid": "Paid", "unpaid": "Not paid yet", "pay": "Pay online", "payNA": "Pay cash to your technician after the job.",
        "tech": "Your technician", "techWait": "We're matching a technician to your job. You'll see their name and rating here.",
        "verified": "ID-verified, skill-tested", "jobs": "jobs", "new": "new",
        "partsT": "Approve these parts", "partsS": "Nothing is installed until you approve. If you reject a part, the job carries on without it.",
        "ok": "Approve", "no": "Reject", "partsDone": "Parts", "approved": "approved", "rejected": "rejected",
        "rate": "How was the visit?", "rateB": "Send rating", "rated": "Thanks, your rating was sent.",
        "tags": ["On time", "Clean work", "Fair with parts", "Explained everything", "Polite"],
        "states": {"new": ["Finding your technician", "We're matching the best فنّي for this job."],
                   "assigned": ["Technician assigned", "Your فنّي is preparing for the visit."],
                   "en_route": ["On the way", "Your فنّي is heading to your address."],
                   "arrived": ["Arrived", "Your فنّي is checking the fault with you."],
                   "working": ["Work in progress", "Any spare part comes to this page for your approval first."],
                   "done": ["Done, and under warranty", "Same fault back within 30 days? We send a فنّي back free."],
                   "cancelled": ["Booking cancelled", "This booking was cancelled. You can book again any time."]},
        "steps": [["new", "Received"], ["assigned", "Assigned"], ["en_route", "On the way"], ["working", "Working"], ["done", "Done"]],
        "sync": "Updated", "again": "Book another job", "cur": "EGP"},
 "ar": {"luT": "تابع طلبك", "luS": "اكتب كود الطلب اللي وصلك عند الحجز، زي FN-12345.", "luB": "اعرض طلبي",
        "luE": "ملقيناش الكود ده. اتأكد منه وجرب تاني.", "code": "كود الطلب",
        "newT": "تم تأكيد الحجز", "newS": "احتفظ بالكود. الصفحة دي بتتحدث لوحدها مع كل خطوة في طلبك.",
        "copy": "انسخ الرابط", "copied": "اتنسخ الرابط", "wa": "ابعته على واتساب",
        "bill": "الفاتورة", "labor": "المصنعية، ثابتة", "fee": "رسوم الخدمة", "parts": "قطع غيار وافقت عليها", "total": "الإجمالي",
        "paid": "مدفوع", "unpaid": "لسه مش مدفوع", "pay": "ادفع أونلاين", "payNA": "الدفع كاش للفني بعد الشغل.",
        "tech": "فنّيك", "techWait": "بنختار فني لشغلانتك. اسمه وتقييمه هيظهروا هنا.",
        "verified": "متحقق من هويته ومختبر عمليًا", "jobs": "شغلانة", "new": "جديد",
        "partsT": "وافق على قطع الغيار دي", "partsS": "مفيش حاجة بتتركب قبل موافقتك. لو رفضت قطعة، الشغل بيكمل من غيرها.",
        "ok": "موافق", "no": "رفض", "partsDone": "قطع الغيار", "approved": "اتوافق عليها", "rejected": "اترفضت",
        "rate": "الزيارة كانت عاملة إزاي؟", "rateB": "ابعت التقييم", "rated": "شكرًا، تقييمك وصل.",
        "tags": ["جه في معاده", "شغل نضيف", "أمين في قطع الغيار", "شرح كل حاجة", "محترم"],
        "states": {"new": ["بنختارلك فني", "بنرشح أنسب فنّي للشغلانة دي."],
                   "assigned": ["اتعيّن فني", "فنّيك بيجهز للزيارة."],
                   "en_route": ["في الطريق", "فنّيك متوجه لعنوانك."],
                   "arrived": ["وصل", "فنّيك بيراجع العطل معاك."],
                   "working": ["الشغل جاري", "أي قطعة غيار هتوصلك هنا توافق عليها الأول."],
                   "done": ["خلص، وعليه ضمان", "نفس العطل رجع خلال ٣٠ يوم؟ بنبعتلك فنّي تاني ببلاش."],
                   "cancelled": ["الطلب اتلغى", "الطلب ده اتلغى. تقدر تحجز تاني في أي وقت."]},
        "steps": [["new", "استلمنا"], ["assigned", "اتعيّن"], ["en_route", "في الطريق"], ["working", "شغال"], ["done", "خلص"]],
        "sync": "آخر تحديث", "again": "احجز شغلانة تانية", "cur": "جنيه"},
}


def track():
    """Single page for both languages (?lang=en|ar), as before."""
    L = "ar"
    B.page_for_footer[0] = "index"
    star = '<svg viewBox="0 0 24 24"><path d="M12 2.8l2.8 5.8 6.3.9-4.6 4.4 1.1 6.3L12 17.2l-5.6 3 1.1-6.3L2.9 9.5l6.3-.9z"/></svg>'
    body = f"""<header class="nav">
  <div class="wrap nav-in">
    <a class="logo" id="homeLink" href="index-ar.html"><b>فنّي</b><span>Fanni</span></a>
    <div class="nav-end"><a class="lang" id="langSwitch" href="#">English</a>
      <a class="btn btn-amber" id="bookLink" href="book-ar.html" data-cta="track_book"></a></div>
  </div>
</header>
<main class="wrap tr-in">
  <section class="lookup" id="lookup" hidden>
    <h1 id="luT"></h1><p id="luS"></p>
    <form class="row" id="luForm"><label class="sr" for="codeInput">code</label>
      <input class="inp" id="codeInput" placeholder="FN-12345" autocomplete="off">
      <button class="btn btn-teal" id="luB"></button></form>
    <p class="ferr" id="luE"></p>
  </section>

  <div id="tracker" hidden>
    <div class="banner" id="banner" hidden>{B.ic('check')}<div><span id="bnT"></span><p id="bnS"></p>
      <div class="share"><button type="button" class="btn btn-line" id="copyBtn"></button><a class="btn btn-line" id="waBtn" target="_blank" rel="noopener"></a></div></div></div>
    <div class="tr-grid">
      <div>
        <section class="status" id="status">
          <div class="top"><div><h1 id="stT"></h1><p class="sub" id="stS"></p></div>
            <div class="code"><span id="codeLbl"></span><b id="stCode" class="num"></b></div></div>
          <div class="chips" id="chips"></div>
          <ol class="tl" id="tl"></ol>
        </section>
        <section class="card partsc" id="partsCard" hidden></section>
        <section class="card" id="techCard"></section>
        <section class="card" id="rateCard" hidden>
          <h2 id="rateT"></h2>
          <div class="stars" id="stars">{''.join(f'<button type="button" class="star" data-s="{i}" aria-label="{i}">{star}</button>' for i in range(1,6))}</div>
          <div class="tags" id="tags"></div>
          <button type="button" class="btn btn-amber" id="rateBtn"></button>
        </section>
      </div>
      <aside class="billc"><div class="ticket">
        <div class="ticket-head"><h2 id="billT"></h2></div>
        <div class="rc" id="bill"></div>
        <div id="payBox"></div>
      </div>
      <section class="card" id="doneParts" hidden></section></aside>
    </div>
    <p class="sync" id="sync"></p>
  </div>
</main>
"""
    js = r"""
const TR = __TR__;
const P = new URLSearchParams(location.search);
const LG = P.get('lang')==='en' ? 'en' : 'ar';
const X = TR[LG];
document.documentElement.lang = LG; document.documentElement.dir = LG==='en'?'ltr':'rtl';
document.title = LG==='en' ? 'Track your booking | Fanni' : 'تابع طلبك | فنّي';
const $ = id => document.getElementById(id);
const cur = n => LG==='en' ? 'EGP '+n2(n) : n2(n)+' جنيه';
$('homeLink').href = LG==='en'?'index.html':'index-ar.html';
$('bookLink').href = LG==='en'?'book.html':'book-ar.html';
$('bookLink').textContent = X.again;
$('langSwitch').textContent = LG==='en'?'العربية':'English';
function setLangLink(){const q=new URLSearchParams(location.search);q.set('lang',LG==='en'?'ar':'en');q.delete('new');$('langSwitch').href='track.html?'+q}
setLangLink();
['luT','luS','luB'].forEach(k=>$(k).textContent=X[k]); $('luE').textContent=X.luE;
$('codeLbl').textContent=X.code; $('billT').textContent=X.bill; $('rateT').textContent=X.rate; $('rateBtn').textContent=X.rateB;
$('tags').innerHTML = X.tags.map(t=>`<button type="button" class="tag" aria-pressed="false">${esc(t)}</button>`).join('');
$('tags').addEventListener('click',ev=>{const b=ev.target.closest('.tag');if(b)b.setAttribute('aria-pressed',b.getAttribute('aria-pressed')!=='true')});

let CODE=null, timer=null, rating=0, rated=false;
const ORDER=['new','assigned','en_route','arrived','working','done'];

async function lookup(code){
  CODE=(code||'').trim().toUpperCase(); if(!CODE) return;
  if(/^\d{5}$/.test(CODE)) CODE='FN-'+CODE;
  try{
    const r=await fetch('/api/bookings/'+encodeURIComponent(CODE)); const d=await r.json();
    if(!d.ok) throw 0;
    $('lookup').hidden=true; $('tracker').hidden=false;
    render(d.booking);
    if(P.get('new')==='1') showBanner();
    clearInterval(timer); timer=setInterval(refresh,15000);
    const q=new URLSearchParams({code:CODE,lang:LG}); if(P.get('new')==='1')q.set('new','1');
    history.replaceState(null,'','track.html?'+q); setLangLink();
  }catch(e){ $('lookup').hidden=false; $('luE').classList.add('show'); }
}
async function refresh(){ try{const r=await fetch('/api/bookings/'+encodeURIComponent(CODE));const d=await r.json();if(d.ok)render(d.booking)}catch(e){} }
document.addEventListener('visibilitychange',()=>{ if(!document.hidden && CODE) refresh(); });

function showBanner(){
  const link=location.origin+'/track.html?code='+CODE+'&lang='+LG;
  $('banner').hidden=false; $('bnT').textContent=X.newT+' — '+CODE; $('bnS').textContent=X.newS;
  $('copyBtn').textContent=X.copy;
  $('copyBtn').onclick=()=>{navigator.clipboard&&navigator.clipboard.writeText(link).then(()=>{$('copyBtn').textContent=X.copied})};
  $('waBtn').textContent=X.wa; $('waBtn').href='https://wa.me/?text='+encodeURIComponent((LG==='en'?'My Fanni booking ':'طلب فنّي ')+CODE+'\n'+link);
}

function render(b){
  const s=X.states[b.status]||[b.status,''];
  $('stT').textContent=s[0]; $('stS').textContent=s[1]; $('stCode').textContent=b.code;
  $('status').classList.toggle('cancelled',b.status==='cancelled');
  $('chips').innerHTML=[b.day,b.time_window,b.area].filter(Boolean).map(x=>`<span>${esc(x)}</span>`).join('');
  const reached=b.status==='arrived'?'working':b.status, idx=ORDER.indexOf(reached);
  $('tl').innerHTML=X.steps.map(([k,lbl])=>{const i=ORDER.indexOf(k);
    const c=b.status==='cancelled'?'':(i<idx||b.status==='done'?'done':i===idx?'now':'');
    return `<li class="${c}" ${c==='now'?'aria-current="step"':''}>${esc(lbl)}</li>`}).join('');

  // technician
  const t=b.technician;
  $('techCard').innerHTML = `<h2>${esc(X.tech)}</h2>` + (t
    ? `<div class="tech"><div class="av">${esc((t.name||'?').trim()[0])}</div><div><b>${esc(t.name)}</b><small>${esc(X.verified)} — ${n2(t.jobs_done)} ${esc(X.jobs)}</small></div>
       <div class="r">${t.rating?t.rating.toFixed(1)+'★':esc(X.new)}</div></div>`
    : `<div class="wait">${b.status==='cancelled'?'':'<span class="dotp"></span>'}<span>${esc(b.status==='cancelled'?'—':X.techWait)}</span></div>`);

  // parts waiting for approval — shown above everything else in the column
  const parts=b.parts_quotes||[], pending=parts.filter(p=>p.status==='pending');
  const pname=p=>LG==='en'&&p.part_name_en?p.part_name_en:p.part_name;
  $('partsCard').hidden=!pending.length;
  if(pending.length) $('partsCard').innerHTML=`<h2>${esc(X.partsT)}</h2><p>${esc(X.partsS)}</p>`+pending.map(p=>`
    <div class="prow"><div class="nm">${esc(pname(p))}<small class="num">${cur(p.price_egp)}</small></div>
      <div class="bt"><button type="button" class="btn btn-ok" data-part="${p.id}" data-d="approved">${esc(X.ok)}</button>
      <button type="button" class="btn btn-line" data-part="${p.id}" data-d="rejected">${esc(X.no)}</button></div></div>`).join('');
  const decided=parts.filter(p=>p.status!=='pending');
  $('doneParts').hidden=!decided.length;
  if(decided.length) $('doneParts').innerHTML=`<h2>${esc(X.partsDone)}</h2><div class="plist-done">`+decided.map(p=>`
    <div><span>${esc(pname(p))}<span class="st-chip st-${p.status}">${esc(X[p.status])}</span></span><span class="num">${cur(p.price_egp)}</span></div>`).join('')+'</div>';

  // bill
  const paid=b.payment_status==='paid';
  $('bill').innerHTML=`
    <div class="rc-row"><span class="k">${esc(X.labor)}</span><span class="v num">${cur(b.labor_egp)}</span></div>
    <div class="rc-row"><span class="k">${esc(X.fee)}</span><span class="v num">${cur(b.service_fee_egp)}</span></div>
    ${b.parts_egp?`<div class="rc-row"><span class="k">${esc(X.parts)}</span><span class="v num">${cur(b.parts_egp)}</span></div>`:''}
    <div class="tear" aria-hidden="true"></div>
    <div class="rc-total" style="border:0;padding:0;margin:0"><span class="k">${esc(X.total)}<span class="paid ${paid?'':'unpaid'}">${esc(paid?X.paid:X.unpaid)}</span></span>
      <span class="v">${LG==='en'?'<small>EGP</small> ':''}<span class="num">${n2(b.total_egp)}</span>${LG==='ar'?' <small>جنيه</small>':''}</span></div>`;
  $('payBox').innerHTML = (!paid && b.status!=='cancelled')
    ? (b.payment_available ? `<button type="button" class="btn btn-teal btn-block btn-lg" id="payBtn" style="margin-top:18px">${esc(X.pay)}</button>`
                           : `<p class="rc-note">${esc(X.payNA)}</p>`) : '';
  if($('payBtn')) $('payBtn').onclick=payNow;

  $('rateCard').hidden = !(b.status==='done' && !rated);
  $('sync').textContent = X.sync+' '+new Date().toLocaleTimeString(LG==='en'?'en-GB':'ar-EG-u-nu-latn',{hour:'2-digit',minute:'2-digit'});
}

$('partsCard').addEventListener('click',async ev=>{
  const b=ev.target.closest('[data-part]'); if(!b) return;
  b.closest('.bt').querySelectorAll('button').forEach(x=>x.disabled=true);
  try{
    const r=await fetch('/api/bookings/'+encodeURIComponent(CODE)+'/parts/'+b.dataset.part+'/decision',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({decision:b.dataset.d})});
    const d=await r.json();
    if(d.ok){ track('part_decision',{decision:b.dataset.d,lang:LG}); render(d.booking); }
    else { alert(d.error); refresh(); }
  }catch(e){ b.closest('.bt').querySelectorAll('button').forEach(x=>x.disabled=false); }
});
async function payNow(){
  const btn=$('payBtn'); btn.disabled=true;
  try{ const r=await fetch('/api/bookings/'+encodeURIComponent(CODE)+'/pay',{method:'POST'}); const d=await r.json();
    if(d.ok){ track('payment_started',{value:d.amount_egp,currency:'EGP'}); location.href=d.iframe_url; return; }
    alert(d.error); }catch(e){}
  btn.disabled=false;
}
$('stars').addEventListener('click',ev=>{const b=ev.target.closest('.star');if(!b)return;rating=+b.dataset.s;
  document.querySelectorAll('.star').forEach(x=>x.classList.toggle('lit',+x.dataset.s<=rating))});
$('rateBtn').addEventListener('click',async()=>{
  if(!rating){ $('stars').querySelector('.star').focus(); return; }
  const btn=$('rateBtn'); btn.disabled=true;
  const tags=[...document.querySelectorAll('.tag[aria-pressed=true]')].map(x=>x.textContent);
  try{ const r=await fetch('/api/bookings/'+encodeURIComponent(CODE)+'/rating',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({stars:rating,tags})}); const d=await r.json();
    if(d.ok||/already/i.test(d.error||'')){ rated=true; track('rating_sent',{stars:rating}); $('rateCard').innerHTML=`<h2>${esc(X.rated)}</h2>`; return; }
    alert(d.error); }catch(e){}
  btn.disabled=false;
});
$('luForm').addEventListener('submit',ev=>{ev.preventDefault();$('luE').classList.remove('show');lookup($('codeInput').value)});
if(P.get('code')) lookup(P.get('code')); else { $('lookup').hidden=false; $('codeInput').focus(); }
""".replace("__TR__", json.dumps(TR, ensure_ascii=False))
    css = B.read("site.css") + "\n" + B.read("flow.css")
    return (B.head(L, "تابع طلبك | فنّي", S["ar"]["meta_desc"], css).replace("<body>", '<body class="flow">')
            + body + B.script(L, js))
