"""Build the GitHub profile: themed SVG assets (light + dark) and README.md.

    python scripts/build.py           # rebuild everything from data/stats.json
    python scripts/build.py --fetch   # refresh data/stats.json from the GitHub API first

--fetch needs a token in GH_TOKEN (or STATS_TOKEN) that can read the owner's
private repos. Only aggregates (weekly counts, language bytes) are written to
data/stats.json, never repo names or commit messages.
"""
import datetime as dt
import json
import math
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
DATA = ROOT / "data" / "stats.json"
OWNER = "swapnil-dhavate"
PORTFOLIO = "https://swapnil-dhavate.netlify.app"
LINKEDIN = "https://www.linkedin.com/in/swapnil-dhavate-7b9486144/"

# Work repos and doc-only repos stay out of the activity numbers.
EXCLUDE_REPOS = {"MES_SUPPORT", "mes_support_help_by_using_files", "weekend-ai-projects", OWNER}

SANS = "'Segoe UI', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif"
MONO = "ui-monospace, 'SF Mono', 'Cascadia Code', Consolas, 'Liberation Mono', monospace"

THEMES = {
    "dark": dict(
        bg="#0B1020", bg2="#141C3A", card="#111831", card2="#0E1530", border="#25304F",
        text="#E8ECF4", muted="#A3AEC2", faint="#6B7894", grid="#1E2746",
        a1="#60A5FA", a2="#A78BFA", a3="#22D3EE", green="#34D399", amber="#FBBF24",
        pink="#F472B6", orb1="#3B82F6", orb2="#8B5CF6", chip="#1A2344", chipText="#C7D2FE",
    ),
    "light": dict(
        bg="#F7F9FF", bg2="#EEF2FF", card="#FFFFFF", card2="#F8FAFF", border="#DDE3F0",
        text="#0F172A", muted="#475569", faint="#94A3B8", grid="#E6EAF5",
        a1="#2563EB", a2="#7C3AED", a3="#0891B2", green="#059669", amber="#D97706",
        pink="#DB2777", orb1="#93C5FD", orb2="#C4B5FD", chip="#EEF2FF", chipText="#3730A3",
    ),
}


# ---------------------------------------------------------------- helpers
def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def tw(s, size, bold=False):
    """Rough text width for system sans fonts; errs on the wide side."""
    w = 0.0
    for ch in str(s):
        if ch in "il.,:;'|!·":
            w += 0.30
        elif ch == " ":
            w += 0.29
        elif ch in "mwMW@":
            w += 0.86
        elif ch.isupper() or ch in "%&$":
            w += 0.67
        elif ch.isdigit():
            w += 0.57
        else:
            w += 0.54
    return w * size * (1.07 if bold else 1.0)


def wrap(text, maxw, size, bold=False):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if tw(trial, size, bold) <= maxw or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def svg(w, h, body, t, extra_css="", title=""):
    css = f"""
    text {{ font-family: {SANS}; }}
    .mono {{ font-family: {MONO}; }}
    .fade {{ animation: fadeUp .8s cubic-bezier(.2,.7,.2,1) both; }}
    @keyframes fadeUp {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
    @keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: .35; }} }}
    @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
    {extra_css}"""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'fill="none" role="img" aria-label="{esc(title)}"><title>{esc(title)}</title>'
        f"<style>{css}</style>{grad_defs(t)}{body}</svg>"
    )


def grad_defs(t):
    return f"""<defs>
  <linearGradient id="gBrand" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{t['a1']}"/><stop offset=".55" stop-color="{t['a2']}"/><stop offset="1" stop-color="{t['a3']}"/>
  </linearGradient>
  <linearGradient id="gBrandV" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{t['a2']}"/><stop offset="1" stop-color="{t['a1']}"/>
  </linearGradient>
  <linearGradient id="gCard" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{t['card']}"/><stop offset="1" stop-color="{t['card2']}"/>
  </linearGradient>
  <pattern id="pDots" width="22" height="22" patternUnits="userSpaceOnUse">
    <circle cx="2" cy="2" r="1.1" fill="{t['grid']}"/>
  </pattern>
</defs>"""


def card_rect(x, y, w, h, t, r=18):
    return (f'<rect x="{x+.5}" y="{y+.5}" width="{w-1}" height="{h-1}" rx="{r}" fill="url(#gCard)" '
            f'stroke="{t["border"]}"/>')


def text(x, y, s, size, fill, weight=400, anchor="start", cls="", extra=""):
    c = f' class="{cls}"' if cls else ""
    return (f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}"{c} {extra}>{esc(s)}</text>')


def chip(x, y, label, t, size=12, color=None, h=24):
    w = tw(label, size) + 20
    fill = t["chip"]
    tc = color or t["chipText"]
    return (f'<rect x="{x}" y="{y}" width="{w:.1f}" height="{h}" rx="{h/2}" fill="{fill}"/>'
            + text(x + 10, y + h / 2 + size * 0.36, label, size, tc, 500)), w


# Simple line icons on a 24x24 grid, drawn with strokes.
ICONS = {
    "app": '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 9h18M7 6.5h.01M10 6.5h.01"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l5 5"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "flame": '<path d="M12 3c1 3.5 5 5.5 5 10a5 5 0 0 1-10 0c0-2.5 1.5-3.5 2-5 1 1 1.5 2 1.5 3 1.5-1.5 2-4.5 1.5-8z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/>',
    "brief": '<rect x="3" y="7" width="18" height="13" rx="2.5"/><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M3 12.5h18"/>',
    "pen": '<path d="M4 20l1-4 11-11 3 3-11 11z"/><path d="M14 7l3 3"/>',
    "film": '<rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>',
    "mic": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"/>',
    "coins": '<ellipse cx="12" cy="6.5" rx="7" ry="3"/><path d="M5 6.5v5c0 1.7 3.1 3 7 3s7-1.3 7-3v-5M5 11.5v5c0 1.7 3.1 3 7 3s7-1.3 7-3v-5"/>',
    "shield": '<path d="M12 3l7.5 3v5.5c0 4.5-3.2 8-7.5 9.5-4.3-1.5-7.5-5-7.5-9.5V6z"/><path d="M9 12l2 2 4-4"/>',
    "home": '<path d="M3.5 11L12 4l8.5 7"/><path d="M6 9.5V20h12V9.5"/><rect x="10" y="14" width="4" height="6"/>',
    "factory": '<path d="M3 20V10l5 3V10l5 3V7l4 2v11z"/><path d="M3 20h18M17 9V4h3v16"/>',
    "doc": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2.5"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "pin": '<path d="M12 21s-6.5-6-6.5-11a6.5 6.5 0 0 1 13 0c0 5-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.3"/>',
}


def icon(name, x, y, size, color, sw=1.8):
    s = size / 24
    return (f'<g transform="translate({x},{y}) scale({s:.4f})" stroke="{color}" stroke-width="{sw/s*s:.2f}" '
            f'stroke-linecap="round" stroke-linejoin="round" fill="none">{ICONS[name]}</g>')


# ---------------------------------------------------------------- content
KPIS = [
    ("7+", "years in manufacturing", "Plant ops, own factory, ERP, MES"),
    ("3", "MES modules specified", "Workshop to Product Owner sign-off"),
    ("+4%", "diketene yield", "Specialty-chemicals plant programme"),
    ("13", "AI projects shipped", "Every one runs at $0 a month"),
]

CAREER = [
    # role, org, start, end (None = now), colour key, note
    ("Trainee Engineer", "Ganesh Fabrierecon", (2019, 6), (2019, 10), "amber", "Beverage plant erection and commissioning"),
    ("Technical Associate", "Laxmi Organic Industries", (2019, 11), (2021, 8), "pink", "Diketene yield +4%, SAP production data"),
    ("Founder & Owner-Operator", "Soelite Foods", (2021, 8), (2023, 6), "green", "Built and ran a 200 kg/day tofu plant"),
    ("Business Analyst, ERP", "JM Enterprises", (2023, 9), (2025, 9), "a1", "Gap report to go-live, Manufacturing & Quality"),
    ("Business Analyst, MES", "Hind Industec", (2025, 9), None, "a2", "Steel MES: capability, routes, conversions"),
    ("AI side projects", "Built with Claude Code", (2026, 7), None, "a3", "13 tools on free tiers, human-approved"),
]

STAGES = [
    ("Discover", "Sit with plant SMEs, clients and the product team. Map how the process really runs.",
     "Process maps · gap analysis"),
    ("Define", "Turn it into rules a developer can build and a tester can check. Prioritise with MoSCoW.",
     "BRD · FRD · user stories + AC"),
    ("Design", "Put a clickable prototype in front of SMEs early, so wrong ideas fail in review, not UAT.",
     "Figma · HTML mock-ups · UML"),
    ("Deliver", "Run sprint ceremonies, triage bugs in Jira, keep stakeholders aligned on scope and dates.",
     "Backlog · sprints · PO sign-off"),
    ("Verify", "Check master data across systems in the browser on the deployed build, before users see it.",
     "Playwright via Claude Code · RTM"),
]

PROJECTS = [
    dict(slug="nursai", name="NursAI Prep", kicker="AI PRODUCT · WEB APP", icon="app", status="live",
         url="https://mock-test-generater-new.vercel.app",
         desc="Timed mock tests with negative marking for nursing exams (DHS/DMER, NCLEX), study tracking and an admin question bank.",
         tech=["React", "TypeScript", "Supabase", "Gemini"], metric=("2", "AI providers, auto fallback")),
    dict(slug="subs", name="Subscription Auditor", kicker="DATA PRODUCT · WEB APP", icon="search", status="live",
         url="https://subscription-auditor-india.streamlit.app",
         desc="Finds forgotten subscriptions in Indian bank statements with testable rules, so no bank data ever goes to AI.",
         tech=["Python", "pandas", "Streamlit"], metric=("0", "bank rows sent to AI")),
    dict(slug="linkbio", name="Link-in-Bio Page", kicker="WEB · ANALYTICS", icon="link", status="live",
         url="https://link-in-bio-27p.pages.dev",
         desc="Self-hosted Linktree alternative with first-party click analytics and AI-written weekly insights.",
         tech=["Cloudflare Pages", "D1", "Chart.js"], metric=("$0", "per month to run")),
    dict(slug="shiplog", name="Public Ship Log", kicker="AUTOMATION · OPEN SOURCE", icon="flame", status="public",
         url="https://swapnil-dhavate.github.io/public-ship-log/",
         desc="Build-streak tracker: logs work from Telegram and GitHub commits, drafts Bluesky posts for approval, publishes a heatmap.",
         tech=["Python", "GitHub Actions", "Pages"], metric=("15m", "sync cycle")),
    dict(slug="chief", name="AI Chief of Staff", kicker="AUTOMATION · DAILY 7 AM", icon="sun", status="private",
         desc="One morning brief on Telegram from Gmail, Calendar, Tasks, Drive and Outlook. Saves drafts, never sends email.",
         tech=["Apps Script", "Gemini", "Power Automate"], metric=("18", "line brief, priority order")),
    dict(slug="jobs", name="Job Alerts + Cover Letters", kicker="AUTOMATION · EVERY 2 HOURS", icon="brief", status="private",
         desc="BA openings from 5 job boards and about 66 career portals, de-duplicated, with tailored cover letters on demand.",
         tech=["Cloudflare Workers", "KV", "Actions"], metric=("~66", "career portals scanned")),
    dict(slug="pulse", name="AI Pulse Engine", kicker="CONTENT · DAILY 9 AM", icon="pen", status="private",
         desc="Daily LinkedIn post drafts with branded AI image cards, sent to Telegram for a YES/NO approval before posting.",
         tech=["Gemini", "Workers", "FLUX"], metric=("YES/NO", "approval gate")),
    dict(slug="shorts", name="YouTube Shorts Pipeline", kicker="MEDIA · DAILY", icon="film", status="private",
         desc="Daily Hindi-narrated Shorts: AI script, TTS voice, AI images and ffmpeg editing, approved by a human first.",
         tech=["Gemini", "Piper TTS", "ffmpeg"], metric=("$0", "production budget")),
    dict(slug="voice", name="Voice Note Idea Catcher", kicker="AI · TELEGRAM BOT", icon="mic", status="private",
         desc="Voice notes from walks become sorted idea lists, with duplicate detection and a weekly digest.",
         tech=["Whisper", "Gemini", "SQLite"], metric=("1/wk", "idea digest")),
    dict(slug="money", name="Money Dashboard", kicker="DATA · DASHBOARD", icon="coins", status="private",
         desc="Income dashboard with AI categorisation. Every total is calculated in code, never by the AI.",
         tech=["Python", "SQLite", "Chart.js"], metric=("3", "fallback tiers")),
    dict(slug="security", name="Security Checker", kicker="DEVSECOPS · CLI", icon="shield", status="private",
         desc="Finds exposed API keys in code and git history before deploy, with masked reports and CI blocking.",
         tech=["gitleaks", "Python", "pre-commit"], metric=("CI", "blocks leaked keys")),
    dict(slug="smarthome", name="Smart Home Agent", kicker="AGENT · IOT", icon="home", status="private",
         desc="Controls a Samsung TV from Telegram, voice or the command line through an AI agent.",
         tech=["Workers", "SmartThings", "Claude"], metric=("3", "ways to control")),
]

TOOLBOX = [
    ("Business analysis", "a1", ["Requirement elicitation", "BRD · FRD · FSD", "Business rules", "Gap analysis",
                                  "Process mapping", "User stories & AC", "RTM", "Data mapping"]),
    ("Agile & delivery", "a2", ["Scrum", "Sprint planning", "MoSCoW", "UAT coordination", "Bug triage",
                                "Stakeholder management", "Jira", "Confluence"]),
    ("Modelling & prototyping", "a3", ["Figma", "draw.io · UML", "MS Visio", "Lucidchart", "Axure RP",
                                       "Balsamiq", "HTML mock-ups"]),
    ("AI in daily BA work", "pink", ["Claude Code", "MCP: Jira · Confluence", "MCP: Figma · draw.io",
                                     "Playwright", "Claude", "ChatGPT", "Gemini"]),
    ("Data & testing", "green", ["Excel", "SQL", "SAP production data", "Playwright checks", "UAT"]),
    ("Built with Claude Code", "amber", ["Python", "React", "Supabase", "Streamlit", "Cloudflare Workers",
                                         "GitHub Actions", "Apps Script", "Telegram API"]),
]

SECTIONS = {
    "impact": ("01", "Impact in numbers", "Results from the plant floor to product teams"),
    "career": ("02", "Career path", "Seven years across every side of manufacturing"),
    "process": ("03", "How I work", "A spec is only done when the system proves it"),
    "projects": ("04", "Things I've built", "Specified by me, built with Claude Code, tested until they work"),
    "activity": ("05", "Build activity", "Live numbers from all my repositories, updated daily"),
    "toolbox": ("06", "Toolbox", "Grouped by the job each tool does"),
}


# ---------------------------------------------------------------- assets
def header(t):
    W, H = 1200, 360
    flow_x = 812
    nodes = [("Plant process", "factory", t["amber"]), ("Business rules", "doc", t["a2"]),
             ("Working software", "app", t["green"])]
    body = [f'<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="26" fill="{t["bg"]}" stroke="{t["border"]}"/>',
            f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="26" fill="url(#pDots)" opacity=".9"/>',
            f'<circle cx="980" cy="70" r="190" fill="url(#rOrb1)" class="orb1"/>',
            f'<circle cx="160" cy="330" r="170" fill="url(#rOrb2)" class="orb2"/>',
            f'<rect x="56" y="58" width="6" height="40" rx="3" fill="url(#gBrandV)" class="fade"/>']
    body.append(text(76, 74, "BUSINESS ANALYST", 14, t["a1"], 700, cls="mono fade", extra='letter-spacing="3"'))
    body.append(text(76, 95, "MES · ERP · MANUFACTURING", 13, t["muted"], 500, cls="mono fade",
                     extra='letter-spacing="2" style="animation-delay:.05s"'))
    body.append(text(54, 168, "Swapnil Dhavate", 60, "url(#gBrand)", 800, cls="fade",
                     extra='letter-spacing="-1.5" style="animation-delay:.15s"'))
    body.append(text(56, 214, "I translate the plant floor into software that works.", 24, t["text"], 500,
                     cls="fade", extra='style="animation-delay:.3s"'))
    body.append(text(56, 244, "Requirements, business rules and prototypes for MES and ERP, checked in the browser.",
                     16, t["muted"], 400, cls="fade", extra='style="animation-delay:.4s"'))
    # Pills
    p1 = "Open to BA · Product Analyst · Functional Consultant roles"
    w1 = tw(p1, 14, True) * .9 + 40
    body.append(f'<g class="fade" style="animation-delay:.55s">'
                f'<rect x="56" y="276" width="{w1:.0f}" height="36" rx="18" fill="{t["card"]}" stroke="{t["border"]}"/>'
                f'<circle cx="76" cy="294" r="5" fill="{t["green"]}" style="animation:pulse 2s ease-in-out infinite"/>'
                f'<circle cx="76" cy="294" r="9" fill="none" stroke="{t["green"]}" opacity=".35"/>'
                + text(90, 299, p1, 14, t["text"], 600) + "</g>")
    p2x = 56 + w1 + 12
    p2 = "Pune, India"
    w2 = tw(p2, 14, True) * .9 + 50
    body.append(f'<g class="fade" style="animation-delay:.65s">'
                f'<rect x="{p2x:.0f}" y="276" width="{w2:.0f}" height="36" rx="18" fill="{t["card"]}" stroke="{t["border"]}"/>'
                + icon("pin", p2x + 13, 285, 18, t["a1"]) + text(p2x + 36, 299, p2, 14, t["text"], 600) + "</g>")
    # Flow on the right: three stacked nodes joined by a rail with travelling dots.
    rail_x = flow_x + 26
    body.append(f'<line x1="{rail_x}" y1="88" x2="{rail_x}" y2="276" stroke="{t["border"]}" stroke-width="2" '
                f'stroke-dasharray="4 6"/>')
    for i, delay in enumerate((0, 1.3)):
        body.append(f'<circle cx="{rail_x}" cy="88" r="4.5" fill="url(#gBrandV)">'
                    f'<animate attributeName="cy" values="88;276" dur="2.6s" begin="{delay}s" repeatCount="indefinite"/>'
                    f'<animate attributeName="opacity" values="0;1;1;0" dur="2.6s" begin="{delay}s" repeatCount="indefinite"/>'
                    f'</circle>')
    for i, (label, ic, col) in enumerate(nodes):
        y = 58 + i * 94
        body.append(f'<g class="fade" style="animation-delay:{.35 + i*.2:.2f}s">'
                    f'<rect x="{flow_x}" y="{y}" width="330" height="60" rx="16" fill="{t["card"]}" stroke="{t["border"]}"/>'
                    f'<rect x="{flow_x + 8}" y="{y + 8}" width="44" height="44" rx="12" fill="{col}" opacity=".14"/>'
                    + icon(ic, flow_x + 18, y + 18, 24, col)
                    + text(flow_x + 66, y + 27, f"STEP 0{i+1}", 11, t["faint"], 700, cls="mono", extra='letter-spacing="1.5"')
                    + text(flow_x + 66, y + 47, label, 18, t["text"], 700)
                    + "</g>")
        if i < 2:
            ay = y + 60 + 17
            body.append(f'<path d="M{flow_x+165} {ay-8} l7 8 l7 -8" stroke="{t["faint"]}" stroke-width="2" '
                        f'stroke-linecap="round" stroke-linejoin="round" fill="none" transform="translate(-7,0)"/>')
    defs = (f'<defs><radialGradient id="rOrb1"><stop offset="0" stop-color="{t["orb1"]}" stop-opacity=".45"/>'
            f'<stop offset="1" stop-color="{t["orb1"]}" stop-opacity="0"/></radialGradient>'
            f'<radialGradient id="rOrb2"><stop offset="0" stop-color="{t["orb2"]}" stop-opacity=".4"/>'
            f'<stop offset="1" stop-color="{t["orb2"]}" stop-opacity="0"/></radialGradient></defs>')
    css = """
    .orb1 { animation: drift1 14s ease-in-out infinite alternate; }
    .orb2 { animation: drift2 16s ease-in-out infinite alternate; }
    @keyframes drift1 { to { transform: translate(-60px, 40px); } }
    @keyframes drift2 { to { transform: translate(70px, -30px); } }"""
    return svg(W, H, defs + "".join(body), t, css,
               "Swapnil Dhavate, Business Analyst for MES and ERP. I translate the plant floor into software that works.")


def section(t, key):
    num, title, sub = SECTIONS[key]
    W, H = 1200, 92
    body = [text(0, 34, num, 15, t["a1"], 700, cls="mono", extra='letter-spacing="2"'),
            f'<rect x="34" y="27" width="40" height="2" rx="1" fill="url(#gBrand)"/>',
            text(0, 72, title, 32, t["text"], 800, extra='letter-spacing="-.6"'),
            text(tw(title, 32, True) + 18, 72, sub, 16, t["muted"], 400)]
    return svg(W, H, "".join(body), t, title=f"{title}. {sub}")


def kpis(t):
    W, H, gap = 1200, 176, 16
    cw = (W - 3 * gap) / 4
    cols = ["a1", "a2", "pink", "green"]
    body = []
    for i, (v, l, s) in enumerate(KPIS):
        x = i * (cw + gap)
        c = t[cols[i]]
        body.append(f'<g class="fade" style="animation-delay:{i*.12:.2f}s">' + card_rect(x, 0, cw, H, t))
        body.append(f'<rect x="{x+24}" y="24" width="28" height="4" rx="2" fill="{c}"/>')
        body.append(text(x + 24, 92, v, 52, c, 800, extra='letter-spacing="-1.5"'))
        body.append(text(x + 24, 124, l, 17, t["text"], 700))
        body.append(text(x + 24, 148, s, 13.5, t["muted"]))
        # tiny decorative bars
        for k in range(5):
            bh = 8 + (k * 7 + i * 5) % 24
            body.append(f'<rect x="{x + cw - 86 + k*12}" y="{70 - bh}" width="7" height="{bh}" rx="2" fill="{c}" '
                        f'opacity="{.18 + k*.12:.2f}"/>')
        body.append("</g>")
    return svg(W, H, "".join(body), t, title="7+ years in manufacturing; 3 MES modules specified; "
               "+4% diketene yield; 13 AI projects at $0 a month")


def ym(y, m):
    return y + (m - 1) / 12


def career(t):
    today = dt.date.today()
    W = 1200
    row_h, top = 58, 64
    H = top + row_h * len(CAREER) + 28
    x0, x1 = 400, 1176
    y_start, y_end = 2019.0, 2027.0
    sx = lambda v: x0 + (v - y_start) / (y_end - y_start) * (x1 - x0)
    body = [card_rect(0, 0, W, H, t, 22)]
    # year grid
    for yr in range(2019, 2028):
        x = sx(yr)
        body.append(f'<line x1="{x:.1f}" y1="{top-14}" x2="{x:.1f}" y2="{H-22}" stroke="{t["grid"]}" stroke-width="1"/>')
        if yr < 2027:
            body.append(text(x + 4, top - 24, str(yr), 12.5, t["faint"], 600, cls="mono"))
    now_v = ym(today.year, today.month) + today.day / 365
    nx = sx(now_v)
    body.append(f'<line x1="{nx:.1f}" y1="{top-14}" x2="{nx:.1f}" y2="{H-22}" stroke="{t["green"]}" stroke-width="1.5" '
                f'stroke-dasharray="3 4"/>')
    body.append(text(nx - 6, top - 24, "NOW", 11.5, t["green"], 700, anchor="end", cls="mono"))
    for i, (role, org, s, e, ck, note) in enumerate(CAREER):
        y = top + i * row_h
        c = t[ck]
        sv = ym(*s)
        ev = ym(*e) + 1 / 12 if e else now_v
        bx, bw = sx(sv), max(sx(ev) - sx(sv), 10)
        d = f'style="animation-delay:{.1 + i*.12:.2f}s"'
        body.append(f'<g class="fade" {d}>')
        body.append(f'<circle cx="34" cy="{y+22}" r="6" fill="{c}"/>')
        body.append(text(52, y + 20, role, 16, t["text"], 700))
        body.append(text(52, y + 40, f"{org} · {note}", 12.5, t["muted"]))
        body.append(f'<rect x="{bx:.1f}" y="{y+8}" width="{bw:.1f}" height="26" rx="8" fill="{c}" opacity=".9">'
                    f'<animate attributeName="width" from="0" to="{bw:.1f}" dur="1s" begin="{.2 + i*.12:.2f}s" fill="freeze" '
                    f'calcMode="spline" keySplines=".2 .7 .2 1" keyTimes="0;1"/></rect>')
        months = round((ev - sv) * 12)
        dur = f"{months} mo" if months < 12 else f"{months/12:.1f} yrs".replace(".0 ", " ")
        if e is None:
            dur += " · now"
        if tw(dur, 12, True) + 16 < bw:
            body.append(text(bx + 10, y + 26, dur, 12, "#FFFFFF", 700))
        elif bx + bw + 8 + tw(dur, 12, True) < x1:
            body.append(text(bx + bw + 8, y + 26, dur, 12, t["muted"], 600))
        else:
            body.append(text(bx - 8, y + 26, dur, 12, t["muted"], 600, anchor="end"))
        body.append("</g>")
    return svg(W, H, "".join(body), t, title="Career timeline: Trainee Engineer 2019, Technical Associate at Laxmi "
               "Organic 2019-2021, Founder of Soelite Foods 2021-2023, Business Analyst ERP 2023-2025, "
               "Business Analyst MES 2025-now, AI side projects 2026-now")


def process(t):
    W, gap = 1200, 18
    cw = (W - 4 * gap) / 5
    H = 256
    cols = ["amber", "a1", "a2", "pink", "green"]
    body = []
    for i, (name, desc, out) in enumerate(STAGES):
        x = i * (cw + gap)
        c = t[cols[i]]
        body.append(f'<g class="fade" style="animation-delay:{i*.12:.2f}s">' + card_rect(x, 0, cw, H, t))
        body.append(f'<circle cx="{x+36}" cy="38" r="16" fill="{c}" opacity=".16"/>')
        body.append(text(x + 36, 44, str(i + 1), 16, c, 800, anchor="middle"))
        body.append(text(x + 62, 44, name, 19, t["text"], 800))
        for j, line in enumerate(wrap(desc, cw - 40, 13.5)):
            body.append(text(x + 20, 84 + j * 20, line, 13.5, t["muted"]))
        body.append(f'<line x1="{x+20}" y1="{H-82}" x2="{x+cw-20}" y2="{H-82}" stroke="{t["border"]}"/>')
        body.append(text(x + 20, H - 60, "OUTPUT", 10.5, c, 700, cls="mono", extra='letter-spacing="1.5"'))
        for j, line in enumerate(wrap(out, cw - 40, 12.5, True)[:2]):
            body.append(text(x + 20, H - 38 + j * 18, line, 12.5, t["text"], 600))
        body.append("</g>")
        if i < 4:
            ax = x + cw + gap / 2
            body.append(f'<circle cx="{ax}" cy="38" r="9" fill="{t["bg"]}" stroke="{t["border"]}"/>'
                        f'<path d="M{ax-2.5} 34 l4 4 l-4 4" stroke="{t["muted"]}" stroke-width="1.8" fill="none" '
                        f'stroke-linecap="round" stroke-linejoin="round"/>')
    return svg(W, H, "".join(body), t, title="How I work: Discover, Define, Design, Deliver, Verify")


def project_card(t, p):
    W, H, PAD = 600, 236, 16
    status = p["status"]
    scol = {"live": t["green"], "public": t["a1"], "private": t["faint"]}[status]
    slabel = {"live": "LIVE DEMO", "public": "OPEN SOURCE", "private": "DEMO ON REQUEST"}[status]
    body = [f'<clipPath id="cc"><rect width="{W}" height="{H}" rx="20"/></clipPath>', card_rect(0, 0, W, H, t, 20),
            f'<rect x="0" y="0" width="{W}" height="4" fill="url(#gBrand)" opacity=".9" clip-path="url(#cc)"/>']
    body.append(f'<rect x="24" y="26" width="48" height="48" rx="14" fill="url(#gBrand)" opacity=".16"/>')
    body.append(icon(p["icon"], 36, 38, 24, t["a1"], 2))
    body.append(text(88, 44, p["kicker"], 11, t["faint"], 700, cls="mono", extra='letter-spacing="1.4"'))
    body.append(text(88, 70, p["name"], 22, t["text"], 800, extra='letter-spacing="-.3"'))
    # status pill, top right
    sw_ = tw(slabel, 10.5, True) * 1.12 + 34
    sx_ = W - 24 - sw_
    body.append(f'<rect x="{sx_:.0f}" y="28" width="{sw_:.0f}" height="24" rx="12" fill="{scol}" opacity=".13"/>')
    if status == "private":
        body.append(icon("lock", sx_ + 9, 33, 14, scol, 2.2))
    else:
        body.append(f'<circle cx="{sx_+16:.0f}" cy="40" r="4" fill="{scol}" style="animation:pulse 2s infinite"/>')
    body.append(text(sx_ + 27, 44, slabel, 10.5, scol, 700, cls="mono", extra='letter-spacing="1"'))
    # description
    desc_w = 412
    for j, line in enumerate(wrap(p["desc"], desc_w, 14.5)[:3]):
        body.append(text(24, 108 + j * 21, line, 14.5, t["muted"]))
    # metric, right column
    mv, ml = p["metric"]
    mx = W - 24
    body.append(f'<line x1="{W-150}" y1="96" x2="{W-150}" y2="168" stroke="{t["border"]}"/>')
    body.append(text(mx, 136, mv, 34 if len(mv) <= 4 else 26, "url(#gBrand)", 800, anchor="end",
                     extra='letter-spacing="-1"'))
    for j, line in enumerate(wrap(ml, 118, 12)[:2]):
        body.append(text(mx, 156 + j * 16, line, 12, t["faint"], 500, anchor="end"))
    # tech chips
    cx = 24
    for tech in p["tech"]:
        g, w = chip(cx, H - 46, tech, t, 12)
        body.append(g)
        cx += w + 8
    return svg(W, H + PAD, "".join(body), t, title=f'{p["name"]}: {p["desc"]}')


def toolbox(t):
    W, gap = 1200, 18
    cw = (W - 2 * gap) / 3
    rows = []
    # pre-compute heights per row so cards in a row match
    layouts = []
    for name, ck, items in TOOLBOX:
        cx, cy, placed = 22, 62, []
        for it in items:
            w = tw(it, 12.5) + 20
            if cx + w > cw - 22:
                cx, cy = 22, cy + 34
            placed.append((cx, cy, it))
            cx += w + 8
        layouts.append((name, ck, placed, cy + 26 + 22))
    body = []
    y = 0
    for r in range(0, len(layouts), 3):
        row = layouts[r:r + 3]
        rh = max(l[3] for l in row)
        for i, (name, ck, placed, _) in enumerate(row):
            x = i * (cw + gap)
            c = t[ck]
            body.append(f'<g class="fade" style="animation-delay:{(r+i)*.08:.2f}s">' + card_rect(x, y, cw, rh, t))
            body.append(f'<rect x="{x+22}" y="{y+24}" width="10" height="10" rx="3" fill="{c}"/>')
            body.append(text(x + 40, y + 34, name, 16, t["text"], 800))
            for (cx, cy, it) in placed:
                g, _ = chip(x + cx, y + cy, it, t, 12.5, h=26)
                body.append(g)
            body.append("</g>")
        y += rh + gap
    H = y - gap
    return svg(W, H, "".join(body), t, title="Toolbox: " + "; ".join(f"{n}: {', '.join(i)}" for n, _, i in TOOLBOX))


def activity(t, st):
    W, H = 1200, 400
    weeks = st["weeks"]
    body = [card_rect(0, 0, 770, H, t, 22), card_rect(790, 0, 410, H, t, 22)]
    # tiles row
    tiles = [(st["human_commits"], "commits", t["a1"]), (st["repos"], "repositories", t["a2"]),
             (st["bot_commits"], "automated runs", t["green"]), (st["live_apps"], "live apps", t["pink"])]
    tw_ = (770 - 48 - 3 * 12) / 4
    for i, (v, l, c) in enumerate(tiles):
        x = 24 + i * (tw_ + 12)
        body.append(f'<rect x="{x:.1f}" y="24" width="{tw_:.1f}" height="74" rx="14" fill="{t["bg2"]}" opacity=".7"/>')
        body.append(text(x + 16, 64, f"{v:,}", 28, c, 800, extra='letter-spacing="-.8"'))
        body.append(text(x + 16, 86, l, 12.5, t["muted"], 500))
    # bar chart
    cx0, cx1, cy0, cy1 = 56, 746, 132, 352
    body.append(text(24, 124, "Commits per week, all repos (private included), bots excluded", 13, t["muted"], 600))
    mx = max([w["n"] for w in weeks] + [1])
    step = 10 if mx > 30 else 5 if mx > 12 else 2
    top = math.ceil(mx / step) * step
    for k in range(0, top + 1, step):
        y = cy1 - k / top * (cy1 - cy0 - 12)
        body.append(f'<line x1="{cx0}" y1="{y:.1f}" x2="{cx1}" y2="{y:.1f}" stroke="{t["grid"]}"/>')
        body.append(text(cx0 - 10, y + 4, str(k), 11, t["faint"], 500, anchor="end", cls="mono"))
    n = len(weeks)
    slot = (cx1 - cx0) / max(n, 1)
    bw = max(min(slot * 0.62, 26), 3)
    last_month = None
    for i, w in enumerate(weeks):
        h = w["n"] / top * (cy1 - cy0 - 12)
        x = cx0 + i * slot + (slot - bw) / 2
        if w["n"]:
            body.append(f'<rect x="{x:.1f}" y="{cy1-h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="{min(4, bw/2):.1f}" '
                        f'fill="url(#gBrandV)"><animate attributeName="height" from="0" to="{h:.1f}" dur=".9s" '
                        f'begin="{i*0.03:.2f}s" fill="freeze"/><animate attributeName="y" from="{cy1}" to="{cy1-h:.1f}" '
                        f'dur=".9s" begin="{i*0.03:.2f}s" fill="freeze"/></rect>')
        else:
            body.append(f'<rect x="{x:.1f}" y="{cy1-2}" width="{bw:.1f}" height="2" rx="1" fill="{t["grid"]}"/>')
        mlabel = dt.date.fromisoformat(w["start"]).strftime("%b")
        if mlabel != last_month:
            body.append(text(x, cy1 + 22, mlabel, 11.5, t["faint"], 600, cls="mono"))
            last_month = mlabel
    body.append(f'<line x1="{cx0}" y1="{cy1}" x2="{cx1}" y2="{cy1}" stroke="{t["border"]}"/>')
    # languages donut
    langs = st["languages"]
    total = sum(l["bytes"] for l in langs) or 1
    ccx, ccy, r, sw = 900, 150, 72, 26
    body.append(text(814, 44, "Languages in my projects", 16, t["text"], 800))
    body.append(text(814, 64, "by code size, generated from my specs", 12.5, t["muted"]))
    circ = 2 * math.pi * r
    off = 0
    palette = [t["amber"], t["a1"], t["green"], t["pink"], t["a2"], t["a3"], t["faint"]]
    for i, l in enumerate(langs):
        frac = l["bytes"] / total
        dash = frac * circ
        body.append(f'<circle cx="{ccx}" cy="{ccy}" r="{r}" stroke="{palette[i % len(palette)]}" stroke-width="{sw}" '
                    f'fill="none" stroke-dasharray="{max(dash-2,0.1):.2f} {circ:.2f}" stroke-dashoffset="{-off:.2f}" '
                    f'transform="rotate(-90 {ccx} {ccy})" class="fade" style="animation-delay:{i*.1:.1f}s"/>')
        off += dash
    body.append(text(ccx, ccy + 2, str(len([l for l in langs if l["name"] != "Other"])), 30, t["text"], 800,
                     anchor="middle"))
    body.append(text(ccx, ccy + 22, "languages", 11.5, t["muted"], 500, anchor="middle"))
    # legend, two columns
    for i, l in enumerate(langs):
        col, row = i % 2, i // 2
        x = 814 + col * 186
        y = 262 + row * 30
        pct = l["bytes"] / total * 100
        body.append(f'<rect x="{x}" y="{y-10}" width="12" height="12" rx="3" fill="{palette[i % len(palette)]}"/>')
        body.append(text(x + 20, y, l["name"], 13.5, t["text"], 600))
        body.append(text(x + 172, y, f"{pct:.0f}%" if pct >= 1 else "<1%", 13, t["muted"], 600, anchor="end", cls="mono"))
    # right column side info next to donut
    body.append(text(1010, 128, f'{st["months"]}', 30, t["a2"], 800))
    body.append(text(1010, 148, "months building", 12.5, t["muted"], 500))
    body.append(text(1010, 190, f'{st["active_weeks"]}', 30, t["a3"], 800))
    body.append(text(1010, 210, "active weeks", 12.5, t["muted"], 500))
    body.append(text(1176, H - 18, f'Updated {st["updated"]} by GitHub Actions', 11, t["faint"], 500,
                     anchor="end", cls="mono"))
    return svg(W, H, "".join(body), t, title=f'Build activity: {st["human_commits"]} commits across '
               f'{st["repos"]} repositories, {st["bot_commits"]} automated runs, {st["live_apps"]} live apps')


def footer(t):
    W, H = 1200, 150
    body = [f'<path d="M0 60 C 200 20, 400 100, 600 60 S 1000 20, 1200 60 L1200 150 L0 150 Z" fill="url(#gBrand)" '
            f'opacity=".12"><animate attributeName="d" dur="9s" repeatCount="indefinite" values="'
            f'M0 60 C 200 20, 400 100, 600 60 S 1000 20, 1200 60 L1200 150 L0 150 Z;'
            f'M0 70 C 200 100, 400 30, 600 70 S 1000 100, 1200 50 L1200 150 L0 150 Z;'
            f'M0 60 C 200 20, 400 100, 600 60 S 1000 20, 1200 60 L1200 150 L0 150 Z"/></path>',
            text(600, 100, "“AI drafts, code checks the numbers, and nothing goes public without approval.”",
                 19, t["text"], 600, anchor="middle", extra='font-style="italic"'),
            text(600, 128, "THE RULE BEHIND EVERY PROJECT HERE", 11, t["muted"], 700, anchor="middle",
                 cls="mono", extra='letter-spacing="2"')]
    return svg(W, H, "".join(body), t,
               title="AI drafts, code checks the numbers, and nothing goes public without approval.")


# ---------------------------------------------------------------- stats
def gh(url, token, data=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "User-Agent": "profile-builder"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read()), r.headers.get("Link", "")


def paged(url, token):
    out = []
    while url:
        page, link = gh(url, token)
        out += page
        url = None
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part[part.find("<") + 1:part.find(">")]
    return out


def is_bot(c):
    login = (c.get("author") or {}).get("login") or ""
    name = c["commit"]["author"]["name"] or ""
    return login.endswith("[bot]") or "bot" in login.lower() or "bot" in name.lower()


def fetch_stats(token):
    repos = [r for r in paged(f"https://api.github.com/user/repos?per_page=100&affiliation=owner", token)
             if r["name"] not in EXCLUDE_REPOS and not r["fork"]]
    human, bots, langs = [], 0, {}
    for r in repos:
        try:
            commits = paged(f"https://api.github.com/repos/{OWNER}/{r['name']}/commits?per_page=100", token)
        except urllib.error.HTTPError:
            commits = []  # empty repository
        for c in commits:
            if is_bot(c):
                bots += 1
            else:
                human.append(c["commit"]["author"]["date"][:10])
        lang, _ = gh(f"https://api.github.com/repos/{OWNER}/{r['name']}/languages", token)
        for k, v in lang.items():
            langs[k] = langs.get(k, 0) + v
    today = dt.date.today()
    first = min(dt.date.fromisoformat(d) for d in human) if human else today
    start = max(first, today - dt.timedelta(weeks=52))
    start -= dt.timedelta(days=start.weekday())
    weeks = []
    w = start
    while w <= today:
        n = sum(1 for d in human if w <= dt.date.fromisoformat(d) < w + dt.timedelta(days=7))
        weeks.append({"start": w.isoformat(), "n": n})
        w += dt.timedelta(days=7)
    top = sorted(langs.items(), key=lambda kv: -kv[1])
    main = [{"name": k, "bytes": v} for k, v in top[:5]]
    rest = sum(v for _, v in top[5:])
    if rest:
        main.append({"name": "Other", "bytes": rest})
    months = (today.year - first.year) * 12 + today.month - first.month + 1
    return {
        "updated": today.isoformat(), "human_commits": len(human), "bot_commits": bots,
        "repos": len(repos), "live_apps": sum(1 for p in PROJECTS if p["status"] in ("live", "public")),
        "months": months, "active_weeks": sum(1 for w in weeks if w["n"]), "weeks": weeks, "languages": main,
    }


# ---------------------------------------------------------------- README
def pic(name, alt, width="100%"):
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">'
            f'<img src="assets/{name}-light.svg" alt="{esc(alt)}" width="{width}"></picture>')


def readme(st):
    def badge(label, msg, color, logo, url):
        return (f'<a href="{url}"><img src="https://img.shields.io/badge/{label}-{msg}-{color}?style=for-the-badge'
                f'&logo={logo}&logoColor=white&labelColor=0B1020" alt="{label}: {msg.replace("%20", " ").replace("--", "-")}"></a>')

    badges = " ".join([
        badge("Portfolio", "swapnil--dhavate.netlify.app", "2563EB", "netlify", PORTFOLIO),
        badge("LinkedIn", "Connect", "0A66C2", "linkedin", LINKEDIN),
        badge("Resume", "PDF", "7C3AED", "readdotcv", f"{PORTFOLIO}/Swapnil_Dhavate_Resume.pdf"),
        badge("Contact", "Say%20hello", "059669", "maildotru", f"{PORTFOLIO}/#contact"),
    ])
    cards = []
    for i in range(0, len(PROJECTS), 2):
        row = []
        for p in PROJECTS[i:i + 2]:
            url = p.get("url") or f"{PORTFOLIO}/#work"
            row.append(f'<a href="{url}">{pic("project-" + p["slug"], p["name"] + ": " + p["desc"], "49%")}</a>')
        cards.append("\n".join(row))
    plain = "\n".join(
        f'| **{p["name"]}** | {p["desc"]} | {", ".join(p["tech"])} | '
        + (f'[Open]({p["url"]})' if p.get("url") else "Demo on request") + " |" for p in PROJECTS)
    return f"""<!-- Generated by scripts/build.py. Edit the script, not this file. -->
<div align="center">

{pic("header", "Swapnil Dhavate, Business Analyst for MES and ERP. I translate the plant floor into software that works.")}

<br/>

{badges}

</div>

<br/>

{pic("section-impact", "01 Impact in numbers")}

{pic("kpis", "7+ years in manufacturing, 3 MES modules specified, +4% diketene yield, 13 AI projects at $0 a month")}

I'm a **Business Analyst for MES and ERP** who has worked on every side of manufacturing: refinery internships, a specialty-chemicals plant, my own tofu factory and now a steel MES. I write the requirements and business rules that turn plant processes into working systems, and I check my work in the browser with Playwright before it reaches UAT.

<br/>

{pic("section-career", "02 Career path")}

{pic("career", "Career timeline from 2019 to now")}

<br/>

{pic("section-process", "03 How I work")}

{pic("process", "Discover, Define, Design, Deliver, Verify")}

<br/>

{pic("section-projects", "04 Things I've built")}

<p align="center">
{(chr(10) + "<br/>" + chr(10)).join(cards)}
</p>

> [!NOTE]
> I write the spec, Claude Code writes the code, and I test it until it works. Source code stays private, so this page is the showcase. Live demos are linked, and I'm happy to walk through any project in an interview.

<details>
<summary><b>Plain-text project list</b></summary>

| Project | What it does | Built with | Link |
|---|---|---|---|
{plain}

</details>

<br/>

{pic("section-activity", "05 Build activity")}

{pic("activity", f"{st['human_commits']} commits across {st['repos']} repositories")}

<br/>

{pic("section-toolbox", "06 Toolbox")}

{pic("toolbox", "Business analysis, agile delivery, prototyping, AI and build tools")}

<br/>

<div align="center">

{pic("footer", "AI drafts, code checks the numbers, and nothing goes public without approval.")}

**Hiring a BA who has run the plant?** [Let's talk →]({PORTFOLIO}/#contact)

</div>
"""


# ---------------------------------------------------------------- main
def main():
    if "--fetch" in sys.argv:
        token = os.environ.get("STATS_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            print("No STATS_TOKEN/GH_TOKEN set; keeping cached stats.")
        else:
            DATA.parent.mkdir(exist_ok=True)
            DATA.write_text(json.dumps(fetch_stats(token), indent=1), encoding="utf-8")
    st = json.loads(DATA.read_text(encoding="utf-8"))
    ASSETS.mkdir(exist_ok=True)
    for name, t in THEMES.items():
        out = {"header": header(t), "kpis": kpis(t), "career": career(t), "process": process(t),
               "toolbox": toolbox(t), "activity": activity(t, st), "footer": footer(t)}
        for key in SECTIONS:
            out["section-" + key] = section(t, key)
        for p in PROJECTS:
            out["project-" + p["slug"]] = project_card(t, p)
        for k, v in out.items():
            (ASSETS / f"{k}-{name}.svg").write_text(v, encoding="utf-8")
    (ROOT / "README.md").write_text(readme(st), encoding="utf-8")
    print(f"Built {len(list(ASSETS.glob('*.svg')))} SVGs and README.md")


if __name__ == "__main__":
    main()
