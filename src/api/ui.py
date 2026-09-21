"""
The screens. Server-rendered HTML, no build step and no CDN — a demo must not depend
on a bundler or someone else's uptime, and the other person has to be able to change a
page without learning a framework first.

Four views, matching how the work actually happens:

    /            what came in and what needs me           (overview)
    /inbox       every email, filterable                  (triage)
    /case/{id}   one case: the email, the two documents, the decision
    /report      the discrepancy report, for sending on
"""

from __future__ import annotations

import html
from typing import Iterable

from ..models import Category, EmailRecord, EmailResult, Status
from ..report import NO_MISMATCH, REVIEW_EXPLANATION, verdict_line

CATEGORIES = [c.value for c in Category]
STATUSES = [s.value for s in Status]


def e(value) -> str:
    return html.escape("" if value is None else str(value))


def fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value:,}" if isinstance(value, int) else str(value)


# ---------------------------------------------------------------------------
CSS = """
*{box-sizing:border-box}
:root{--bg:#f5f6f8;--pane:#fff;--line:#e4e7eb;--ink:#14181d;--dim:#667085;
 --faint:#98a2b3;--red:#b42318;--redbg:#fef3f2;--amber:#b54708;--amberbg:#fffaeb;
 --green:#067647;--greenbg:#ecfdf3;--blue:#175cd3;--blubg:#eff6ff}
body{margin:0;background:var(--bg);color:var(--ink);
 font:14px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
 -webkit-font-smoothing:antialiased}
a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
code{font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;background:#f1f3f5;
 padding:1px 5px;border-radius:4px}

/* top bar */
.top{background:#101828;color:#fff;position:sticky;top:0;z-index:20}
.top .row{max-width:1260px;margin:0 auto;padding:0 20px;display:flex;align-items:center;
 gap:18px;height:56px}
.brand{font-weight:600;font-size:15px;white-space:nowrap}
.brand small{display:block;font-weight:400;font-size:11px;opacity:.6;letter-spacing:.02em}
nav{display:flex;gap:4px;margin-left:8px}
nav a{color:#cfd6e0;padding:6px 11px;border-radius:6px;font-size:13px;white-space:nowrap}
nav a:hover{background:#1d2939;text-decoration:none}
nav a.on{background:#2a3648;color:#fff}
.runbox{margin-left:auto;display:flex;align-items:center;gap:9px;font-size:12px;
 white-space:nowrap}
@media(max-width:1100px){.runbox>span:nth-of-type(2){display:none}}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block}
.llm{display:flex;align-items:center;gap:7px;padding:4px 10px;border-radius:99px;
 background:#1d2939;font-size:12px;white-space:nowrap}
.llm.on{background:#05603a}
.llm b{font-weight:600}
.sw{width:30px;height:17px;border-radius:99px;background:#475467;position:relative;
 border:none;padding:0;cursor:pointer;flex:none}
.sw::after{content:"";position:absolute;top:2px;left:2px;width:13px;height:13px;
 border-radius:50%;background:#fff;transition:left .15s}
.llm.on .sw{background:#32d583}.llm.on .sw::after{left:15px}
.spend{opacity:.72;font-variant-numeric:tabular-nums}
.dot.ready{background:#32d583}.dot.running{background:#fdb022;animation:p 1s infinite}
.dot.failed{background:#f97066}.dot.idle{background:#667085}
@keyframes p{50%{opacity:.25}}

/* layout */
main{max-width:1180px;margin:0 auto;padding:26px 20px 60px}
h1{font-size:19px;margin:0 0 4px}
.lede{color:var(--dim);margin:0 0 22px;font-size:13px}
h2{font-size:14px;margin:30px 0 10px;letter-spacing:.01em}
.pane{background:var(--pane);border:1px solid var(--line);border-radius:10px;
 overflow:hidden;margin-bottom:14px}
.pane>header{padding:12px 16px;border-bottom:1px solid var(--line);display:flex;
 align-items:center;gap:10px;font-size:13px;font-weight:600}
.pane>.pad{padding:14px 16px}
.cols{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.35fr);gap:14px;
 align-items:start}
@media(max-width:900px){.cols{grid-template-columns:1fr}}

/* stats */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));gap:12px;
 margin-bottom:8px}
.stat{background:var(--pane);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.stat b{display:block;font-size:26px;font-weight:600;line-height:1.15;letter-spacing:-.02em}
.stat span{font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em}
.stat.alert b{color:var(--amber)}.stat.bad b{color:var(--red)}

/* tags */
.tag{font-size:11px;font-weight:600;padding:2px 8px;border-radius:99px;
 letter-spacing:.02em;white-space:nowrap;display:inline-block}
.t-MISMATCH{background:var(--redbg);color:var(--red)}
.t-NEEDS_REVIEW{background:var(--amberbg);color:var(--amber)}
.t-OK{background:var(--greenbg);color:var(--green)}
.cat{font-size:11px;color:var(--dim);white-space:nowrap}
.settled{font-size:11px;color:var(--green);font-weight:600}

/* tables */
table{border-collapse:collapse;width:100%;font-size:13px}
th{text-align:left;font-size:11px;font-weight:500;color:var(--dim);text-transform:uppercase;
 letter-spacing:.05em;padding:9px 16px;border-bottom:1px solid var(--line);background:#fafbfc}
td{padding:9px 16px;border-bottom:1px solid #f0f2f4;vertical-align:top}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover{background:#fafbfc}
/* a whole row is a link: say so with the cursor, and make the hover unmistakable
   rather than the barely-there tint a plain table gets */
tbody tr.row{cursor:pointer}
tbody tr.row:hover{background:#eef4ff}
tbody tr.row:hover td.id a{text-decoration:underline}
tbody tr.row:hover td.sub{color:var(--ink)}
tbody tr.row:focus-within{background:#eef4ff;outline:2px solid var(--blue);outline-offset:-2px}
td.id{font-family:ui-monospace,Menlo,monospace;font-size:12px;white-space:nowrap}
td.sub{color:var(--dim);max-width:400px;overflow:hidden;text-overflow:ellipsis;
 white-space:nowrap}
tr.differs td{background:var(--redbg)}
tr.differs td.f{font-weight:600;color:var(--red)}
td.f{white-space:nowrap}
td.pick{width:38px;padding-right:0}
.why{color:var(--faint);font-size:11px;margin-top:2px}

/* filters */
.filters{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:14px}
.filters select,.filters input{font:inherit;font-size:13px;padding:6px 10px;
 border:1px solid #cfd4dc;border-radius:7px;background:#fff}
.filters input{min-width:220px}
.chip{font-size:12px;padding:5px 11px;border-radius:99px;border:1px solid var(--line);
 background:#fff;color:var(--dim)}
.chip.on{background:#101828;border-color:#101828;color:#fff}

/* buttons */
button,.btn{font:inherit;font-size:13px;padding:7px 14px;border-radius:7px;cursor:pointer;
 border:1px solid #cfd4dc;background:#fff;color:var(--ink)}
button:hover,.btn:hover{background:#f4f5f7;text-decoration:none}
button:disabled{opacity:.5;cursor:default}
.b-red{background:var(--red);border-color:var(--red);color:#fff}
.b-red:hover{background:#96201a}
.b-green{background:var(--green);border-color:var(--green);color:#fff}
.b-green:hover{background:#05603a}
.b-light{background:#1d2939;border-color:#1d2939;color:#fff;font-size:12px;padding:5px 12px}
.b-light:hover{background:#2a3648}
.actions{padding:13px 16px;border-top:1px solid var(--line);background:#fafbfc;
 display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.hint{color:var(--faint);font-size:12px}
.b-amber{background:var(--amber);border-color:var(--amber);color:#fff}
.b-amber:hover{background:#93370d}
a.skip{font-size:13px;color:var(--dim);text-decoration:underline;align-self:center}
.want{margin:4px 0 0 18px;padding:0}
.want li{font-size:13px;line-height:1.7;color:var(--ink)}

/* email pane */
.meta{font-size:12px;color:var(--dim);margin-bottom:10px}
.meta b{color:var(--ink);font-weight:600}
.bodytext{font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;
 word-break:break-word;max-height:330px;overflow:auto;background:#fafbfc;
 border:1px solid var(--line);border-radius:7px;padding:12px;color:#344054}
.att{display:inline-block;font-size:12px;background:var(--blubg);color:var(--blue);
 padding:3px 9px;border-radius:6px;margin:3px 4px 0 0;font-family:ui-monospace,Menlo,monospace}
a.att:hover{background:#dbeafe;text-decoration:none}
.banner{padding:11px 16px;font-size:13px;border-radius:8px;margin-bottom:14px}
.banner.amber{background:var(--amberbg);color:#93370d;border:1px solid #fedf89}
.banner.green{background:var(--greenbg);color:#05603a;border:1px solid #abefc6}
.banner.red{background:var(--redbg);color:#912018;border:1px solid #fecdca}
.empty{color:var(--faint);padding:26px 16px;text-align:center;font-size:13px}
.drop{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:760px){.drop{grid-template-columns:1fr}}
.field{margin-bottom:12px}
.field label{display:block;font-size:12px;color:var(--dim);margin-bottom:5px;
 text-transform:uppercase;letter-spacing:.04em}
.field input[type=file]{font:inherit;font-size:13px;width:100%;padding:9px;
 border:1px dashed #cfd4dc;border-radius:8px;background:#fafbfc}
.field input[type=text],.field textarea{font:inherit;font-size:13px;width:100%;
 padding:8px 10px;border:1px solid #cfd4dc;border-radius:7px}
.field textarea{min-height:64px;resize:vertical}
.note{font-size:12px;color:var(--dim);line-height:1.6}
.md h1,.md h2,.md h3{margin:18px 0 8px}.md table{margin:10px 0}
.md th,.md td{padding:6px 12px}
"""

JS = """
// Nothing here needs a token: the rules require the prototype to be publicly
// accessible and the organizers confirmed that gating the paid actions is not allowed.
// The spending is defended by caching every AI response and by a cumulative ceiling —
// see the note at the top of api/main.py.
async function post(path, body) {
  return fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'},
                      body: body ? JSON.stringify(body) : null});
}

// A list row is a link to its case. The <a> on the id still does the real work — this
// only widens the target, because one small link in the first column did not read as
// "open this" and people could not find their way in.
//
// Three things it must not do: hijack a click on something that is already interactive,
// swallow a middle-click or ctrl-click (those should open a tab), or fire when somebody
// was selecting text.
document.addEventListener('click', (ev) => {
  const row = ev.target.closest('tr.row');
  if (!row) return;
  if (ev.target.closest('a, button, input, label, select, textarea')) return;
  if (ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
  if (window.getSelection && String(window.getSelection())) return;
  location.href = row.dataset.href;
});
document.addEventListener('auxclick', (ev) => {        // middle click opens a tab
  const row = ev.target.closest('tr.row');
  if (!row || ev.button !== 1) return;
  if (ev.target.closest('a, button, input')) return;
  window.open(row.dataset.href, '_blank');
});

async function decide(id, status, back, note) {
  const box = document.getElementById('case-' + id);
  const fields = status === 'MISMATCH'
    ? [...box.querySelectorAll('input.pickfield:checked')].map(c => c.value) : [];
  if (status === 'MISMATCH' && !fields.length) {
    alert('Tick the fields that actually differ, or clear the case as no mismatch.');
    return;
  }
  box.querySelectorAll('button').forEach(b => b.disabled = true);
  // settling a case costs nothing, so it needs no token
  const r = await fetch('/review/' + id, {method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({status: status, defect_fields: fields,
                          reviewer: 'reviewer', note: note || null})});
  if (!r.ok) { alert('Could not save: ' + r.status);
    box.querySelectorAll('button').forEach(b => b.disabled = false); return; }
  location.href = back || location.pathname + location.search;
}

async function toggleLlm(btn) {
  const on = btn.getAttribute('aria-pressed') === 'true';
  btn.disabled = true;
  const r = await post('/settings/llm', {enabled: !on});
  if (r.ok) { location.reload(); }
  else {
    alert('Could not switch: ' + r.status);
    btn.disabled = false;
  }
}

async function runInbox(btn) {
  btn.disabled = true; btn.textContent = 'Processing…';
  const r = await post('/run', null);
  if (r.status === 429) { alert('A run just started — give it a moment.');
    btn.disabled = false; btn.textContent = 'Re-run'; return; }
  location.reload();                       // comes back with data-run="running"
}

// While a run is in flight the page says "processing the inbox…" — so something has to
// notice when it stops. Poll /health rather than reloading on a timer: a blind reload
// loop fights the reader for the scroll position, and one that fires before the run
// lands just starts another one.
//
// This MUST wait for DOMContentLoaded. The script tag is in the head, so at parse time
// document.body is still null; the earlier version tested `document.body.dataset` right
// here, got null, silently armed nothing, and left the banner spinning until somebody
// reloaded by hand.
function watchRun() {
  if (!document.body || document.body.dataset.run !== 'running') return;
  let tries = 0;
  const poll = async () => {
    try {
      const h = await (await fetch('/health', {cache: 'no-store'})).json();
      if (h.run && h.run.status !== 'running') { location.reload(); return; }
    } catch (e) { /* a restarting service refuses connections; keep waiting */ }
    if (++tries < 120) setTimeout(poll, 1500);   // give up after ~3 minutes
    else location.reload();                      // and let the page show the real state
  };
  setTimeout(poll, 1000);
}
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', watchRun);
} else {
  watchRun();
}
"""


# ---------------------------------------------------------------------------
def llm_switch(llm: dict | None) -> str:
    """The Claude on/off switch, in the header of every page.

    AI costs money and the rules do not need it, so it is off unless somebody turns it
    on — here, without a redeploy or an ssh session.

    The figure is CUMULATIVE, from the ledger on disk, not per-process: a restart must
    not appear to reset what has been spent.

    One number, because the header is read at a glance and in front of an audience.
    The ceiling and the cache hits still matter — a warm cache is why a second run is
    free, and a run making zero calls has not done nothing — but they belong in the
    tooltip, not in the strip along the top of every page.
    """
    if llm is None:
        return ""
    if llm.get("cap_reached"):
        return (f'<span class=llm title="the cumulative ${llm.get("cap_usd", 0):.2f} '
                'spend ceiling was reached; raise LLM_SPEND_CAP_USD to continue">'
                'AI <b>capped</b>'
                f'<span class=spend>Spent ${llm.get("total_usd", 0):.2f}</span></span>')
    if not llm["has_key"]:
        return ('<span class=llm title="no ANTHROPIC_API_KEY on this machine">'
                'AI <b>no key</b></span>')
    on = llm["enabled"]
    spend = (f'<span class=spend>Spent ${llm["total_usd"]:.2f}</span>'
             if llm.get("total_usd") else "")
    return (f'<span class="llm {"on" if on else ""}" '
            f'title="{e(llm["model"])} · {llm.get("total_calls", 0)} paid calls, '
            f'{llm.get("cache_hits", 0)} served from cache · '
            f'${llm.get("total_usd", 0):.2f} of a ${llm.get("cap_usd", 0):.2f} ceiling · '
            f'{llm["budget"]}/run · {e(llm["source"])}">'
            f'<button class=sw onclick="toggleLlm(this)" aria-pressed="{str(on).lower()}"'
            f' aria-label="AI fallbacks"></button>'
            f'AI <b>{"on" if on else "off"}</b>{spend}</span>')


def page(title: str, body: str, *, active: str = "", run=None, llm=None) -> str:
    status = getattr(run, "status", "idle")
    if status == "running":
        note = "processing the inbox…"
    elif status == "ready":
        seconds = run.seconds or 0
        note = (f"{run.processed} emails in {seconds:.1f}s"
                + (f" · {run.llm_calls} Claude calls" if run.llm_calls else " · no LLM calls"))
    elif status == "failed":
        note = "last run failed"
    else:
        note = "not run yet"

    def link(href: str, label: str, key: str) -> str:
        return f'<a href="{href}" class="{"on" if active == key else ""}">{label}</a>'

    return f"""<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{e(title)} · SDOC</title><style>{CSS}</style><script>{JS}</script>
<body data-run="{e(status)}">
<div class=top><div class=row>
  <div class=brand>Shipping document verification<small>SI vs draft BL · APRIL operations inbox</small></div>
  <nav>{link('/', 'Overview', 'overview')}{link('/inbox', 'Inbox', 'inbox')}
       {link('/review', 'Needs review', 'review')}{link('/report', 'Report', 'report')}
       {link('/upload', 'Upload new data', 'upload')}</nav>
  <div class=runbox><span class="dot {e(status)}"></span><span>{e(note)}</span>
    {llm_switch(llm)}
    <button class=b-light onclick="runInbox(this)">Re-run</button></div>
</div></div>
<main>{body}</main></body></html>"""


def stat_cards(counts: dict[str, int]) -> str:
    cards = [("emails", "emails in", ""), ("checks", "document checks", ""),
             ("discrepancies", "discrepancies", "bad"), ("review", "need a person", "alert"),
             ("settled", "settled by a person", "")]
    return '<div class=stats>' + "".join(
        f'<div class="stat {cls}"><b>{counts.get(key, 0)}</b><span>{label}</span></div>'
        for key, label, cls in cards) + '</div>'


def row_link(result: EmailResult, email: EmailRecord | None, settled: bool) -> str:
    """One row of a list, clickable anywhere.

    The id keeps a real <a> so middle-click, open-in-new-tab and keyboard navigation
    still work — but `data-href` on the row makes the whole thing a click target,
    because a single small link in the first column does not read as "you can open
    this" and people were not finding their way into a case.
    """
    subject = e(email.subject) if email else ""
    return (f'<tr class=row data-href="/case/{e(result.email_id)}">'
            f'<td class=id><a href="/case/{e(result.email_id)}">{e(result.email_id)}</a></td>'
            f'<td class=sub>{subject}</td>'
            f'<td><span class=cat>{e(result.category.value)}</span></td>'
            f'<td><span class="tag t-{e(result.status.value)}">{e(result.status.value)}</span>'
            f'{" <span class=settled>· settled</span>" if settled else ""}</td>'
            f'<td>{e(verdict_line(result))}</td></tr>')


def table(results: Iterable[EmailResult], emails: dict, resolutions: dict,
          empty: str) -> str:
    rows = "".join(row_link(r, emails.get(r.email_id), r.email_id in resolutions)
                   for r in results)
    if not rows:
        return f'<div class=pane><div class=empty>{e(empty)}</div></div>'
    return ('<div class=pane><table><thead><tr><th>email</th><th>subject</th>'
            '<th>category</th><th>outcome</th><th>what it says</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')


# ---------------------------------------------------------------------------
def overview(store, llm=None) -> str:
    if not store.ready:
        running = store.run.status == "running"
        return page("Overview", f"""
<h1>Shipping document verification</h1>
<p class=lede>Every email in the operations inbox, triaged; every draft Bill of Lading
checked against the Shipping Instruction it should match.</p>
<div class=pane><div class=empty>
  {'Processing the inbox — this page will refresh itself.' if running else
   'Nothing processed yet.'}<br><br>
  <button onclick="runInbox(this)" {'disabled' if running else ''}>Process the inbox</button>
</div></div>""", active="overview", run=store.run, llm=llm)

    counts = store.counts()
    reviews = store.open_reviews()
    mismatches = store.mismatches()
    by_rule = sum(1 for r in store.results.values() if r.decided_by.value == "rule")

    banner = ""
    if reviews:
        banner = (f'<div class="banner amber"><b>{len(reviews)} cases need a person.</b> '
                  f'The pipeline could not decide these on its own — it has put the '
                  f'evidence on each one rather than guessing. '
                  f'<a href="/case/{e(reviews[0].email_id)}">Start with '
                  f'{e(reviews[0].email_id)} →</a></div>')
    elif store.resolutions:
        banner = ('<div class="banner green">Everything that needed a person has been '
                  'settled.</div>')

    return page("Overview", f"""
<h1>Overview</h1>
<p class=lede>{counts['emails']} emails triaged in {store.run.seconds:.1f}s ·
{by_rule}/{counts['emails']} decided by rules, no LLM call ·
{counts['checks']} of them are document checks.</p>
{banner}
{stat_cards(counts)}
<h2>Needs a person</h2>
{table(reviews[:10], store.emails, store.resolutions, 'Nothing is waiting.')}
{f'<p class=lede><a href="/review">See all {len(reviews)} →</a></p>' if len(reviews) > 10 else ''}
<h2>Discrepancies found</h2>
{table(mismatches[:10], store.emails, store.resolutions, NO_MISMATCH)}
{f'<p class=lede><a href="/inbox?status=MISMATCH">See all {len(mismatches)} →</a></p>'
 if len(mismatches) > 10 else ''}
""", active="overview", run=store.run, llm=llm)


def inbox(store, category: str | None, status: str | None, query: str | None,
          page_no: int, per_page: int = 60, llm=None) -> str:
    rows = store.filtered(category, status, query)
    total = len(rows)
    pages = max(1, -(-total // per_page))
    page_no = max(1, min(page_no, pages))
    window = rows[(page_no - 1) * per_page: page_no * per_page]

    def option(value: str, current: str | None, label: str | None = None) -> str:
        sel = " selected" if (current or "") == value else ""
        return f'<option value="{e(value)}"{sel}>{e(label or value or "any")}</option>'

    nav = ""
    if pages > 1:
        def qs(n: int) -> str:
            parts = [f"page={n}"]
            if category:
                parts.append(f"category={e(category)}")
            if status:
                parts.append(f"status={e(status)}")
            if query:
                parts.append(f"q={e(query)}")
            return "/inbox?" + "&amp;".join(parts)
        prev = f'<a class=btn href="{qs(page_no - 1)}">← previous</a>' if page_no > 1 else ""
        nxt = f'<a class=btn href="{qs(page_no + 1)}">next →</a>' if page_no < pages else ""
        nav = (f'<div class=filters style="margin-top:14px">{prev}{nxt}'
               f'<span class=hint>page {page_no} of {pages}</span></div>')

    return page("Inbox", f"""
<h1>Inbox</h1>
<p class=lede>Every email and what the pipeline decided about it. {total} shown.</p>
<form class=filters method=get action=/inbox>
  <input name=q value="{e(query or '')}" placeholder="search id, subject or sender">
  <select name=category onchange="this.form.submit()">
    {option('', category, 'any category')}
    {"".join(option(c, category) for c in CATEGORIES)}</select>
  <select name=status onchange="this.form.submit()">
    {option('', status, 'any outcome')}
    {"".join(option(s, status) for s in STATUSES)}</select>
  <button type=submit>Filter</button>
  <a class=btn href="/inbox">Clear</a>
</form>
{table(window, store.emails, store.resolutions, 'Nothing matches that filter.')}
{nav}
""", active="inbox", run=store.run, llm=llm)


def review_list(store, llm=None) -> str:
    reviews = store.open_reviews()
    settled = [store.results[eid] for eid in sorted(store.resolutions)]
    return page("Needs review", f"""
<h1>Needs a person</h1>
<p class=lede>The pipeline escalates what it cannot decide instead of guessing. Each case
carries the two documents side by side and the reason it stopped.</p>
{table(reviews, store.emails, store.resolutions, 'Nothing is waiting.')}
{'<h2>Settled</h2>' + table(settled, store.emails, store.resolutions, '') if settled else ''}
""", active="review", run=store.run, llm=llm)


def _email_pane(email: EmailRecord | None) -> str:
    if email is None:
        return '<div class=pane><div class=empty>The email record is not loaded.</div></div>'
    # The attachments are links: "escalate with the source evidence" only means
    # something if the reviewer can open the document we read the values out of.
    attachments = "".join(
        f'<a class=att target=_blank href="/attachment/{e(a.split("/")[-1])}">'
        f'{e(a.split("/")[-1])}</a>' for a in email.attachments) or \
        '<span class=hint>no attachments</span>'
    return f"""<div class=pane><header>The email</header><div class=pad>
  <div class=meta><b>From</b> {e(email.sender)}</div>
  <div class=meta><b>Subject</b> {e(email.subject)}</div>
  <div class=meta><b>Attachments</b><br>{attachments}</div>
  <div class=bodytext>{e(email.body)}</div></div></div>"""


# The banner says why we stopped. This says what to do about it. Without it an
# escalation is a dead end: the queue insists a person is needed, the person opens
# the case and finds an empty column.
REVIEW_NEXT_STEP = {
    "missing_attachment":
        "Reply to the sender and ask for the Shipping Instruction and the draft Bill "
        "of Lading. Nothing can be checked until they arrive.",
    "wrong_doc_type":
        "What came in is some other document. Ask the sender for the draft Bill of "
        "Lading itself.",
    "unreadable":
        "Open the attachment on the left. If you can read it, key the values in by "
        "hand; if it is genuinely corrupt, ask the sender to resend it.",
    "missing_value":
        "The field is blank on one side, not different. Check it against the booking, "
        "or ask the sender to fill it in.",
}


def _nothing_to_compare_pane(result: EmailResult, email: EmailRecord | None) -> str:
    """Stands in for the comparison table when there was no pair to compare.

    An email can be escalated before any document is read — nothing attached, or
    nothing readable — and it still lands in somebody's queue. Saying what we
    expected, what actually arrived, and what to do next is the whole content of
    the review in that case.
    """
    arrived = "".join(f'<li>{e(a.split("/")[-1])}</li>'
                      for a in (email.attachments if email else [])) or \
              '<li class=hint>nothing was attached</li>'
    reason = result.review_reason.value if result.review_reason else None
    step = REVIEW_NEXT_STEP.get(reason, "")
    return f"""<div class=pane><header>There is nothing to compare</header><div class=pad>
  <p class=note>This email asks for a draft Bill of Lading to be checked against a
  Shipping Instruction. That pair never reached us, so none of the seven fields
  could be read — this is not a clean result, it is an unanswered question.</p>
  <div class=meta><b>Expected</b>
    <ul class=want><li>Shipping Instruction</li><li>draft Bill of Lading</li></ul></div>
  <div class=meta><b>Arrived</b><ul class=want>{arrived}</ul></div>
  {f'<p class=note><b>What to do:</b> {e(step)}</p>' if step else ''}
  <p class=note>If you already have the documents, you can
  <a href="/upload">upload the pair</a> and the check will run on them.</p>
</div></div>"""


def _comparison_pane(result: EmailResult, actionable: bool) -> str:
    if not result.comparisons:
        return ""
    rows = []
    for row in result.comparisons:
        bad = not row.match
        # Pre-tick only rows where BOTH documents state a value and the two disagree.
        # A row that is blank on one side is not a discrepancy — it is the reason we
        # stopped — and pre-ticking it would walk the reviewer straight into calling a
        # missing value a defect, which is the one confusion this whole system exists
        # to prevent. It stays tickable, in case the reviewer knows better than we do.
        genuinely_differs = bad and row.si_value is not None and row.bl_value is not None
        pick = (f'<td class=pick><input class=pickfield type=checkbox '
                f'value="{e(row.field)}"'
                f'{" checked" if genuinely_differs else ""}></td>') if actionable else ""
        why = f'<div class=why>{e(row.note)}</div>' if row.note else ""
        rows.append(f'<tr class="{"differs" if bad else ""}">{pick}'
                    f'<td class=f>{e(row.field)}</td>'
                    f'<td>{e(fmt(row.si_value))}</td>'
                    f'<td>{e(fmt(row.bl_value))}{why}</td></tr>')
    head = ('<tr>' + ('<th></th>' if actionable else '') +
            '<th>field</th><th>Shipping Instruction</th><th>draft Bill of Lading</th></tr>')
    return (f'<div class=pane><header>The two documents, field by field</header>'
            f'<table><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table></div>')


def case(store, result: EmailResult, back: str = "/", llm=None) -> str:
    email = store.email(result.email_id)
    settled = result.email_id in store.resolutions
    # Whether there are rows to tick — NOT whether the reviewer has anything to do.
    # Conflating the two is what left every missing-attachment case with no buttons
    # under a banner telling the reviewer to review it.
    tickable = bool(result.comparisons)
    open_review = result.status is Status.NEEDS_REVIEW and not settled

    tone = {"MISMATCH": "red", "NEEDS_REVIEW": "amber", "OK": "green"}[result.status.value]
    reason = result.review_reason.value if result.review_reason else None
    detail = f" — {REVIEW_EXPLANATION.get(reason, '')}" if reason else ""
    banner = (f'<div class="banner {tone}"><b>{e(verdict_line(result))}</b>'
              f'{e(detail) if detail and reason not in verdict_line(result) else ""}</div>')

    resolution = store.resolutions.get(result.email_id)
    settled_note = ""
    if resolution:
        settled_note = (f'<div class="banner green">Settled by '
                        f'{e(resolution["reviewer"])} as {e(resolution["status"])}'
                        f'{" on " + e(", ".join(resolution["defect_fields"])) if resolution["defect_fields"] else ""}.'
                        f'</div>')

    actions = ""
    if (tickable and not settled) or open_review:
        eid = e(result.email_id)
        nxt = store.next_open_review(result.email_id)
        target = f"/case/{nxt}" if nxt and nxt != result.email_id else back
        # A plain link, deliberately. Recording a resolution is exactly what takes a
        # case out of the queue, so a button that settles the case cannot honestly be
        # labelled "leave open" — the old one lied, and quietly emptied the queue.
        skip = f'<a class=skip href="{e(target)}">Leave open</a>'
    if tickable and not settled:
        actions = f"""<div class=actions>
  <button class=b-red onclick="decide('{eid}','MISMATCH','{e(target)}')">Confirm discrepancy</button>
  <button class=b-green onclick="decide('{eid}','OK','{e(target)}')">No mismatch</button>
  {skip}
  <span class=hint>tick the rows that really differ, then confirm</span></div>"""
    elif open_review:
        # Nothing to tick, but the case is open and a person is being asked to act,
        # so the two things a person can actually conclude have to be on the screen.
        actions = f"""<div class=actions>
  <button class=b-amber onclick="decide('{eid}','NEEDS_REVIEW','{e(target)}','documents requested from the sender')">Documents requested</button>
  <button class=b-green onclick="decide('{eid}','OK','{e(target)}','no document check needed')">No check needed</button>
  {skip}
  <span class=hint>chasing it clears your queue but keeps the verdict at
  NEEDS_REVIEW — nothing has been checked yet</span></div>"""

    provenance = ""
    if result.classified_by_rule:
        provenance = (f'<div class=pad><span class=hint>Routed to '
                      f'{e(result.category.value)} by <code>{e(result.classified_by_rule)}</code> '
                      f'({e(result.decided_by.value)}).</span></div>')

    return page(result.email_id, f"""
<p class=lede><a href="{e(back)}">← back</a></p>
<h1>{e(result.email_id)} <span class="tag t-{e(result.status.value)}">{e(result.status.value)}</span></h1>
{settled_note}{banner}
<div id="case-{e(result.email_id)}" class=cols>
  <div>{_email_pane(email)}</div>
  <div>{_comparison_pane(result, tickable) or (_nothing_to_compare_pane(result, email) if open_review or result.review_reason else "")}
    <div class=pane>{provenance}{actions if actions else '<div class=pad><span class=hint>Nothing to decide on this one.</span></div>'}</div>
  </div>
</div>""", active="", run=store.run, llm=llm)


def upload_page(store, llm=None, error: str | None = None, notice: str | None = None) -> str:
    from .uploads import ALLOWED_SUFFIXES, MAX_FILE_BYTES

    banner = ""
    if error:
        banner = f'<div class="banner red">{e(error)}</div>'
    elif notice:
        banner = f'<div class="banner green">{e(notice)}</div>'

    formats = ", ".join(sorted(x for x in ALLOWED_SUFFIXES if x != ".json"))
    ai_on = bool(llm and llm.get("enabled"))
    ai_note = ("The AI fallback is <b>on</b>, so a layout the rules do not recognise "
               "goes to Claude." if ai_on else
               "The AI fallback is currently <b>off</b>, so anything the rules cannot "
               "parse will be escalated rather than read by Claude.")

    return page("Upload new data", f"""
<h1>Upload new data</h1>
<p class=lede>Nothing here is written into the bundled dataset, and you can put it back
with one click.</p>
{banner}
<div class=drop>
  <div class=pane>
    <header>Compare one pair</header>
    <form class=pad method=post action="/upload" enctype="multipart/form-data">
      <div class=field>
        <label>Shipping Instruction</label>
        <input type=file name=si accept="{e(formats)}" required>
      </div>
      <div class=field>
        <label>Draft Bill of Lading</label>
        <input type=file name=bl accept="{e(formats)}" required>
      </div>
      <div class=field>
        <label>Email subject (optional)</label>
        <input type=text name=subject placeholder="TO CONFIRM DOCS _ ...">
      </div>
      <div class=field>
        <label>Email body (optional)</label>
        <textarea name=body placeholder="Please check the draft BL against the SI."></textarea>
      </div>
      <button class=b-red type=submit>Compare them</button>
      <p class=note style="margin-top:12px">
        {e(formats)} · up to {MAX_FILE_BYTES // 1024 // 1024} MB each.<br>
        {ai_note}
      </p>
    </form>
  </div>

  <div class=pane>
    <header>Load a whole inbox</header>
    <form class=pad method=post action="/upload/inbox" enctype="multipart/form-data">
      <div class=field>
        <label>A .zip shaped like <code>data/</code></label>
        <input type=file name=archive accept=".zip" required>
      </div>
      <p class=note>
        <code>inbox/email_*.json</code> — each with <code>email_id</code>,
        <code>from</code>, <code>subject</code>, <code>body</code> and
        <code>attachments</code><br>
        <code>attachments/</code> — the files those records point at, named
        <code>&lt;id&gt;_SI.*</code> and <code>&lt;id&gt;_BL.*</code>
      </p>
      <button type=submit>Load and process</button>
    </form>
    <div class=actions>
      <form method=post action="/upload/reset" style="margin:0">
        <button type=submit>Back to the bundled inbox</button>
      </form>
      <span class=hint>currently {store.counts().get("emails", 0)} emails loaded</span>
    </div>
  </div>
</div>

<h2>What happens to an uploaded document</h2>
<div class="pane"><div class=pad><p class=note>
The same code path the bundled inbox takes — no special case. The rules read every label
they recognise, aligning by meaning rather than by header text, so
<code>Load Port</code> and <code>Port of Loading</code> land in the same field. Anything
they cannot parse, or a scan with no text layer, goes to Claude; anything neither can
settle is escalated with the evidence rather than guessed.<br><br>
An answer is cached against the exact bytes of the request, so running the same
documents again is free — but the <b>first</b> pass over anything new is a real call.
</p></div></div>
""", active="upload", run=store.run, llm=llm)


def report_page(store, markdown: str, llm=None) -> str:
    return page("Report", f"""
<h1>Discrepancy report</h1>
<p class=lede>What to send on: every check that found something, and every case a person
still has to settle. <a href="/report.md">Download as Markdown</a> ·
<a href="/submission.json">submission.json</a></p>
<div class="pane md"><div class=pad>{_markdown(markdown)}</div></div>
""", active="report", run=store.run, llm=llm)


def _markdown(text: str) -> str:
    """Just enough Markdown for our own report: headings, tables, bold, italics."""
    import re
    out: list[str] = []
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue                                   # the |---| separator row
            tag = "th" if not in_table else "td"
            if not in_table:
                out.append("<table>")
                in_table = True
            out.append("<tr>" + "".join(f"<{tag}>{_inline(c)}</{tag}>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        if stripped.startswith("### "):
            out.append(f"<h3>{_inline(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            out.append(f"<h2>{_inline(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            out.append(f"<h1>{_inline(stripped[2:])}</h1>")
        elif stripped:
            out.append(f"<p>{_inline(stripped)}</p>")
    if in_table:
        out.append("</table>")
    return "\n".join(out)


def _inline(text: str) -> str:
    import re
    safe = html.escape(text)
    safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
    safe = re.sub(r"`(.+?)`", r"<code>\1</code>", safe)
    safe = re.sub(r"_(.+?)_", r"<i>\1</i>", safe)
    return safe


__all__ = ["page", "llm_switch", "overview", "inbox", "review_list", "case",
           "upload_page", "report_page", "CSS", "JS"]
