#!/usr/bin/env python3
"""
Agentlyfe Operations Dashboard
Access: http://localhost:8080
Auto-refreshes every 60 seconds.
"""

import csv
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template_string, request

ROOT = Path(__file__).resolve().parent.parent
SPAIN_TZ   = timezone(timedelta(hours=2))
COUNTRIES  = ["us", "uk", "au", "ca", "ie", "nz"]
NICHES     = ["builders", "electricians", "plumbers", "roofers", "hvac"]
STATE_FILE   = ROOT / "configs" / "dashboard_state.json"
CONTEXT_FILE = ROOT / "configs" / "business_context.json"
DROPBOX_AB = Path.home() / "Dropbox" / "leads_ab"

app = Flask(__name__)

# ── HELPERS ──────────────────────────────────────────────

def spain_now():
    return datetime.now(SPAIN_TZ)

def today_str():
    return spain_now().strftime("%Y-%m-%d")

def load_state():
    default = {
        "date": today_str(),
        "calisthenics_done": False,
        "calls_made": 0,
        "emails_sent": 0,
        "content_posted": False,
        "briefing_reviewed": False,
        "content_week": {d: False for d in ["mon","tue","wed","thu","fri","sat","sun"]},
    }
    try:
        if STATE_FILE.exists():
            s = json.loads(STATE_FILE.read_text())
            # Auto-reset daily fields at midnight Spain time
            if s.get("date") != today_str():
                s["date"] = today_str()
                s["calisthenics_done"] = False
                s["calls_made"] = 0
                s["emails_sent"] = 0
                s["content_posted"] = False
                s["briefing_reviewed"] = False
                save_state(s)
            merged = {**default, **s}
            merged["content_week"] = {**default["content_week"], **s.get("content_week", {})}
            return merged
    except Exception:
        pass
    return default

def save_state(s):
    STATE_FILE.write_text(json.dumps(s, indent=2))

def load_context():
    try:
        return json.loads(CONTEXT_FILE.read_text())
    except Exception:
        return {}

def get_weather():
    try:
        # Set WEATHER_LAT / WEATHER_LON / WEATHER_LOCATION env vars to enable.
        lat = os.environ.get("WEATHER_LAT")
        lon = os.environ.get("WEATHER_LON")
        label = os.environ.get("WEATHER_LOCATION", "")
        if not (lat and lon):
            return ""
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current_weather": True,
                "temperature_unit": "celsius",
            },
            timeout=5
        )
        if resp.status_code == 200:
            w = resp.json().get("current_weather", {})
            temp = w.get("temperature", "?")
            code = int(w.get("weathercode", 0))
            icons = {0:"☀️",1:"🌤",2:"⛅",3:"☁️",45:"🌫",48:"🌫",
                     51:"🌦",53:"🌦",55:"🌧",61:"🌧",63:"🌧",65:"🌧",
                     71:"🌨",73:"🌨",75:"🌨",80:"🌦",81:"🌦",82:"🌦",
                     95:"⛈",96:"⛈",99:"⛈"}
            icon = icons.get(code, "🌡")
            return f"{icon} {temp}°C{(' · ' + label) if label else ''}"
    except Exception:
        pass
    return ""

def get_master_count(country):
    f = ROOT / "masters" / f"{country}_master.txt"
    if not f.exists():
        return 0
    try:
        return sum(1 for line in f.open() if line.strip())
    except Exception:
        return 0

def get_progress(country):
    f = ROOT / "state" / f"{country}_progress.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text())
    except Exception:
        return {}

def get_latest_csv_stats(country):
    d = ROOT / "outputs" / country
    if not d.exists():
        return None
    csvs = sorted(d.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)
    if not csvs:
        return None
    f = csvs[0]
    counts = {"A+": 0, "A": 0, "B": 0, "C": 0, "total": 0}
    try:
        with f.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                counts["total"] += 1
                p = row.get("priority", "")
                if p in counts:
                    counts[p] += 1
    except Exception:
        pass
    counts["file"] = f.name
    counts["mtime"] = datetime.fromtimestamp(f.stat().st_mtime, SPAIN_TZ)
    return counts

def get_todays_files():
    midnight = spain_now().replace(hour=0, minute=0, second=0, microsecond=0)
    files = []
    for country in COUNTRIES:
        d = ROOT / "outputs" / country
        if not d.exists():
            continue
        for f in d.glob("*.csv"):
            mt = datetime.fromtimestamp(f.stat().st_mtime, SPAIN_TZ)
            if mt >= midnight:
                files.append({"name": f.name, "badge": country.upper(), "time": mt.strftime("%H:%M")})
    if DROPBOX_AB.exists():
        for f in DROPBOX_AB.rglob("*.csv"):
            mt = datetime.fromtimestamp(f.stat().st_mtime, SPAIN_TZ)
            if mt >= midnight:
                files.append({"name": f.name, "badge": "DROPBOX", "time": mt.strftime("%H:%M")})
    files.sort(key=lambda x: x["time"], reverse=True)
    return files[:12]

def build_next_actions(state, progress_all, context):
    actions = []

    # Daily targets
    calls = state.get("calls_made", 0)
    if calls < 80:
        actions.append({"p": "🔴", "label": "HIGH", "text": f"Make {80 - calls} more calls today", "cmd": None})

    emails = state.get("emails_sent", 0)
    if emails < 20:
        actions.append({"p": "🔴", "label": "HIGH", "text": f"Send {20 - emails} more emails today", "cmd": None})

    if not state.get("calisthenics_done"):
        actions.append({"p": "🟠", "label": "DAILY", "text": "Calisthenics not done yet", "cmd": None})

    # Urgent clients
    for name, data in context.get("clients", {}).items():
        if data.get("status") in ("URGENT", "UNPAID", "PENDING_SIGNATURE"):
            label = "URGENT" if data["status"] in ("URGENT","UNPAID") else "CLOSE"
            actions.append({"p": "🟠", "label": label, "text": f"Follow up: {name}", "cmd": None})

    # Scraping needs
    for cc in COUNTRIES:
        p = progress_all.get(cc, {})
        niche_p = p.get("niche_progress", {})
        if not niche_p:
            actions.append({"p": "🔵", "label": "START", "text": f"Start scraping {cc.upper()} — 0 niches done", "cmd": f"scrape {cc} roofers"})
            continue
        for niche, nd in niche_p.items():
            if not nd.get("completed") and nd.get("last_run"):
                try:
                    cfg = json.loads((ROOT / "configs" / f"{cc}.json").read_text())
                    total = len(cfg.get("cities", []))
                    done = len(nd.get("completed_cities", []))
                    if done < total:
                        actions.append({
                            "p": "🟡", "label": "SCRAPE",
                            "text": f"Continue {niche} {cc.upper()} ({done}/{total} cities)",
                            "cmd": f"scrape {cc} {niche}"
                        })
                except Exception:
                    pass

    return actions[:8]

def get_latest_handoff():
    hd = ROOT / "handoff"
    if not hd.exists():
        return None
    files = sorted(hd.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)
    return files[0].name if files else None

def calc_mrr(clients):
    mrr = 0
    for _, data in clients.items():
        if data.get("status") == "ACTIVE":
            m = re.search(r'[€$](\d+)', data.get("details", ""))
            if m:
                mrr += int(m.group(1))
    return mrr

# ── ROUTES ───────────────────────────────────────────────

@app.route("/toggle", methods=["POST"])
def toggle():
    data = request.get_json()
    key = data.get("key", "")
    s = load_state()
    if key.startswith("week_"):
        day = key[5:]
        s["content_week"][day] = not s["content_week"].get(day, False)
    elif key in s and isinstance(s[key], bool):
        s[key] = not s[key]
    save_state(s)
    return jsonify({"ok": True})

@app.route("/count", methods=["POST"])
def count():
    data = request.get_json()
    key = data.get("key")
    val = data.get("value", 0)
    s = load_state()
    if key in ("calls_made", "emails_sent"):
        try:
            s[key] = max(0, int(val))
        except (ValueError, TypeError):
            pass
    save_state(s)
    return jsonify({"ok": True})

@app.route("/")
def index():
    state   = load_state()
    context = load_context()
    weather = get_weather()
    now     = spain_now()
    clients = context.get("clients", {})
    mrr     = calc_mrr(clients)

    countries_data = []
    progress_all   = {}
    for cc in COUNTRIES:
        p  = get_progress(cc)
        progress_all[cc] = p
        mc = get_master_count(cc)
        cs = get_latest_csv_stats(cc)
        niches_done = sum(1 for nd in p.get("niche_progress", {}).values() if nd.get("completed"))
        last_run = None
        for nd in p.get("niche_progress", {}).values():
            lr = nd.get("last_run")
            if lr and (not last_run or lr > last_run):
                last_run = lr
        # per-niche status for dots
        niche_status = {}
        for niche in NICHES:
            nd = p.get("niche_progress", {}).get(niche, {})
            niche_status[niche] = "done" if nd.get("completed") else ("partial" if nd.get("completed_cities") else "none")
        countries_data.append({
            "code": cc.upper(), "cc": cc,
            "master_count": mc,
            "niches_done": niches_done,
            "last_run": last_run[:10] if last_run else "never",
            "csv_stats": cs,
            "niche_status": niche_status,
        })

    today_files  = get_todays_files()
    next_actions = build_next_actions(state, progress_all, context)
    latest_handoff = get_latest_handoff()
    mrr_pct = min(100, int(mrr / 2500 * 100)) if mrr else 0

    return render_template_string(TEMPLATE,
        state=state, context=context, clients=clients, mrr=mrr, mrr_pct=mrr_pct,
        weather=weather, now=now, countries_data=countries_data,
        today_files=today_files, next_actions=next_actions,
        latest_handoff=latest_handoff, NICHES=NICHES,
    )

# ── TEMPLATE ─────────────────────────────────────────────

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>⬡ AGENTLYFE OPS</title>
<style>
:root{--bg:#080808;--bg2:#111;--bg3:#1a1a1a;--border:#242424;--green:#00ff88;--red:#ff4444;--orange:#ff8c00;--yellow:#ffd700;--blue:#4488ff;--grey:#444;--text:#e0e0e0;--dim:#666;--font:'SF Mono','Fira Code',Consolas,monospace}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:var(--font);font-size:13px;min-height:100vh}
a{color:var(--green);text-decoration:none}
/* HEADER */
.hdr{background:var(--bg2);border-bottom:1px solid var(--border);padding:10px 20px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:99}
.logo{font-size:15px;font-weight:700;color:var(--green);letter-spacing:3px}
.hdr-mid{display:flex;gap:16px;align-items:center;color:var(--dim);font-size:12px}
.clock{font-size:17px;font-weight:700}
/* GRID */
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;padding:14px;max-width:1400px;margin:0 auto}
.card{background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:16px}
.card-title{font-size:10px;letter-spacing:2px;color:var(--dim);text-transform:uppercase;margin-bottom:14px;display:flex;justify-content:space-between;align-items:center}
.card-title .badge{color:var(--green);font-size:11px}
.full{grid-column:1/-1}
/* CHECKLIST */
.ck-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.ck{background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:13px 10px;cursor:pointer;text-align:center;transition:.15s all;user-select:none}
.ck:hover{border-color:var(--green)}
.ck.done{background:#001508;border-color:var(--green);color:var(--green)}
.ck.warn{background:#140600;border-color:var(--orange);color:var(--orange)}
.ck-icon{font-size:20px;margin-bottom:5px}
.ck-label{font-size:10px;letter-spacing:1px;text-transform:uppercase;font-weight:700}
.ck-sub{font-size:10px;color:var(--dim);margin-top:3px}
.ck.done .ck-sub{color:#00aa55}
.counter-row{display:flex;align-items:center;justify-content:center;gap:6px;margin:6px 0 2px}
input[type=number]{background:var(--bg);border:1px solid var(--border);color:var(--text);font-family:var(--font);font-size:13px;padding:3px 7px;border-radius:4px;width:56px;text-align:center}
.btn-sm{background:var(--bg3);border:1px solid var(--border);color:var(--dim);font-family:var(--font);font-size:11px;padding:3px 9px;border-radius:4px;cursor:pointer}
.btn-sm:hover{border-color:var(--green);color:var(--green)}
.week-row{display:flex;align-items:center;gap:10px;margin-top:14px;padding-top:12px;border-top:1px solid var(--border)}
.week-lbl{font-size:10px;letter-spacing:1px;text-transform:uppercase;color:var(--dim);white-space:nowrap}
.week-dots{display:flex;gap:5px}
.wd{width:30px;height:30px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;cursor:pointer;border:1px solid var(--border);background:var(--bg3);color:var(--dim)}
.wd:hover{border-color:var(--green)}
.wd.done{background:#001508;border-color:var(--green);color:var(--green)}
/* MRR */
.mrr-num{font-size:34px;font-weight:700;color:var(--green);line-height:1}
.mrr-sub{font-size:11px;color:var(--dim);margin:4px 0 8px}
.pbar{background:var(--bg3);border-radius:3px;height:5px;overflow:hidden;margin-bottom:14px}
.pfill{height:100%;border-radius:3px;transition:width .4s}
.cli-row{display:flex;justify-content:space-between;align-items:center;padding:8px 10px;border-radius:4px;background:var(--bg3);border:1px solid var(--border);margin-bottom:6px}
.cli-name{font-weight:700;font-size:13px}
.cli-detail{font-size:10px;color:var(--dim);margin-top:2px;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sdot{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:6px}
.stag{font-size:9px;padding:2px 7px;border-radius:3px;font-weight:700;white-space:nowrap}
/* ACTIONS */
.act-row{display:flex;align-items:flex-start;gap:8px;padding:8px 10px;border-radius:4px;background:var(--bg3);border:1px solid var(--border);margin-bottom:5px}
.act-p{font-size:14px;flex-shrink:0;padding-top:1px}
.act-lbl{font-size:9px;letter-spacing:1px;text-transform:uppercase;color:var(--dim);white-space:nowrap;margin-top:3px}
.act-txt{flex:1;font-size:12px;line-height:1.4}
.act-cmd{font-size:10px;background:var(--bg);border:1px solid var(--border);padding:3px 7px;border-radius:3px;color:var(--blue);cursor:pointer;white-space:nowrap;flex-shrink:0}
.act-cmd:hover{color:var(--green);border-color:var(--green)}
/* COUNTRIES */
.cc-row{display:grid;grid-template-columns:36px 1fr auto;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)}
.cc-row:last-child{border-bottom:none}
.cc-code{font-weight:700;font-size:12px;color:var(--green);text-align:center}
.cc-bar{background:var(--bg3);border-radius:2px;height:4px;overflow:hidden;margin:4px 0}
.cc-fill{height:100%;border-radius:2px}
.cc-meta{font-size:10px;color:var(--dim);line-height:1.5}
.ndots{display:flex;gap:3px;margin-top:3px}
.nd{width:7px;height:7px;border-radius:50%}
.nd.done{background:var(--green)}
.nd.partial{background:var(--yellow)}
.nd.none{background:var(--grey)}
.cc-count{font-size:13px;font-weight:700;text-align:right}
/* ACTIVITY */
.act-file{display:flex;justify-content:space-between;align-items:center;padding:6px 8px;border-radius:4px;background:var(--bg3);margin-bottom:4px}
.act-fn{font-size:11px;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;margin-right:8px}
.act-badge{font-size:9px;padding:2px 6px;border-radius:3px;background:#001508;color:var(--green);white-space:nowrap}
.act-t{font-size:10px;color:var(--dim);white-space:nowrap;margin-left:6px}
/* HANDOFF */
.ho-file{font-size:11px;background:var(--bg3);border:1px solid var(--border);border-radius:4px;padding:8px 10px;color:var(--green);margin-bottom:10px;word-break:break-all}
.tip{font-size:11px;color:var(--dim);line-height:1.7}
code{color:var(--blue);background:var(--bg3);padding:1px 4px;border-radius:3px;font-family:var(--font)}
code.g{color:var(--green)}
/* COLD CALL */
.cc-setup{font-size:12px;line-height:1.9;color:var(--dim)}
.cc-setup strong{color:var(--text)}
.cc-setup .hl{color:var(--green);font-size:15px;font-weight:700}
.city-list{font-size:11px;color:var(--dim);margin-top:8px;padding-top:8px;border-top:1px solid var(--border);line-height:1.9}
.empty{color:var(--grey);font-style:italic;font-size:11px;padding:6px 0}
@media(max-width:768px){.grid{grid-template-columns:1fr}.full{grid-column:1}.ck-grid{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>

<div class="hdr">
  <div class="logo">⬡ AGENTLYFE</div>
  <div class="hdr-mid">
    <span>{{ weather }}</span>
    <span>Auto-refresh: 60s</span>
  </div>
  <div class="clock">{{ now.strftime('%a %d %b · %H:%M') }}</div>
</div>

<div class="grid">

{# ── DAILY CHECKLIST ── #}
<div class="card full">
  <div class="card-title">Daily Ops Checklist <span class="badge">{{ now.strftime('%d %B %Y') }}</span></div>
  <div class="ck-grid">

    <div class="ck {% if state.calisthenics_done %}done{% else %}warn{% endif %}" onclick="tog('calisthenics_done')">
      <div class="ck-icon">{% if state.calisthenics_done %}✅{% else %}💪{% endif %}</div>
      <div class="ck-label">Calisthenics</div>
      <div class="ck-sub">{% if state.calisthenics_done %}Done ✓{% else %}Not done yet{% endif %}</div>
    </div>

    <div class="ck {% if state.calls_made >= 80 %}done{% elif state.calls_made > 0 %}warn{% endif %}" style="cursor:default">
      <div class="ck-icon">{% if state.calls_made >= 80 %}✅{% else %}📞{% endif %}</div>
      <div class="ck-label">Cold Calls</div>
      <div class="counter-row">
        <input type="number" id="calls_v" value="{{ state.calls_made }}" min="0" max="300">
        <button class="btn-sm" onclick="saveN('calls_made','calls_v')">Save</button>
      </div>
      <div class="ck-sub">{{ state.calls_made }} / 80</div>
    </div>

    <div class="ck {% if state.emails_sent >= 20 %}done{% elif state.emails_sent > 0 %}warn{% endif %}" style="cursor:default">
      <div class="ck-icon">{% if state.emails_sent >= 20 %}✅{% else %}📧{% endif %}</div>
      <div class="ck-label">Cold Emails</div>
      <div class="counter-row">
        <input type="number" id="emails_v" value="{{ state.emails_sent }}" min="0" max="200">
        <button class="btn-sm" onclick="saveN('emails_sent','emails_v')">Save</button>
      </div>
      <div class="ck-sub">{{ state.emails_sent }} / 20</div>
    </div>

    <div class="ck {% if state.content_posted %}done{% endif %}" onclick="tog('content_posted')">
      <div class="ck-icon">{% if state.content_posted %}✅{% else %}🎬{% endif %}</div>
      <div class="ck-label">Content</div>
      <div class="ck-sub">{% if state.content_posted %}Posted ✓{% else %}Post today{% endif %}</div>
    </div>

    <div class="ck {% if state.briefing_reviewed %}done{% endif %}" onclick="tog('briefing_reviewed')">
      <div class="ck-icon">{% if state.briefing_reviewed %}✅{% else %}📋{% endif %}</div>
      <div class="ck-label">Briefing</div>
      <div class="ck-sub">{% if state.briefing_reviewed %}Reviewed ✓{% else %}Review morning brief{% endif %}</div>
    </div>

  </div>
  <div class="week-row">
    <span class="week-lbl">Content week:</span>
    <div class="week-dots">
      {% for day in ['mon','tue','wed','thu','fri','sat','sun'] %}
      <div class="wd {% if state.content_week.get(day) %}done{% endif %}" onclick="tog('week_{{ day }}')" title="{{ day }}">{{ day[0].upper() }}</div>
      {% endfor %}
    </div>
    <span style="font-size:10px;color:var(--dim);margin-left:8px">Target: 3× IG · 1× YT/week</span>
  </div>
</div>

{# ── MRR & CLIENTS ── #}
<div class="card">
  <div class="card-title">Client Pipeline & MRR</div>
  <div class="mrr-num">€{{ mrr }}<span style="font-size:16px;color:var(--dim)">/mo</span></div>
  <div class="mrr-sub">Target: €2,500 retainer · €5,000 total MRR</div>
  <div class="pbar"><div class="pfill" style="width:{{ mrr_pct }}%;background:{% if mrr_pct>=100 %}var(--green){% elif mrr_pct>=50 %}var(--yellow){% else %}var(--orange){% endif %}"></div></div>
  {% set STATUS_COL = {'ACTIVE':'#00ff88','PENDING_SIGNATURE':'#ffd700','URGENT':'#ff4444','PIPELINE':'#ffd700','UNPAID':'#ff8c00','COLD':'#444','WRITE_OFF':'#333','CLOSED':'#333','NEW':'#4488ff'} %}
  {% for name, data in clients.items() %}
  {% set c = STATUS_COL.get(data.status, '#555') %}
  <div class="cli-row">
    <div>
      <div><span class="sdot" style="background:{{c}}"></span><span class="cli-name">{{name}}</span></div>
      <div class="cli-detail">{{data.details[:90]}}{% if data.details|length > 90 %}…{% endif %}</div>
    </div>
    <span class="stag" style="background:{{c}}22;color:{{c}};border:1px solid {{c}}44">{{data.status}}</span>
  </div>
  {% else %}
  <div class="empty">No clients in context</div>
  {% endfor %}
</div>

{# ── NEXT ACTIONS ── #}
<div class="card">
  <div class="card-title">Next Actions Queue</div>
  {% for a in next_actions %}
  <div class="act-row">
    <div style="display:flex;flex-direction:column;align-items:center;gap:2px">
      <div class="act-p">{{a.p}}</div>
      <div class="act-lbl">{{a.label}}</div>
    </div>
    <div class="act-txt">{{a.text}}</div>
    {% if a.cmd %}<div class="act-cmd" onclick="copyCmd('{{a.cmd}}')" title="Click to copy Telegram command">📋 {{a.cmd}}</div>{% endif %}
  </div>
  {% else %}
  <div class="empty">All clear — no pending actions</div>
  {% endfor %}
</div>

{# ── SCRAPE PROGRESS ── #}
<div class="card">
  <div class="card-title">Scrape Progress <span class="badge">{{ countries_data|selectattr('master_count')|list|length }}/6 active</span></div>
  {% for cd in countries_data %}
  {% set pct = (cd.niches_done / 5 * 100)|int %}
  {% set bc = '#00ff88' if pct == 100 else ('#ffd700' if pct > 0 else '#333') %}
  <div class="cc-row">
    <div class="cc-code">{{cd.code}}</div>
    <div>
      <div style="display:flex;justify-content:space-between;font-size:11px">
        <span>{{cd.niches_done}}/5 niches</span>
        <span style="color:var(--dim)">last: {{cd.last_run}}</span>
      </div>
      <div class="cc-bar"><div class="cc-fill" style="width:{{pct}}%;background:{{bc}}"></div></div>
      <div class="ndots">
        {% for niche in NICHES %}
        {% set ns = cd.niche_status.get(niche, 'none') %}
        <div class="nd {{ns}}" title="{{niche}}"></div>
        {% endfor %}
      </div>
      {% if cd.csv_stats %}
      <div class="cc-meta">A+:{{cd.csv_stats['A+']}} A:{{cd.csv_stats['A']}} B:{{cd.csv_stats['B']}} C:{{cd.csv_stats['C']}} · {{cd.csv_stats['file'][:32]}}{% if cd.csv_stats['file']|length > 32 %}…{% endif %}</div>
      {% endif %}
    </div>
    <div class="cc-count" style="color:{% if cd.master_count > 0 %}var(--green){% else %}var(--grey){% endif %}">{{cd.master_count}}<div style="font-size:9px;color:var(--dim);text-align:right">leads</div></div>
  </div>
  {% endfor %}
</div>

{# ── TODAY'S ACTIVITY ── #}
<div class="card">
  <div class="card-title">Today's Activity</div>
  {% if today_files %}
    {% for f in today_files %}
    <div class="act-file">
      <div class="act-fn">{{f.name}}</div>
      <span class="act-badge">{{f.badge}}</span>
      <span class="act-t">{{f.time}}</span>
    </div>
    {% endfor %}
  {% else %}
  <div class="empty">No files modified today yet</div>
  {% endif %}
</div>

{# ── SESSION HANDOFF ── #}
<div class="card">
  <div class="card-title">Session Handoff</div>
  {% if latest_handoff %}
  <div class="ho-file">📄 {{latest_handoff}}</div>
  {% else %}
  <div class="empty" style="margin-bottom:10px">No handoff file yet</div>
  {% endif %}
  <div class="tip">
    Create handoff via Telegram: <code class="g">handoff</code><br>
    Or run directly: <code>python3 scripts/create_handoff.py</code><br>
    Files saved to: <code>handoff/session_*.md</code>
  </div>
</div>

{# ── COLD CALL SETUP ── #}
<div class="card">
  <div class="card-title">Cold Call Setup · Dingtone</div>
  <div class="cc-setup">
    <div>Recommended area code: <span class="hl">919</span></div>
    <div style="font-size:11px;color:var(--dim)">Raleigh + Durham NC — 2 of your 10 target cities</div>
    <div class="city-list">
      <strong>US target cities:</strong><br>
      Richmond VA · Raleigh NC · Greenville SC · Wilmington NC · Savannah GA<br>
      Virginia Beach VA · Knoxville TN · Roanoke VA · Durham NC · Columbia SC
    </div>
  </div>
</div>

</div>{# end grid #}

<script>
async function tog(key) {
  await fetch('/toggle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key})});
  location.reload();
}
async function saveN(key, inputId) {
  const v = document.getElementById(inputId).value;
  await fetch('/count',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key,value:parseInt(v)||0})});
  location.reload();
}
function copyCmd(cmd) {
  if(navigator.clipboard){navigator.clipboard.writeText(cmd).then(()=>showToast('Copied: '+cmd))}
  else{prompt('Copy this Telegram command:',cmd)}
}
function showToast(msg){
  const t=document.createElement('div');
  t.style.cssText='position:fixed;bottom:20px;right:20px;background:#00ff88;color:#000;padding:10px 16px;border-radius:6px;font-family:monospace;font-size:12px;z-index:999';
  t.textContent=msg;document.body.appendChild(t);setTimeout(()=>t.remove(),2500);
}
</script>
</body>
</html>"""

if __name__ == "__main__":
    if not STATE_FILE.exists():
        save_state(load_state())
    print(f"⬡ Dashboard starting on http://0.0.0.0:8080")
    print(f"⬡ Access at: http://localhost:8080")
    app.run(host="0.0.0.0", port=8080, debug=False)
