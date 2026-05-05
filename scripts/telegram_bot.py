#!/usr/bin/env python3
"""
COMMAND Telegram Bot
Listens for messages, routes to ops_router, replies with output.
Run as a service: systemctl start openclaw-bot
"""

import json
import subprocess
import time
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent.parent
SECRETS_FILE    = ROOT / "configs" / "secrets" / "notion.env"
SPAIN_TZ        = timezone(timedelta(hours=2))

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
ALLOWED_USER    = int(_S["TELEGRAM_CHAT_ID"])
SCRIPTS         = ROOT / "scripts"
OPS_ROUTER      = SCRIPTS / "ops_router.py"
OFFSET_FILE     = ROOT / "state" / "telegram_offset.txt"

# ── TELEGRAM API ──────────────────────────────────────────
def tg(method, data=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    body = json.dumps(data or {}).encode()
    req = urllib.request.Request(url, data=body,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[TG ERROR] {e}")
        return {}

def send(chat_id, text):
    # Telegram max message length is 4096
    if len(text) > 4000:
        text = text[:4000] + "\n\n... [truncated]"
    tg("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    })

def get_updates(offset=None):
    params = {"timeout": 30, "allowed_updates": ["message"]}
    if offset:
        params["offset"] = offset
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    body = json.dumps(params).encode()
    req = urllib.request.Request(url, data=body,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=35) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[POLL ERROR] {e}")
        return {}

# ── OFFSET PERSISTENCE ────────────────────────────────────
def load_offset():
    try:
        if OFFSET_FILE.exists():
            return int(OFFSET_FILE.read_text().strip())
    except:
        pass
    return None

def save_offset(offset):
    try:
        OFFSET_FILE.write_text(str(offset))
    except:
        pass

# ── COMMAND EXECUTION ─────────────────────────────────────
def run_ops(command: str) -> str:
    try:
        result = subprocess.run(
            ["python3", str(OPS_ROUTER)] + command.split(),
            capture_output=True, text=True, timeout=300
        )
        output = (result.stdout or "").strip()
        error  = (result.stderr or "").strip()

        if output:
            return output
        if error and result.returncode != 0:
            return f"❌ Error:\n{error}"
        return "✅ Done."
    except subprocess.TimeoutExpired:
        return "⏱ Command timed out (5 min limit). Check VPS logs."
    except Exception as e:
        return f"❌ Failed: {e}"

# ── HELP TEXT ─────────────────────────────────────────────
VALID_COUNTRIES = {"uk", "us", "au", "ca", "ie", "nz", "fi"}
VALID_NICHES    = {"builders", "electricians", "plumbers", "roofers", "hvac", "painters", "landscapers", "pest_control", "barbershops"}

HELP = """⬡ <b>COMMAND BOT — OPENCLAW CONTROL</b>

<b>SCRAPING</b>
<code>scrape us roofers</code> — scrape next 3 cities (background)
<code>scrape uk builders</code> — any country/niche combo

<b>NOTION SYNC</b>
<code>sync us notion</code> — sync a country's leads to Notion
<code>sync all notion</code> — sync everything

<b>INTELLIGENCE</b>
<code>ask [question]</code> — ask COMMAND anything
<code>briefing</code> — run morning briefing now

<b>DAILY CHECKLIST</b>
<code>done calisthenics</code> — mark training done
<code>calls 45</code> — update call count (target: 80)
<code>emails 12</code> — update email count (target: 20)
<code>done content</code> — mark content posted
<code>check</code> — show today's checklist

<b>SESSION</b>
<code>handoff</code> — generate session handoff file
<code>dashboard</code> — get dashboard URL

<b>STATUS</b>
<code>status</code> — show lead counts per country
<code>help</code> — show this message

Countries: uk · us · au · ca · ie · nz · fi
Niches: builders · electricians · plumbers · roofers · hvac
Dashboard: http://localhost:8080"""

# ── DASHBOARD STATE HELPERS ───────────────────────────────
_STATE_FILE = ROOT / "configs" / "dashboard_state.json"
_SPAIN_TZ   = timezone(timedelta(hours=2))

def _today_str():
    return datetime.now(_SPAIN_TZ).strftime("%Y-%m-%d")

def _load_dash_state():
    default = {"date": _today_str(), "calisthenics_done": False,
                "calls_made": 0, "emails_sent": 0,
                "content_posted": False, "briefing_reviewed": False,
                "content_week": {d: False for d in ["mon","tue","wed","thu","fri","sat","sun"]}}
    try:
        if _STATE_FILE.exists():
            s = json.loads(_STATE_FILE.read_text())
            if s.get("date") != _today_str():
                s.update({"date": _today_str(), "calisthenics_done": False,
                           "calls_made": 0, "emails_sent": 0,
                           "content_posted": False, "briefing_reviewed": False})
                _STATE_FILE.write_text(json.dumps(s, indent=2))
            return {**default, **s}
    except Exception:
        pass
    return default

def _toggle_state(key):
    try:
        s = _load_dash_state()
        s[key] = not s.get(key, False)
        _STATE_FILE.write_text(json.dumps(s, indent=2))
    except Exception:
        pass

def _set_count(key, value):
    try:
        s = _load_dash_state()
        s[key] = max(0, int(value))
        _STATE_FILE.write_text(json.dumps(s, indent=2))
    except Exception:
        pass

def _get_checklist():
    s = _load_dash_state()
    cal  = "✅" if s.get("calisthenics_done") else "⬜"
    calls = s.get("calls_made", 0)
    emails = s.get("emails_sent", 0)
    c_calls  = "✅" if calls >= 80 else f"🔄 {calls}/80"
    c_emails = "✅" if emails >= 20 else f"🔄 {emails}/20"
    content  = "✅" if s.get("content_posted") else "⬜"
    brief    = "✅" if s.get("briefing_reviewed") else "⬜"
    return (
        f"⬡ <b>TODAY'S CHECKLIST</b>\n\n"
        f"{cal} Calisthenics\n"
        f"{c_calls} Cold calls\n"
        f"{c_emails} Cold emails\n"
        f"{content} Content posted\n"
        f"{brief} Briefing reviewed\n\n"
        f"Dashboard: http://localhost:8080"
    )


# ── STATUS COMMAND ────────────────────────────────────────
def get_status() -> str:
    lines = ["⬡ <b>OPENCLAW STATUS</b>", ""]
    now = datetime.now(SPAIN_TZ).strftime("%d %b %Y · %H:%M")
    lines.append(f"🕐 {now}")
    lines.append("")

    countries = ["uk", "us", "au", "ca", "ie", "nz", "fi"]
    for cc in countries:
        master = ROOT / "masters" / f"{cc}_master.txt"
        progress = ROOT / "state" / f"{cc}_progress.json"
        config = ROOT / "configs" / f"{cc}.json"

        if not config.exists():
            lines.append(f"🔴 {cc.upper()} — no config")
            continue

        lead_count = 0
        if master.exists():
            try:
                lead_count = sum(1 for _ in master.open() if _.strip())
            except:
                pass

        completed = 0
        total_niches = 0
        if progress.exists():
            try:
                p = json.loads(progress.read_text())
                niche_progress = p.get("niche_progress", {})
                total_niches = len(niche_progress)
                for niche_data in niche_progress.values():
                    if niche_data.get("completed"):
                        completed += 1
            except:
                pass

        icon = "✅" if (total_niches > 0 and completed == total_niches) else ("🔄" if completed > 0 else "⏳")
        lines.append(f"{icon} {cc.upper()} — {lead_count} leads · {completed}/{total_niches} niches done")

    return "\n".join(lines)

# ── MESSAGE HANDLER ───────────────────────────────────────
def handle(chat_id, user_id, text):
    # Security — only respond to you
    if user_id != ALLOWED_USER:
        send(chat_id, "⛔ Unauthorized.")
        return

    text = text.strip()
    lower = text.lower()

    print(f"[{datetime.now(SPAIN_TZ).strftime('%H:%M:%S')}] CMD: {text}")

    # ── HELP ──
    if lower in ("help", "/help", "/start"):
        send(chat_id, HELP)
        return

    # ── STATUS ──
    if lower in ("status", "/status"):
        send(chat_id, get_status())
        return

    # ── DASHBOARD CHECKLIST ──
    if lower in ("done calisthenics", "calisthenics done", "done cal", "cal done"):
        _toggle_state("calisthenics_done")
        send(chat_id, "💪 Calisthenics marked done. Dashboard updated.")
        return

    if lower.startswith("calls "):
        try:
            n = int(lower.split()[1])
            _set_count("calls_made", n)
            left = max(0, 80 - n)
            send(chat_id, f"📞 Calls updated: {n}/80. {left} to go." if left > 0 else f"📞 Calls done: {n}/80. Target hit! ✅")
        except (IndexError, ValueError):
            send(chat_id, "Usage: <code>calls 45</code>")
        return

    if lower.startswith("emails "):
        try:
            n = int(lower.split()[1])
            _set_count("emails_sent", n)
            left = max(0, 20 - n)
            send(chat_id, f"📧 Emails updated: {n}/20. {left} to go." if left > 0 else f"📧 Emails done: {n}/20. Target hit! ✅")
        except (IndexError, ValueError):
            send(chat_id, "Usage: <code>emails 15</code>")
        return

    if lower in ("done content", "content done", "posted"):
        _toggle_state("content_posted")
        send(chat_id, "🎬 Content marked posted. Dashboard updated.")
        return

    if lower in ("check", "checklist", "/check"):
        send(chat_id, _get_checklist())
        return

    # ── SESSION HANDOFF ──
    if lower in ("handoff", "/handoff"):
        send(chat_id, "⬡ Generating session handoff...")
        try:
            result = subprocess.run(
                ["python3", str(SCRIPTS / "create_handoff.py")],
                capture_output=True, text=True, timeout=30
            )
            output = (result.stdout or "").strip()
            send(chat_id, f"✅ {output}" if output else "✅ Handoff created. Check handoff/ folder.")
        except Exception as e:
            send(chat_id, f"❌ Handoff failed: {e}")
        return

    # ── DASHBOARD URL ──
    if lower in ("dashboard", "/dashboard"):
        send(chat_id, "⬡ <b>Dashboard</b>\nhttp://localhost:8080\nAuto-refreshes every 60s.")
        return

    # ── BRIEFING ──
    if lower in ("briefing", "/briefing"):
        send(chat_id, "⬡ Running briefing...")
        result = run_ops(f"ask run morning briefing")
        # Run actual briefing script directly
        try:
            subprocess.Popen(
                ["python3", str(SCRIPTS / "morning_briefing.py")],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            send(chat_id, "⬡ Briefing sent.")
        except Exception as e:
            send(chat_id, f"❌ {e}")
        return

    # ── SCRAPE ──
    if lower.startswith("scrape "):
        parts = lower.split()
        if len(parts) >= 3:
            country, niche = parts[1], parts[2]
            if country not in VALID_COUNTRIES:
                send(chat_id, f"❌ Unknown country: <code>{country}</code>\nUse: uk · us · au · ca · ie · nz · fi")
                return
            if niche not in VALID_NICHES:
                send(chat_id, f"❌ Unknown niche: <code>{niche}</code>\nUse: builders · electricians · plumbers · roofers · hvac")
                return
            log_path = f"/tmp/openclaw_scrape_{country}_{niche}.log"
            send(chat_id, f"⬡ Scraping <b>{niche}</b> in <b>{country.upper()}</b>...\nRunning in background (~10-15 min). You'll get a ping when it's done.")
            try:
                with open(log_path, "w") as log:
                    proc = subprocess.Popen(
                        ["python3", str(OPS_ROUTER), "scrape", country, niche],
                        stdout=log, stderr=log
                    )
                # Fire off completion watcher in a detached process so it survives
                # even if the bot restarts mid-scrape.
                notify_script = ROOT / "scripts" / "scrape_completion_notify.py"
                subprocess.Popen(
                    ["setsid", "python3", notify_script,
                     str(proc.pid), country, niche, log_path],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except Exception as e:
                send(chat_id, f"❌ Failed to start: {e}")
        else:
            send(chat_id, "Usage: <code>scrape us roofers</code>")
        return

    # ── PREPARE / MARKET PREP ──
    _is_prep = (lower.startswith("prepare ") or lower.startswith("market prep")
                or lower.startswith("prep market") or lower.startswith("prep "))
    if _is_prep:
        tokens = lower.split()
        country = next((t for t in tokens if t in VALID_COUNTRIES), None)
        niche   = next((t for t in tokens if t in VALID_NICHES), None)
        if not country:
            send(chat_id, "Usage: <code>prepare us</code> or <code>prepare roofers us</code>")
            return
        send(chat_id, f"⬡ Preparing {country.upper()} market...")
        if niche:
            result = run_ops(f"prepare {niche} {country}")
        else:
            result = run_ops(f"prepare next market {country}")
        send(chat_id, result[:4000] if result else "✅ Done.")
        return

    # ── SYNC ──
    if lower.startswith("sync "):
        send(chat_id, f"⬡ Syncing to Notion...")
        result = run_ops(text.lower())
        send(chat_id, result[:4000] if result else "✅ Synced.")
        return

    # ── ASK ──
    if lower.startswith("ask "):
        question = text[4:].strip()
        send(chat_id, "⬡ Thinking...")
        result = run_ops(f"ask {question}")
        send(chat_id, result[:4000] if result else "No response.")
        return

    # ── GENERATE CONFIG (also accepts "create config") ──
    if lower.startswith("generate config") or lower.startswith("create config"):
        parts = lower.split()
        country = parts[2] if len(parts) > 2 else "all"
        send(chat_id, f"⬡ Generating config for {country.upper()}...")
        result = run_ops(f"generate config {country}")
        send(chat_id, result[:4000] if result else "✅ Done.")
        return

    # ── CREATE DEAL ──
    if lower.startswith("create deal"):
        deal_info = text[11:].strip().lstrip(":").strip()
        send(chat_id, "⬡ Creating deal in Notion...")
        result = run_ops(f"create deal: {deal_info}")
        send(chat_id, result)
        return

    # ── ADD LEAD ──
    if lower.startswith("add lead:") or lower.startswith("add lead "):
        lead_info = text[9:].strip() if lower.startswith("add lead:") else text[9:].strip()
        send(chat_id, "⬡ Adding lead to Notion...")
        result = run_ops(f"add {lead_info}")
        send(chat_id, result)
        return

    # ── UNKNOWN — route through ops_router anyway ──
    send(chat_id, f"⬡ Running: <code>{text}</code>")
    result = run_ops(text.lower())
    if result:
        send(chat_id, result[:4000])
    else:
        send(chat_id, f"Unknown command. Send <code>help</code> for all commands.")

# ── MAIN LOOP ─────────────────────────────────────────────
def main():
    print(f"⬡ COMMAND Bot starting...")
    print(f"  Allowed user: {ALLOWED_USER}")
    print(f"  Ops router: {OPS_ROUTER}")

    offset = load_offset()
    print(f"  Starting from offset: {offset}")
    print(f"⬡ Listening for commands...\n")

    while True:
        try:
            data = get_updates(offset)

            if not data.get("ok"):
                time.sleep(5)
                continue

            updates = data.get("result", [])

            for update in updates:
                offset = update["update_id"] + 1
                save_offset(offset)

                msg = update.get("message", {})
                if not msg:
                    continue

                chat_id = msg.get("chat", {}).get("id")
                user_id = msg.get("from", {}).get("id")
                text    = msg.get("text", "").strip()

                if not text or not chat_id:
                    continue

                handle(chat_id, user_id, text)

        except KeyboardInterrupt:
            print("\n⬡ Bot stopped.")
            break
        except Exception as e:
            print(f"[LOOP ERROR] {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
