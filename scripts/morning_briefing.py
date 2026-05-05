#!/usr/bin/env python3
import json, os, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

ROOT            = Path(__file__).resolve().parent.parent
SECRETS_FILE    = ROOT / "configs" / "secrets" / "notion.env"
DROPBOX_AB      = Path.home() / "Dropbox" / "leads_ab"
ANTHROPIC_KEY_F = ROOT / "configs" / "secrets" / "anthropic_key.txt"
CONTEXT_FILE    = ROOT / "configs" / "business_context.json"
NOTION_VERSION  = "2022-06-28"
SPAIN_TZ        = timezone(timedelta(hours=2))
NICHES          = ["builders", "electricians", "plumbers", "roofers", "hvac"]
COUNTRIES       = ["uk", "us", "au", "ca", "ie", "nz"]

def _load_secrets():
    secrets = {}
    try:
        for line in SECRETS_FILE.read_text().splitlines():
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                secrets[k.strip()] = v.strip()
    except Exception as e:
        raise RuntimeError(f"Cannot load secrets from {SECRETS_FILE}: {e}")
    return secrets

_S              = _load_secrets()
TELEGRAM_TOKEN  = _S["TELEGRAM_TOKEN"]
TELEGRAM_CHAT   = _S["TELEGRAM_CHAT_ID"]
NOTION_TOKEN    = _S["NOTION_TOKEN"]
NOTION_DB_ID    = _S["NOTION_LEADS_DB_ID"]

SYSTEM = """You are COMMAND — a tactical AI assistant for a solo operator running cold-outreach campaigns to local businesses.

The user's business context (clients, projects, current strategy, notes) is loaded
from configs/business_context.json and passed to you in the user prompt.

=== COMMAND RULES ===
- Always push toward the MOST CASHFLOW path
- Direct, tactical, no fluff
- Highest leverage action first
- Reference specific clients and real numbers from the context provided
- Think war strategist, not life coach
- Never use markdown, headers, or bold. Plain text only. Max 2 lines per action.
  Always end with a complete sentence."""

def load_context():
    try:
        return json.loads(CONTEXT_FILE.read_text())
    except:
        return {}

def notion_headers():
    return {"Authorization": f"Bearer {NOTION_TOKEN}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION}

def api_req(url, data=None, headers=None):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers or {})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def get_weather():
    # Override via WEATHER_LAT / WEATHER_LON / WEATHER_TZ env vars (or in your secrets file).
    lat = os.environ.get("WEATHER_LAT", "0")
    lon = os.environ.get("WEATHER_LON", "0")
    tz  = os.environ.get("WEATHER_TZ", "UTC")
    if lat == "0" and lon == "0":
        return "Weather disabled (set WEATHER_LAT / WEATHER_LON env vars)"
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m,"
            f"apparent_temperature,weathercode&timezone={urllib.parse.quote(tz)}"
        )
        with urllib.request.urlopen(url, timeout=5) as r:
            d = json.loads(r.read())
        c = d["current"]
        codes = {0:"Clear",1:"Mainly clear",2:"Partly cloudy",3:"Overcast",
                 45:"Foggy",51:"Drizzle",61:"Rain",80:"Showers",95:"Storm"}
        desc = codes.get(c["weathercode"], "")
        return f"{desc} {c['temperature_2m']}C (feels {c['apparent_temperature']}C) humidity {c['relative_humidity_2m']}% wind {c['wind_speed_10m']}km/h"
    except:
        return "Weather unavailable"

def get_notion_stats():
    try:
        url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
        all_results = []
        cursor = None
        while True:
            payload = {"page_size": 100}
            if cursor:
                payload["start_cursor"] = cursor
            data = api_req(url, data=payload, headers=notion_headers())
            all_results.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

        total = len(all_results)
        by_niche = defaultdict(int)
        by_priority = defaultdict(int)
        by_channel = defaultdict(int)
        email_found = 0

        for p in all_results:
            props = p.get("properties", {})
            def sel(key):
                s = props.get(key, {}).get("select")
                return s["name"] if s else ""
            def txt(key):
                t = props.get(key, {}).get("rich_text", [])
                return t[0]["plain_text"] if t else ""
            niche    = sel("Niche") or sel("niche")
            priority = sel("Priority") or sel("priority")
            channel  = sel("Outreach Channel") or sel("outreach_channel")
            email    = sel("Email Found") or txt("email_found") or sel("Email Status")
            if niche:    by_niche[niche.lower()] += 1
            if priority: by_priority[priority.upper()] += 1
            if channel:  by_channel[channel] += 1
            if email and email.lower() not in ("", "none", "false", "no", "not found"):
                email_found += 1

        return {
            "total": total,
            "by_niche": dict(by_niche),
            "by_priority": dict(by_priority),
            "by_channel": dict(by_channel),
            "email_found": email_found,
            "email_rate": round(email_found / total * 100, 1) if total else 0,
        }
    except Exception as e:
        return {"error": str(e), "total": 0}

def get_csv_stats():
    stats = {"total_files": 0, "enriched_files": 0, "layer2_files": 0}
    try:
        for country in COUNTRIES:
            for niche in NICHES:
                p = DROPBOX_AB / country / niche
                if not p.exists(): continue
                files = list(p.glob("*.csv"))
                stats["total_files"]    += len([f for f in files if "_ab.csv" in f.name and "_enriched" not in f.name])
                stats["enriched_files"] += len([f for f in files if "_enriched.csv" in f.name and "layer2" not in f.name])
                stats["layer2_files"]   += len([f for f in files if "layer2" in f.name])
    except: pass
    return stats

def get_tactical_focus(notion, weather, now_str, context):
    try:
        api_key = ANTHROPIC_KEY_F.read_text().strip()
        pri = notion.get("by_priority", {})
        strategy = context.get("strategy", {})
        money = context.get("money_to_collect", [])
        money_str = ", ".join(money) if money else "None outstanding"

        clients_block = "\n".join(
            f"- {name} [{d.get('status','')}]: {d.get('details','')}"
            for name, d in (context.get("clients") or {}).items()
        ) or "None on file"
        projects_block = "\n".join(
            f"- {name}: {detail}"
            for name, detail in (context.get("projects") or {}).items()
        ) or "None on file"

        prompt = f"""Morning briefing data:
Time: {now_str}
Weather: {weather}
Leads in Notion: {notion.get("total", 0)} total - A:{pri.get("A",0)} (no website) - B:{pri.get("B",0)} (weak site)
Email found rate: {notion.get("email_rate", 0)}%

CURRENT STRATEGY:
Market: {strategy.get("primary_market", "US")}
Niche: {strategy.get("niche", "roofers")}
Daily call target: {strategy.get("daily_call_target", 80)}
Offer: {strategy.get("offer", "Free website → $500 → monthly retainer")}
Weekly goal: {strategy.get("goal", "Close 1 US client")}

ACTIVE CLIENTS:
{clients_block}

PROJECTS:
{projects_block}

Money to collect: {money_str}

Give me exactly 3 highest-cashflow actions for today. Sharp, specific, direct. Reference real numbers."""

        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 250,
            "system": SYSTEM,
            "messages": [{"role": "user", "content": prompt}]
        }).encode()

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={"Content-Type": "application/json",
                     "x-api-key": api_key,
                     "anthropic-version": "2023-06-01"}
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        return data["content"][0]["text"].strip()
    except Exception as e:
        return f"Claude error: {e}"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": TELEGRAM_CHAT, "text": message, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def main():
    now     = datetime.now(SPAIN_TZ)
    now_str = now.strftime("%A %d %B %Y, %H:%M")
    print(f"[{now_str}] Running COMMAND briefing...")

    context = load_context()
    weather = get_weather()
    notion  = get_notion_stats()
    csvs    = get_csv_stats()
    focus   = get_tactical_focus(notion, weather, now_str, context)

    pri      = notion.get("by_priority", {})
    ch       = notion.get("by_channel", {})
    top      = sorted(notion.get("by_niche", {}).items(), key=lambda x: -x[1])[:3]
    strategy = context.get("strategy", {})
    money    = context.get("money_to_collect", [])

    lines = [
        "⬡ <b>COMMAND BRIEFING</b>",
        f"📅 {now.strftime('%A %d %B - %H:%M')}",
        f"🌍 {weather}",
        "",
        "📊 <b>LEADS DATABASE</b>",
        f"Total: <b>{notion.get('total', 0)}</b> leads",
    ]
    if pri:
        lines.append("Priority: " + " - ".join(f"{k}:{v}" for k,v in sorted(pri.items())))
    lines.append(f"Email found: <b>{notion.get('email_rate', 0)}%</b>")
    if ch:
        lines.append("Channels: " + " - ".join(f"{k}:{v}" for k,v in sorted(ch.items(), key=lambda x:-x[1])[:4]))
    if top:
        lines.append("Niches: " + " - ".join(f"{k}:{v}" for k,v in top))

    lines += [
        "",
        "🎯 <b>ACTIVE STRATEGY</b>",
        f"Market: {strategy.get('primary_market','US')} - Niche: {strategy.get('niche','roofers')}",
        f"Target: {strategy.get('daily_call_target',80)} calls/day - {strategy.get('goal','')}",
    ]

    if money:
        lines += ["", "💰 <b>MONEY TO COLLECT</b>"]
        for item in money:
            lines.append(f"🔴 {item}")

    if csvs.get("total_files", 0) > 0:
        lines += ["", "📁 <b>DROPBOX (ALL)</b>",
                  f"Raw: {csvs['total_files']} - Enriched: {csvs['enriched_files']} - Layer2: {csvs['layer2_files']}"]

    lines += [
        "",
        "🎯 <b>TODAY'S FOCUS</b>",
        focus,
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "Reply: <i>scrape us roofers</i> · <i>status</i> · <i>ask [question]</i> · <i>update: [note]</i>"
    ]

    result = send_telegram("\n".join(lines))
    print("✅ Sent." if result.get("ok") else f"❌ {result}")

if __name__ == "__main__":
    main()
