import subprocess
import sys
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
CONFIGS = ROOT / "configs"
CONTEXT_FILE = CONFIGS / "business_context.json"
ANTHROPIC_KEY_F = CONFIGS / "secrets" / "anthropic_key.txt"

COUNTRIES = {"uk", "us", "au", "ca", "ie", "nz", "fi"}
NICHES    = {"builders", "electricians", "plumbers", "roofers", "hvac", "painters", "landscapers", "pest_control", "barbershops"}


def config_path(country: str) -> str:
    return str(CONFIGS / f"{country}.json")


def run_and_print(cmd: list[str]) -> int:
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in process.stdout:
        print(line, end="", flush=True)
    process.wait()
    return process.returncode


def parse_tokens(text: str):
    return text.strip().lower().split()


# ── BUSINESS CONTEXT FILE ─────────────────────────────────
def load_context() -> dict:
    if CONTEXT_FILE.exists():
        try:
            return json.loads(CONTEXT_FILE.read_text())
        except:
            pass
    # Empty default — populate via `update` command or by editing
    # configs/business_context.json directly. See business_context.json.example.
    return {
        "last_updated": "",
        "clients": {},
        "projects": {},
        "notes": []
    }

def save_context(ctx: dict):
    ctx["last_updated"] = datetime.now(timezone(timedelta(hours=2))).strftime("%Y-%m-%d %H:%M")
    CONTEXT_FILE.write_text(json.dumps(ctx, indent=2))

def context_to_text(ctx: dict) -> str:
    lines = ["=== CLIENTS ==="]
    for name, data in ctx.get("clients", {}).items():
        lines.append(f"{name} [{data['status']}]: {data['details']}")
    lines.append("\n=== PROJECTS ===")
    for name, detail in ctx.get("projects", {}).items():
        lines.append(f"{name}: {detail}")
    if ctx.get("notes"):
        lines.append("\n=== NOTES ===")
        for note in ctx["notes"][-10:]:
            lines.append(f"- {note}")
    return "\n".join(lines)

def update_context_with_claude(raw_update: str) -> str:
    """Ask Claude to intelligently update the context file based on natural language."""
    api_key = ANTHROPIC_KEY_F.read_text().strip()
    ctx = load_context()
    current = context_to_text(ctx)

    prompt = f"""You manage a business context file for a solo operator running
a cold-outreach agency.

Current context:
{current}

New update from the operator: "{raw_update}"

Update the context JSON accordingly. Return ONLY valid JSON matching this exact structure:
{{
  "clients": {{
    "ClientName": {{
      "status": "ACTIVE|URGENT|PIPELINE|UNPAID|COLD|CLOSED|NEW",
      "details": "details string"
    }}
  }},
  "projects": {{
    "ProjectName": "details string"
  }},
  "notes": ["note1", "note2"]
}}

Rules:
- Preserve existing clients/projects unless the update explicitly changes them
- Add new clients if mentioned
- Change status if mentioned (closed, signed, paid, dropped etc)
- Add a note summarizing what changed with today's date
- Return ONLY the JSON, no preamble"""

    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }
    )

    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())

    raw = data["content"][0]["text"].strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"): raw = raw[4:]
    raw = raw.strip()

    new_ctx = json.loads(raw)
    new_ctx["last_updated"] = ""
    save_context(new_ctx)

    # Return summary of what changed
    summary_lines = ["✅ Context updated."]
    for name, d in new_ctx.get("clients", {}).items():
        old = ctx.get("clients", {}).get(name, {})
        if old.get("status") != d["status"]:
            summary_lines.append(f"  {name}: {old.get('status','NEW')} → {d['status']}")
        elif name not in ctx.get("clients", {}):
            summary_lines.append(f"  + New client: {name} [{d['status']}]")
    if new_ctx.get("notes") != ctx.get("notes"):
        notes = new_ctx.get("notes", [])
        if notes:
            summary_lines.append(f"  Note: {notes[-1]}")
    return "\n".join(summary_lines)


# ── ASK CLAUDE ────────────────────────────────────────────
def ask_claude(question: str) -> str:
    api_key = ANTHROPIC_KEY_F.read_text().strip()
    ctx = load_context()
    context_text = context_to_text(ctx)
    now = datetime.now(timezone(timedelta(hours=2))).strftime("%A %d %B %Y, %H:%M")

    SYSTEM = f"""You are COMMAND — a tactical AI assistant for a solo operator running
cold-outreach campaigns to local businesses.

=== LIVE BUSINESS CONTEXT ===
{context_text}

=== LEAD SCRAPER ===
Python lead scraper targets local tradespeople across multiple countries.
Niches: builders, electricians, plumbers, roofers, hvac (and any others
defined in the user's country config).
Priority labels: A+ = website + ads + reviews, A = website + reviews,
B = weak/no website, C = decent existing site.

=== RULES ===
Direct, tactical, no fluff. Highest cashflow action first. Reference real numbers
from the context above. Never invent clients or projects that aren't listed."""

    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 400,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": f"[{now}]\n{question}"}]
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    return data["content"][0]["text"].strip()


def main():
    if len(sys.argv) > 1:
        raw = " ".join(sys.argv[1:])
    else:
        raw = sys.stdin.read().strip()

    tokens = parse_tokens(raw)
    if not tokens:
        print("Empty ops request.")
        sys.exit(1)

    cmd = tokens[0]

    # ---------- ASK CLAUDE ----------
    if cmd == "ask" and len(tokens) > 1:
        question = " ".join(tokens[1:])
        print(ask_claude(question))
        sys.exit(0)

    # ---------- UPDATE CONTEXT ----------
    if cmd in ("update", "new", "closed", "client") and len(tokens) > 1:
        raw_update = raw  # pass full original text
        print(update_context_with_claude(raw_update))
        sys.exit(0)

    # also handle natural "update client:" style
    if ":" in raw and any(kw in raw for kw in ["client", "closed", "signed", "paid", "dropped", "new client", "update", "project"]) and not raw.startswith("create"):
        print(update_context_with_claude(raw))
        sys.exit(0)

    # ---------- SHOW CONTEXT ----------
    if tokens == ["context"] or tokens == ["clients"]:
        ctx = load_context()
        print(f"Last updated: {ctx.get('last_updated', 'never')}")
        print(context_to_text(ctx))
        sys.exit(0)

    # ---------- CONFIG GENERATOR ----------
    if cmd == "generate" and len(tokens) >= 2 and tokens[1] == "config":
        country = tokens[2] if len(tokens) > 2 else "all"
        sys.exit(run_and_print([
            "python3", str(SCRIPTS / "config_generator.py"), country
        ]))

    # ---------- NOTION SYNC ----------
    if tokens == ["sync", "all", "notion"]:
        sys.exit(run_and_print([
            "python3", str(SCRIPTS / "notion_sync_manager.py"), "--all"
        ]))

    if len(tokens) == 4 and tokens[0] == "sync" and tokens[1] == "all" and tokens[2] in COUNTRIES and tokens[3] == "notion":
        sys.exit(run_and_print([
            "python3", str(SCRIPTS / "notion_sync_manager.py"),
            "--all", "--country", tokens[2]
        ]))

    if len(tokens) == 3 and tokens[0] == "sync" and tokens[1] in COUNTRIES and tokens[2] == "notion":
        sys.exit(run_and_print([
            "python3", str(SCRIPTS / "notion_sync_manager.py"),
            "--all", "--country", tokens[1]
        ]))

    if len(tokens) == 3 and tokens[0] == "sync" and tokens[1] in NICHES and tokens[2] == "notion":
        sys.exit(run_and_print([
            "python3", str(SCRIPTS / "notion_sync_manager.py"),
            "--niche", tokens[1]
        ]))

    if len(tokens) == 4 and tokens[0] == "sync" and tokens[1] in NICHES and tokens[2] in COUNTRIES and tokens[3] == "notion":
        sys.exit(run_and_print([
            "python3", str(SCRIPTS / "notion_sync_manager.py"),
            "--niche", tokens[1], "--country", tokens[2]
        ]))

    if len(tokens) == 4 and tokens[0] == "sync" and tokens[1] == "latest" and tokens[2] in NICHES and tokens[3] == "notion":
        sys.exit(run_and_print([
            "python3", str(SCRIPTS / "notion_sync_manager.py"),
            "--latest", "--niche", tokens[2]
        ]))

    if len(tokens) == 5 and tokens[0] == "sync" and tokens[1] == "latest" and tokens[2] in NICHES and tokens[3] in COUNTRIES and tokens[4] == "notion":
        sys.exit(run_and_print([
            "python3", str(SCRIPTS / "notion_sync_manager.py"),
            "--latest", "--niche", tokens[2], "--country", tokens[3]
        ]))

    # ---------- SCRAPE ----------
    # Format: scrape uk builders OR scrape builders 3 uk
    if cmd == "scrape":
        # telegram bot format: scrape uk builders
        if len(tokens) == 3 and tokens[1] in COUNTRIES and tokens[2] in NICHES:
            country, niche = tokens[1], tokens[2]
            sys.exit(run_and_print([
                "python3", str(SCRIPTS / "scraper.py"),
                "--config", config_path(country),
                "--niche", niche,
                "--next", "3"
            ]))
        # old format: scrape builders 3 uk
        if len(tokens) == 4 and tokens[1] in NICHES and tokens[2].isdigit() and tokens[3] in COUNTRIES:
            niche, count, country = tokens[1], tokens[2], tokens[3]
            sys.exit(run_and_print([
                "python3", str(SCRIPTS / "scraper.py"),
                "--config", config_path(country),
                "--niche", niche,
                "--next", count
            ]))
        # scrape uk builders 5
        if len(tokens) == 4 and tokens[1] in COUNTRIES and tokens[2] in NICHES and tokens[3].isdigit():
            country, niche, count = tokens[1], tokens[2], tokens[3]
            sys.exit(run_and_print([
                "python3", str(SCRIPTS / "scraper.py"),
                "--config", config_path(country),
                "--niche", niche,
                "--next", count
            ]))

    # ---------- MARKET PREP ----------
    if len(tokens) == 4 and tokens[0] == "prepare" and tokens[1] == "next" and tokens[2] == "market" and tokens[3] in COUNTRIES:
        sys.exit(run_and_print([
            "python3", str(SCRIPTS / "market_prep.py"),
            "--country", tokens[3]
        ]))

    if len(tokens) == 3 and tokens[0] == "prepare" and tokens[1] in NICHES and tokens[2] in COUNTRIES:
        sys.exit(run_and_print([
            "python3", str(SCRIPTS / "market_prep.py"),
            "--country", tokens[2], "--niche", tokens[1], "--count", "3"
        ]))

    # ---------- STATUS COMMANDS ----------
    if cmd == "summary" and len(tokens) >= 2 and tokens[1] in COUNTRIES:
        sys.exit(run_and_print([
            "python3", str(SCRIPTS / "scrape_manager.py"),
            "--config", config_path(tokens[1]), "summary"
        ]))

    if cmd == "next" and len(tokens) >= 2 and tokens[1] in COUNTRIES:
        sys.exit(run_and_print([
            "python3", str(SCRIPTS / "scrape_manager.py"),
            "--config", config_path(tokens[1]), "suggest-next-niche"
        ]))

    if cmd == "where":
        if len(tokens) == 2 and tokens[1] in COUNTRIES:
            sys.exit(run_and_print([
                "python3", str(SCRIPTS / "scrape_manager.py"),
                "--config", config_path(tokens[1]), "status"
            ]))
        if len(tokens) == 3 and tokens[1] in NICHES and tokens[2] in COUNTRIES:
            sys.exit(run_and_print([
                "python3", str(SCRIPTS / "scrape_manager.py"),
                "--config", config_path(tokens[2]),
                "niche-status", "--niche", tokens[1]
            ]))

    if cmd == "cities":
        if len(tokens) == 3 and tokens[1] in NICHES and tokens[2] in COUNTRIES:
            sys.exit(run_and_print([
                "python3", str(SCRIPTS / "scrape_manager.py"),
                "--config", config_path(tokens[2]),
                "next-cities", "--niche", tokens[1], "--count", "3"
            ]))

    if cmd == "bestcities" and len(tokens) == 3 and tokens[1] in NICHES and tokens[2] in COUNTRIES:
        sys.exit(run_and_print([
            "python3", str(SCRIPTS / "scrape_manager.py"),
            "--config", config_path(tokens[2]),
            "city-breakdown", "--niche", tokens[1]
        ]))




    # ---------- CREATE DEAL ----------
    if raw.startswith("create deal"):
        deal_info = raw[11:].strip().lstrip(":").strip()
        sys.exit(run_and_print([
            "python3", str(SCRIPTS / "create_deal.py"), deal_info
        ]))

    # ---------- ADD LEAD ----------
    if cmd == "add" and len(tokens) > 1:
        lead_info = raw[4:].strip()
        sys.exit(run_and_print([
            "python3", str(SCRIPTS / "add_lead.py"), lead_info
        ]))

    print("Unrecognized command. Send 'help' to the bot for all commands.")
    sys.exit(1)


if __name__ == "__main__":
    main()
