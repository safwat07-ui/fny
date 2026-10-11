"""Build the public Fanni pages.  Run:  python3 site_src/build.py

Writes self-contained HTML (CSS + JS inlined) to the repo root so the Flask
app keeps serving them exactly as before. Edit copy in data.py, styles in
site.css / book.css / track.css, shared behaviour in common.js.
"""
import html, json, os
from data import S, SERVICES, AREAS, SLOTS, GA_ID, SERVICE_FEE

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
read = lambda f: open(os.path.join(HERE, f), encoding="utf-8").read()
e = html.escape

ICONS = {
    "ac": '<rect x="2.5" y="4.5" width="19" height="8.5" rx="2"/><path d="M6 10h12"/><path d="M7.5 16c.6 1-.6 2 0 3.5M12 16c.6 1-.6 2 0 3.5M16.5 16c.6 1-.6 2 0 3.5"/>',
    "satellite": '<path d="M4.5 8.5l11 11a8 8 0 0 1-11-11z"/><path d="M10 14l3.6-3.6"/><circle cx="14.6" cy="9.4" r="1.4"/><path d="M15.5 4.6a4 4 0 0 1 3.9 3.9M16 1.8a6.8 6.8 0 0 1 6.2 6.2"/>',
    "cctv": '<path d="M2.8 6.2l13.4 3.6-1.6 5.8L1.2 12z"/><path d="M16.2 9.8l4.4-.9.8 3.1-4.4 1.6"/><path d="M8 13.9L7 18.5H3"/><path d="M3 16v5"/>',
    "wifi": '<path d="M2 9a15 15 0 0 1 20 0M5.5 12.6a10 10 0 0 1 13 0M9 16.1a5 5 0 0 1 6 0"/><path d="M12 19.6h.01" stroke-width="2.6"/>',
    "intercom": '<rect x="6" y="2.5" width="12" height="19" rx="2.2"/><rect x="8.5" y="5.5" width="7" height="5.5" rx="1"/><circle cx="12" cy="16" r="2"/>',
    "smart-home": '<path d="M3 11l9-7.5 9 7.5"/><path d="M5.5 9.3V20.5h13V9.3"/><path d="M9.3 14.6a3.8 3.8 0 0 1 5.4 0M10.9 16.8a1.5 1.5 0 0 1 2.2 0"/>',
    "lock": '<rect x="4" y="10.5" width="16" height="10.5" rx="2"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/><path d="M12 15v2"/>',
    "check": '<circle cx="12" cy="12" r="9.5"/><path d="M7.8 12.3l2.8 2.8 5.6-5.8"/>',
    "shield": '<path d="M12 2.5l8 3v6c0 5-3.4 8.6-8 10-4.6-1.4-8-5-8-10v-6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    "id": '<rect x="2.5" y="5" width="19" height="14" rx="2"/><circle cx="8.5" cy="11" r="2.3"/><path d="M5 16.2c.7-1.6 2-2.4 3.5-2.4s2.8.8 3.5 2.4M14.5 10h4M14.5 13.5h3"/>',
    "tool": '<path d="M14.7 6.3a4 4 0 0 0-5.5 5L3 17.5 6.5 21l6.2-6.2a4 4 0 0 0 5-5.5l-2.6 2.6-2.4-.6-.6-2.4z"/>',
    "star": '<path d="M12 3l2.7 5.6 6.1.8-4.5 4.2 1.1 6.1L12 16.8 6.6 19.7l1.1-6.1L3.2 9.4l6.1-.8z"/>',
}
def ic(name, cls="ic"):
    return f'<svg class="{cls}" viewBox="0 0 24 24" aria-hidden="true">{ICONS[name]}</svg>'

WA_ICON = '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20l1.3-3.8A8 8 0 1 1 8 19z"/><path d="M9 9.5c.3 2 2.5 4.6 5 5l1.2-1.4-1.9-1-0.9.9c-.9-.4-1.7-1.2-2.1-2.1l.9-.9-1-1.9z"/></svg>'

FAVICON = ("data:image/svg+xml," + "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
           "%3Crect width='64' height='64' rx='16' fill='%230F5B63'/%3E%3Ctext x='32' y='45' font-family='Arial' "
           "font-size='40' font-weight='900' text-anchor='middle' fill='%23F08A24'%3E%D9%81%3C/text%3E%3C/svg%3E")

def catalog_json():
    out = []
    for s in SERVICES:
        out.append({k: s[k] for k in ("slug", "en", "ar", "short_en", "short_ar", "blurb_en", "blurb_ar")} |
                   {"jobs": [{"id": j[0], "en": j[1], "den": j[2], "price": j[3], "insp": j[4], "ar": j[5], "dar": j[6]}
                             for j in s["jobs"]]})
    return json.dumps(out, ensure_ascii=False)

def money(n, lang):
    return f"{n:,} جنيه" if lang == "ar" else f"EGP {n:,}"

def other(page, lang):
    """Same page in the other language."""
    pairs = {"index": ("index.html", "index-ar.html"), "services": ("services.html", "services-ar.html"),
             "book": ("book.html", "book-ar.html")}
    en, ar = pairs[page]
    return ar if lang == "en" else en

def page_url(page, lang):
    return {"index": "index.html", "services": "services.html", "book": "book.html"}[page].replace(".html", "-ar.html" if lang == "ar" else ".html")

def head(lang, title, desc, css):
    return f"""<!DOCTYPE html>
<html lang="{lang}" dir="{S[lang]['dir']}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:type" content="website">
<meta name="theme-color" content="#0A3B42">
<link rel="icon" href="{FAVICON}">
<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
<script>
window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}
gtag('js',new Date());gtag('config','{GA_ID}');
function track(ev,params){{try{{gtag('event',ev,params||{{}})}}catch(e){{}}}}
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
{css}
</style>
</head>
<body>
"""

def nav(lang, page, minimal=False):
    t = S[lang]
    home = page_url("index", lang)
    links = "" if minimal else f"""
    <nav class="nav-links" aria-label="Main">
      <a href="{page_url('services', lang)}">{t['nav_prices']}</a>
      <a href="{home}#how">{t['nav_how']}</a>
      <a href="track.html?lang={lang}">{t['nav_track']}</a>
    </nav>"""
    book_btn = "" if page == "book" else f'<a class="btn btn-amber" href="{page_url("book", lang)}" data-cta="nav_book">{t["nav_book"]}</a>'
    other_href = other(page, lang) if page in ("index", "services", "book") else f"track.html?lang={'ar' if lang=='en' else 'en'}"
    return f"""<header class="nav">
  <div class="wrap nav-in">
    <a class="logo" href="{home}" aria-label="Fanni home"><b>فنّي</b><span>{t['brand_sub']}</span></a>{links}
    <div class="nav-end">
      <a class="lang" href="{other_href}" id="langSwitch" lang="{'ar' if lang=='en' else 'en'}">{t['other_lang']}</a>
      {book_btn}
    </div>
  </div>
</header>
"""

def footer(lang):
    t = S[lang]
    svc_page = page_url("services", lang)
    svc_links = "".join(f'<a href="{svc_page}#{s["slug"]}">{e(s[lang])}</a>' for s in SERVICES)
    join = "join-ar.html" if lang == "ar" else "join.html"
    return f"""<footer class="foot">
  <div class="wrap">
    <div class="foot-in">
      <div><a class="logo" href="{page_url('index', lang)}"><b>فنّي</b><span>{t['brand_sub']}</span></a><p>{t['foot_line']}</p>
        <a class="support" data-support hidden target="_blank" rel="noopener">{WA_ICON}{t['support']}</a></div>
      <div><h4>{t['foot_services']}</h4>{svc_links}</div>
      <div><h4>{t['foot_company']}</h4>
        <a href="{svc_page}">{t['nav_prices']}</a>
        <a href="{page_url('book', lang)}">{t['nav_book']}</a>
        <a href="track.html?lang={lang}">{t['nav_track']}</a>
        <a href="{join}">{t['foot_join']}</a>
      </div>
    </div>
    <div class="foot-bot"><span>{t['rights']}</span><a href="{other(page_for_footer[0], lang)}" lang="{'ar' if lang=='en' else 'en'}">{t['other_lang']}</a></div>
  </div>
</footer>
"""
page_for_footer = ["index"]

def script(lang, extra):
    common = read("common.js").replace("__T__", json.dumps(S[lang], ensure_ascii=False)).replace("__CAT__", catalog_json())
    return f"<script>\n{common}\n{extra}\n</script>\n</body>\n</html>\n"


# ───────────────────────── homepage ─────────────────────────
def index(lang):
    t = S[lang]; L = lang
    page_for_footer[0] = "index"
    first = SERVICES[0]
    tabs = "".join(
        f'<button type="button" class="svc-tab" data-slug="{s["slug"]}" aria-pressed="{"true" if i==0 else "false"}">'
        f'{ic(s["slug"])}<span>{e(s["short_"+L])}</span></button>' for i, s in enumerate(SERVICES))
    j0 = first["jobs"][0]
    menu = ""
    for s in SERVICES:
        rows = "".join(
            f'<a class="m-row" data-job="{j[0]}" href="{page_url("book", L)}?job={j[0]}">'
            f'<span class="n" data-f="title">{e(j[5] if L=="ar" else j[1])}</span><span class="ld"></span>'
            f'<span class="pr">{"<em>"+t["insp_short"]+"</em>" if j[4] else ""}<span data-f="price">{money(j[3], L)}</span></span></a>'
            for j in s["jobs"][:3])
        n = len(s["jobs"])
        more = t["all_jobs"].format(n=n, svc=s[L])
        menu += f"""<div class="menu-block">
        <h3>{ic(s['slug'])}{e(s[L])}</h3><p class="bl">{e(s['blurb_'+L])}</p>
        {rows}
        <a class="m-more" href="{page_url('services', L)}#{s['slug']}">{e(more)}</a>
      </div>"""
    steps = "".join(f"<li><h3>{e(a)}</h3><p>{e(b)}</p></li>" for a, b in t["how"])
    trust_icons = ["id", "tool", "star"]
    trust = "".join(f"<div>{ic(trust_icons[i])}<h3>{e(a)}</h3><p>{e(b)}</p></div>" for i, (a, b) in enumerate(t["trust"]))
    faq = "".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in t["faq"])
    mock_price = money(280, L)
    body = f"""{nav(L, 'index')}
<main>
<section class="hero">
  <div class="wrap hero-in">
    <div>
      <h1>{t['h1']}</h1>
      <p class="lead">{t['lead']}</p>
      <div class="hero-ctas">
        <a class="btn btn-amber btn-lg" href="{page_url('book', L)}" data-cta="hero_book">{t['nav_book']}</a>
        <a class="btn btn-light btn-lg" href="track.html?lang={L}" data-cta="hero_track">{t['hero_cta2']}</a>
      </div>
      <ul class="promises">
        <li>{ic('lock')}{t['promise1']}</li>
        <li>{ic('check')}{t['promise2']}</li>
        <li>{ic('shield')}{t['promise3']}</li>
      </ul>
    </div>

    <div class="ticket" id="ticket" aria-label="{e(t['tk_title'])}">
      <div class="stamp" id="stamp">{t['stamp']}</div>
      <div class="ticket-head"><h2>{t['tk_title']}</h2></div>
      <div class="svc-tabs" style="--n:{len(SERVICES)}" role="group" aria-label="{e(t['foot_services'])}">{tabs}</div>
      <fieldset class="job-opts" id="jobOpts"><legend class="sr">{t['tk_pick']}</legend></fieldset>
      <div class="tear" aria-hidden="true"></div>
      <div class="rc" aria-live="polite">
        <div class="rc-row"><span class="k">{t['tk_labor']}</span><span class="v num" id="tkLabor">{money(j0[3], L)}</span></div>
        <div class="rc-row"><span class="k">{t['tk_fee']}</span><span class="v num" id="tkFee">{money(SERVICE_FEE, L)}</span></div>
        <div class="rc-total"><span class="k">{t['tk_total']}</span>
          <span class="v">{'' if L=='ar' else '<small>EGP</small> '}<span id="tkTotal" class="num" data-v="{j0[3]+SERVICE_FEE}">{j0[3]+SERVICE_FEE:,}</span>{' <small>جنيه</small>' if L=='ar' else ''}</span></div>
      </div>
      <p class="rc-note" id="tkNote">{t['tk_parts']}</p>
      <a class="btn btn-teal btn-lg btn-block" id="tkBook" href="{page_url('book', L)}?job={j0[0]}" data-cta="ticket_book">{t['tk_book']}</a>
    </div>
  </div>
</section>

<section class="sec" id="how">
  <div class="wrap">
    <div class="sec-head"><h2 class="sec-h">{t['how_h']}</h2><p class="sec-p">{t['how_p']}</p></div>
    <ol class="steps">{steps}</ol>
  </div>
</section>

<section class="sec sec-mist" id="prices">
  <div class="wrap">
    <div class="sec-head"><h2 class="sec-h">{t['prices_h']}</h2><p class="sec-p">{t['prices_p']}</p></div>
    <div class="menu">{menu}</div>
  </div>
</section>

<section class="sec">
  <div class="wrap parts">
    <div>
      <h2 class="sec-h">{t['parts_h']}</h2>
      <p>{t['parts_p']}</p>
      <p>{t['parts_p2']}</p>
    </div>
    <div class="phone" aria-hidden="true"><div class="screen">
      <div class="sc-top"><div><small>{t['mock_hdr']}</small><b class="num">FN-48213</b></div><b>{t['mock_status']}</b></div>
      <div class="sc-card"><div class="sc-steps"><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i><i></i></div></div>
      <div class="sc-card sc-part"><h4>{t['mock_parts']}</h4>
        <div class="row"><span>{t['mock_part']}</span><span class="num">{mock_price}</span></div>
        <div class="sc-btns"><span class="sc-ok">{t['mock_ok']}</span><span class="sc-no">{t['mock_no']}</span></div></div>
      <div class="sc-card"><h4>{t['mock_bill']}</h4>
        <div class="sc-line"><span>{t['tk_labor']}</span><span class="num">{money(150, L)}</span></div>
        <div class="sc-line"><span>{t['tk_fee']}</span><span class="num">{money(25, L)}</span></div>
        <div class="sc-line t"><span>{t['tk_total']}</span><span class="num">{money(175, L)}</span></div></div>
    </div></div>
  </div>
</section>

<section class="sec sec-mist">
  <div class="wrap">
    <div class="sec-head"><h2 class="sec-h">{t['trust_h']}</h2></div>
    <div class="trust">{trust}</div>
  </div>
</section>

<section class="sec faq">
  <div class="wrap faq-grid">
    <h2 class="sec-h">{t['faq_h']}</h2>
    <div>{faq}</div>
  </div>
</section>

<section class="band">
  <div class="wrap band-in">
    <div><h2>{t['tech_h']}</h2><p>{t['tech_p']}</p></div>
    <a class="btn btn-amber btn-lg" href="{'join-ar.html' if L=='ar' else 'join.html'}" data-cta="band_join">{t['tech_cta']}</a>
  </div>
</section>
</main>
{footer(L)}"""
    js = r"""
let curSlug = CAT[0].slug, curJob = null;
const opts = document.getElementById('jobOpts');
function renderJobs(){
  const s = CAT.find(x=>x.slug===curSlug) || CAT[0];
  if(!curJob || !s.jobs.find(j=>j.id===curJob)) curJob = (s.jobs.find(j=>!j.insp)||s.jobs[0]).id;
  opts.innerHTML = '<legend class="sr">'+esc(T.tk_pick)+'</legend>' + s.jobs.map(j=>`
    <label class="job-opt"><input type="radio" name="tkjob" value="${j.id}" ${j.id===curJob?'checked':''}>
      <span class="rd"></span><span class="t">${esc(j.title)}<small>${esc(j.detail)}</small></span>
      <span class="p num">${money(j.price)}</span></label>`).join('');
  update(false);
}
function update(pop){
  const hit = findJob(curJob); if(!hit) return;
  document.getElementById('tkLabor').textContent = money(hit.job.price);
  document.getElementById('tkFee').textContent = money(FEE);
  countTo(document.getElementById('tkTotal'), hit.job.price + FEE);
  document.getElementById('tkNote').textContent = hit.job.insp ? T.tk_insp : T.tk_parts;
  document.getElementById('tkBook').href = PAGE.book + '?job=' + hit.job.id;
  if(pop){ const st=document.getElementById('stamp'); st.classList.remove('pop'); void st.offsetWidth; st.classList.add('pop'); }
}
opts.addEventListener('change', ev=>{ curJob = +ev.target.value; update(true); track('price_preview',{job_id:curJob,service:curSlug,lang:LANG}); });
document.querySelectorAll('.svc-tab').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('.svc-tab').forEach(x=>x.setAttribute('aria-pressed', x===b ? 'true' : 'false'));
  curSlug = b.dataset.slug; curJob = null; renderJobs(); update(true);
}));
renderJobs();
loadCatalog().then(()=>{
  document.querySelectorAll('.svc-tab').forEach(b=>b.hidden = !CAT.find(s=>s.slug===b.dataset.slug));
  renderJobs();
});
"""
    return head(L, t["meta_title"], t["meta_desc"], read("site.css")) + body + script(L, js)


# ───────────────────────── services / price list ─────────────────────────
def services(lang):
    t = S[lang]; L = lang
    page_for_footer[0] = "services"
    jump = "".join(f'<a href="#{s["slug"]}">{ic(s["slug"])}{e(s[L])}</a>' for s in SERVICES)
    blocks = ""
    for s in SERVICES:
        rows = "".join(
            f'<div class="pl-row" data-job="{j[0]}"><div class="n"><span data-f="title">{e(j[5] if L=="ar" else j[1])}</span>'
            f'<small data-f="detail">{e(j[6] if L=="ar" else j[2])}</small></div>'
            f'<div class="pr"><span data-f="price">{money(j[3], L)}</span>{"<em>"+t["insp_short"]+"</em>" if j[4] else ""}</div>'
            f'<a class="btn btn-line" href="{page_url("book", L)}?job={j[0]}" data-cta="pricelist_book">{t["book"]}</a></div>'
            for j in s["jobs"])
        blocks += f"""<section class="pl-block" id="{s['slug']}">
      <div><h2>{ic(s['slug'])}{e(s[L])}</h2><p class="bl">{e(s['blurb_'+L])}</p></div>
      <div>{rows}</div>
    </section>"""
    notes = "".join(f"<div><h3>{e(a)}</h3><p>{e(b)}</p></div>" for a, b in t["svc_notes"])
    body = f"""{nav(L, 'services')}
<main>
<section class="phead">
  <div class="wrap">
    <h1>{t['svc_h1']}</h1>
    <p>{t['svc_lead']}</p>
    <nav class="jump" aria-label="{e(t['foot_services'])}">{jump}</nav>
  </div>
</section>
<section class="sec" style="padding-top:72px">
  <div class="wrap plist">{blocks}</div>
</section>
<section class="sec sec-mist">
  <div class="wrap">
    <div class="sec-head"><h2 class="sec-h">{t['svc_note_h']}</h2></div>
    <div class="notes3">{notes}</div>
  </div>
</section>
<section class="band">
  <div class="wrap band-in">
    <div><h2>{t['tech_h']}</h2><p>{t['tech_p']}</p></div>
    <a class="btn btn-amber btn-lg" href="{'join-ar.html' if L=='ar' else 'join.html'}" data-cta="band_join">{t['tech_cta']}</a>
  </div>
</section>
</main>
{footer(L)}"""
    js = "loadCatalog();"
    return head(L, t["svc_title"], t["svc_lead"], read("site.css")) + body + script(L, js)


from pages_book import book, track   # noqa: E402  (kept in a separate file for size)

if __name__ == "__main__":
    outputs = {
        "index.html": index("en"), "index-ar.html": index("ar"),
        "services.html": services("en"), "services-ar.html": services("ar"),
        "book.html": book("en"), "book-ar.html": book("ar"),
        "track.html": track(),
    }
    for name, content in outputs.items():
        with open(os.path.join(ROOT, name), "w", encoding="utf-8") as f:
            f.write(content)
        print(f"wrote {name:18} {len(content)//1024:4} KB")
