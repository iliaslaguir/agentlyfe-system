#!/usr/bin/env python3
"""
OpenClaw Lead Adder
Adds a lead to Notion with Claude filling all fields automatically.

Usage:
  python3 add_lead.py "Joe Blogs Plumbing, Manchester UK, 07700123456, joeblogsplumbing.co.uk"
  python3 add_lead.py "Smith Electric Dublin Ireland, 0851234567"
  python3 add_lead.py "Bob's Roofing Boulder Colorado USA, 7205551234, no website"
"""

import json
import sys
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent.parent
CONFIGS         = ROOT / "configs"
ANTHROPIC_KEY_F = CONFIGS / "secrets" / "anthropic_key.txt"
NOTION_ENV      = CONFIGS / "secrets" / "notion.env"
NOTION_VERSION  = "2022-06-28"
SPAIN_TZ        = timezone(timedelta(hours=2))

# ── LOAD SECRETS ──────────────────────────────────────────
def load_secrets():
    secrets = {}
    if NOTION_ENV.exists():
        for line in NOTION_ENV.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                secrets[k.strip()] = v.strip()
    return secrets

# ── WEBSITE CHECKER ───────────────────────────────────────
def check_website(url: str) -> dict:
    """Quick check if website exists and is functional."""
    if not url or url.lower() in ("no website", "none", "n/a", ""):
        return {"has_website": False, "score": 0, "issue": "No website"}

    if not url.startswith("http"):
        url = "http://" + url

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; bot)"}
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            content = r.read(5000).decode("utf-8", errors="ignore")
            score = 30  # base score for having a working site

            # Score factors
            if len(content) > 2000: score += 10
            if "contact" in content.lower(): score += 10
            if "phone" in content.lower() or "tel:" in content.lower(): score += 10
            if "about" in content.lower(): score += 5
            if "gallery" in content.lower() or "portfolio" in content.lower(): score += 5
            if "review" in content.lower() or "testimonial" in content.lower(): score += 10
            if "book" in content.lower() or "quote" in content.lower(): score += 10

            return {
                "has_website": True,
                "score": min(score, 100),
                "issue": "Website exists but could be improved" if score < 60 else "Decent website"
            }
    except Exception as e:
        return {"has_website": True, "score": 10, "issue": f"Site unreachable: {str(e)[:50]}"}


# ── CLAUDE FIELD GENERATOR ────────────────────────────────
def _load_offer_context() -> str:
    """Pull offer + pitch angle from business_context.json (set by config_generator)."""
    ctx_file = ROOT / "configs" / "business_context.json"
    try:
        ctx = json.loads(ctx_file.read_text())
        offer = ctx.get("offer", "").strip()
        pitch = ctx.get("pitch_angle", "").strip()
        target = ctx.get("target_profile", "").strip()
        parts = []
        if offer:  parts.append(f"Offer: {offer}")
        if target: parts.append(f"Target buyer: {target}")
        if pitch:  parts.append(f"Pitch angle: {pitch}")
        return "\n".join(parts) if parts else ""
    except Exception:
        return ""

SYSTEM = f"""You are filling in a lead database for a lead-generation system.

{_load_offer_context() or "Offer: Free website build for small trade businesses then a monthly marketing retainer."}

Priority scoring (gap-based — bigger gap = easier pitch):
- A = Major gap vs what we sell (e.g. no website / no AI receptionist / no current solution) — easiest pitch
- B = Weak / outdated current solution — easy to show value
- C = Has a decent current solution — harder pitch

Outreach channel logic:
- If phone number available → "Call" (highest conversion)
- If email found → "Email"
- Both → "Mixed"
- Neither → "Call" (find the number)

Call Priority:
- A priority leads → "High"
- B priority leads → "Normal"
- C priority leads → "Low"

CALL BUCKET:
- A priority → "Hot"
- B priority → "Warm"
- C priority → "Cold"

Next Action:
- Always start with "Send First Message" for new leads

Stage: Always "New" for new leads

Lead Type: "Manual" for manually added leads, "Scraped" for scraped

Source: Use the search term or "Manual Entry" if added by hand

Email Angle options: "No Website", "Bad Website", "More Leads", "Competitor Analysis"
- A leads → "No Website"
- B leads → "Bad Website"
- C leads → "More Leads"

Respond ONLY with valid JSON, no preamble, no markdown."""

def generate_fields_with_claude(lead_info: str, website_data: dict) -> dict:
    api_key = ANTHROPIC_KEY_F.read_text().strip()

    prompt = f"""Lead information provided:
{lead_info}

Website check results:
- Has website: {website_data['has_website']}
- Website score: {website_data['score']}/100
- Issue: {website_data['issue']}

Generate all fields for this lead. Return ONLY this JSON:
{{
  "priority": "A|B|C",
  "outreach_channel": "Call|Email|Mixed",
  "call_priority": "High|Normal|Low",
  "call_bucket": "Hot|Warm|Cold|None",
  "next_action": "Send First Message",
  "stage": "New",
  "lead_type": "Manual",
  "niche": "builders|electricians|plumbers|roofers|hvac|other",
  "industry": "builders|electricians|plumbers|roofers|hvac|other",
  "country": "UK|US|AU|CA|IE|NZ",
  "city": "city name only",
  "source": "Manual Entry",
  "email_angle": "No Website|Bad Website|More Leads|Competitor Analysis",
  "email_status": "Not Needed|Pending|Found|Not Found",
  "email_discovery_stage": "Not Needed|Pending",
  "issue": "{website_data['issue']}",
  "website_score": {website_data['score']},
  "email_draft": "Subject: [compelling subject line]\\n\\n[2-3 sentence cold email pitching the OFFER above to this specific lead. Reference their niche and city. End with a friendly sign-off.]",
  "delivery_message": "Short 1-line SMS/WhatsApp message to introduce yourself",
  "internal_notes": "Brief note about this lead and why they are a good prospect"
}}"""

    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 800,
        "system": SYSTEM,
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
    return json.loads(raw.strip())


# ── PARSE LEAD INPUT ──────────────────────────────────────
def parse_lead_input(raw: str) -> dict:
    """Extract business name, phone, website, city from natural language."""
    parts = [p.strip() for p in raw.split(",")]
    result = {
        "business_name": parts[0] if parts else "Unknown",
        "phone": "",
        "website": "",
        "city": "",
        "raw": raw
    }

    for part in parts[1:]:
        part = part.strip()
        # Phone detection
        if any(c.isdigit() for c in part) and len([c for c in part if c.isdigit()]) >= 7:
            result["phone"] = part
        # Website detection
        elif any(x in part.lower() for x in ["http", "www", ".com", ".co.uk", ".ie", ".au", ".ca", ".nz", "website"]):
            result["website"] = part if "no website" not in part.lower() else ""
        # City detection (contains country name or looks like a place)
        elif any(x in part.upper() for x in ["UK", "USA", "US", "AU", "CA", "IE", "NZ", "AUSTRALIA", "CANADA", "IRELAND"]):
            result["city"] = part
        elif len(part.split()) <= 4 and part[0].isupper():
            result["city"] = part

    return result


# ── BUILD NOTION PAYLOAD ──────────────────────────────────
def build_notion_payload(parsed: dict, fields: dict, db_id: str) -> dict:
    def txt(val):
        return [{"type": "text", "text": {"content": str(val)}}]

    def sel(val):
        return {"name": str(val)}

    props = {
        "Business Name": {"title": txt(parsed["business_name"])},
        "Stage":         {"status": {"name": fields.get("stage", "New")}},
        "Priority":      {"select": sel(fields.get("priority", "A"))},
        "Outreach Channel": {"select": sel(fields.get("outreach_channel", "Call"))},
        "Call Priority": {"select": sel(fields.get("call_priority", "Normal"))},
        "CALL BUCKET":   {"select": sel(fields.get("call_bucket", "None"))},
        "Next Action":   {"select": sel(fields.get("next_action", "Send First Message"))},
        "Lead Type":     {"select": sel(fields.get("lead_type", "Manual"))},
        "Niche":         {"select": sel(fields.get("niche", "builders"))},
        "Industry":      {"select": sel(fields.get("industry", "builders"))},
        "Country":       {"select": sel(fields.get("country", "UK"))},
        "Source":        {"select": sel(fields.get("source", "Manual Entry"))},
        "Email Angle":   {"select": sel(fields.get("email_angle", "No Website"))},
        "Email Status":  {"select": sel(fields.get("email_status", "Not Needed"))},
        "Email Discovery Stage": {"select": sel(fields.get("email_discovery_stage", "Not Needed"))},
        "Website Score": {"number": int(fields.get("website_score", 0))},
        "Paid":          {"checkbox": False},
        "Link Sent":     {"checkbox": False},
        "City":          {"rich_text": txt(fields.get("city", parsed.get("city", "")))},
        "Issue":         {"rich_text": txt(fields.get("issue", ""))},
        "Internal Notes": {"rich_text": txt(fields.get("internal_notes", ""))},
        "Email Draft":   {"rich_text": txt(fields.get("email_draft", ""))},
        "Delivery message": {"rich_text": txt(fields.get("delivery_message", ""))},
        "Lead Key":      {"rich_text": txt(f"manual_{parsed['business_name'].lower().replace(' ', '_')[:30]}")},
    }

    # Optional fields
    if parsed.get("phone"):
        props["Phone"] = {"phone_number": parsed["phone"]}

    if parsed.get("website") and parsed["website"].startswith("http"):
        props["Website"] = {"url": parsed["website"]}

    return {"parent": {"database_id": db_id}, "properties": props}


# ── ADD TO NOTION ─────────────────────────────────────────
def add_to_notion(payload: dict, token: str) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.notion.com/v1/pages",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION
        }
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


# ── MAIN ──────────────────────────────────────────────────
def add_lead(raw_input: str) -> str:
    secrets = load_secrets()
    token   = secrets.get("NOTION_TOKEN")
    db_id   = secrets.get("NOTION_LEADS_DB_ID")

    if not token or not db_id:
        return "❌ Missing Notion credentials."

    print(f"  Parsing: {raw_input}")
    parsed = parse_lead_input(raw_input)
    print(f"  Business: {parsed['business_name']}")
    print(f"  Phone: {parsed['phone'] or 'none'}")
    print(f"  Website: {parsed['website'] or 'none'}")

    print(f"  Checking website...")
    website_data = check_website(parsed.get("website", ""))
    print(f"  Score: {website_data['score']} | {website_data['issue']}")

    print(f"  Generating fields with Claude...")
    fields = generate_fields_with_claude(raw_input, website_data)
    print(f"  Priority: {fields.get('priority')} | Channel: {fields.get('outreach_channel')}")

    print(f"  Adding to Notion...")
    payload = build_notion_payload(parsed, fields, db_id)
    result  = add_to_notion(payload, token)

    if result.get("id"):
        notion_url = f"https://notion.so/{result['id'].replace('-', '')}"
        return (
            f"✅ Lead added to Notion\n"
            f"📋 {parsed['business_name']}\n"
            f"🎯 Priority: {fields.get('priority')} | {fields.get('outreach_channel')}\n"
            f"📊 Website score: {website_data['score']}/100\n"
            f"🔥 Bucket: {fields.get('call_bucket')}\n"
            f"📝 {fields.get('issue')}\n"
            f"🔗 {notion_url}"
        )
    else:
        return f"❌ Notion error: {str(result)[:200]}"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 add_lead.py \"Business Name, City, Phone, Website\"")
        print("Example: python3 add_lead.py \"Joe Blogs Plumbing, Manchester UK, 07700123456\"")
        sys.exit(1)

    raw = " ".join(sys.argv[1:])
    print(add_lead(raw))
