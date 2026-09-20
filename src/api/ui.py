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
.top .row{max-width:1180px;margin:0 auto;padding:0 24px;display:flex;align-items:center;
 gap:26px;height:56px}
.brand{font-weight:600;font-size:15px;white-space:nowrap}
.brand small{display:block;font-weight:400;font-size:11px;opacity:.6;letter-spacing:.02em}
nav{display:flex;gap:4px;margin-left:8px}
nav a{color:#cfd6e0;padding:6px 12px;border-radius:6px;font-size:13px}
nav a:hover{background:#1d2939;text-decoration:none}
nav a.on{background:#2a3648;color:#fff}
.runbox{margin-left:auto;display:flex;align-items:center;gap:10px;font-size:12px}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block}
.dot.ready{background:#32d583}.dot.running{background:#fdb022;animation:p 1s infinite}
.dot.failed{background:#f97066}.dot.idle{background:#667085}
@keyframes p{50%{opacity:.25}}

/* layout */
main{max-width:1180px;margin:0 auto;padding:26px 24px 60px}
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
.md h1,.md h2,.md h3{margin:18px 0 8px}.md table{margin:10px 0}
.md th,.md td{padding:6px 12px}
"""

JS = """
async function decide(id, status, back) {
  const box = document.getElementById('case-' + id);
  const fields = status === 'MISMATCH'
    ? [...box.querySelectorAll('input.pickfield:checked')].map(c => c.value) : [];
  if (status === 'MISMATCH' && !fields.length) {
    alert('Tick the fields that actually differ, or clear the case as no mismatch.');
    return;
  }
  box.querySelectorAll('button').forEach(b => b.disabled = true);
  const r = await fetch('/review/' + id, {method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({status: status, defect_fields: fields, reviewer: 'reviewer'})});
  if (!r.ok) { alert('Could not save: ' + r.status);
    box.querySelectorAll('button').forEach(b => b.disabled = false); return; }
  location.href = back || location.pathname + location.search;
}
async function runInbox(btn) {
  btn.disabled = true; btn.textContent = 'Processing…';
  await fetch('/run', {method: 'POST'});
  setTimeout(() => location.reload(), 1200);
}
// while a run is in flight, refresh until it lands
if (document.body && document.body.dataset.run === 'running') {
  setTimeout(() => location.reload(), 1500);
}
"""


# ---------------------------------------------------------------------------
def page(title: str, body: str, *, active: str = "", run=None) -> str:
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
       {link('/review', 'Needs review', 'review')}{link('/report', 'Report', 'report')}</nav>
  <div class=runbox><span class="dot {e(status)}"></span><span>{e(note)}</span>
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
    subject = e(email.subject) if email else ""
    return (f'<tr><td class=id><a href="/case/{e(result.email_id)}">{e(result.email_id)}</a></td>'
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
def overview(store) -> str:
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
</div></div>""", active="overview", run=store.run)

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
""", active="overview", run=store.run)


def inbox(store, category: str | None, status: str | None, query: str | None,
          page_no: int, per_page: int = 60) -> str:
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
""", active="inbox", run=store.run)


def review_list(store) -> str:
    reviews = store.open_reviews()
    settled = [store.results[eid] for eid in sorted(store.resolutions)]
    return page("Needs review", f"""
<h1>Needs a person</h1>
<p class=lede>The pipeline escalates what it cannot decide instead of guessing. Each case
carries the two documents side by side and the reason it stopped.</p>
{table(reviews, store.emails, store.resolutions, 'Nothing is waiting.')}
{'<h2>Settled</h2>' + table(settled, store.emails, store.resolutions, '') if settled else ''}
""", active="review", run=store.run)


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


def case(store, result: EmailResult, back: str = "/") -> str:
    email = store.email(result.email_id)
    settled = result.email_id in store.resolutions
    actionable = bool(result.comparisons)

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
    if actionable and not settled:
        eid = e(result.email_id)
        nxt = store.next_open_review(result.email_id)
        target = f"/case/{nxt}" if nxt and nxt != result.email_id else back
        actions = f"""<div class=actions>
  <button class=b-red onclick="decide('{eid}','MISMATCH','{e(target)}')">Confirm discrepancy</button>
  <button class=b-green onclick="decide('{eid}','OK','{e(target)}')">No mismatch</button>
  <button onclick="decide('{eid}','NEEDS_REVIEW','{e(target)}')">Leave open</button>
  <span class=hint>tick the rows that really differ, then confirm</span></div>"""

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
  <div>{_comparison_pane(result, actionable)}
    <div class=pane>{provenance}{actions if actions else '<div class=pad><span class=hint>Nothing to decide on this one.</span></div>'}</div>
  </div>
</div>""", active="", run=store.run)


def report_page(store, markdown: str) -> str:
    return page("Report", f"""
<h1>Discrepancy report</h1>
<p class=lede>What to send on: every check that found something, and every case a person
still has to settle. <a href="/report.md">Download as Markdown</a> ·
<a href="/submission.json">submission.json</a></p>
<div class="pane md"><div class=pad>{_markdown(markdown)}</div></div>
""", active="report", run=store.run)


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


__all__ = ["page", "overview", "inbox", "review_list", "case", "report_page", "CSS", "JS"]
