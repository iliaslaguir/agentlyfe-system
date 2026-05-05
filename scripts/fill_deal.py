#!/usr/bin/env python3
"""
OpenClaw Deal Filler
Finds a deal page in Notion by name and fills it with AI-generated content.

Usage:
  python3 fill_deal.py "Acme Roofing"
  python3 fill_deal.py "Bright Plumbing"
"""

import json
import sys
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent.parent
CONFIGS         = ROOT / "configs"
ANTHROPIC_KEY_F = CONFIGS / "secrets" / "anthropic_key.txt"
NOTION_ENV      = CONFIGS / "secrets" / "notion.env"
CONTEXT_FILE    = CONFIGS / "business_context.json"
NOTION_VERSION  = "2022-06-28"
SPAIN_TZ        = timezone(timedelta(hours=2))

def load_secrets():
    secrets = {}
    if NOTION_ENV.exists():
        for line in NOTION_ENV.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                secrets[k.strip()] = v.strip()
    return secrets

def load_context():
    if CONTEXT_FILE.exists():
        try:
            return json.loads(CONTEXT_FILE.read_text())
        except:
            pass
    return {"clients": {}, "projects": {}, "notes": []}

def notion_req(url, data, token, method="POST"):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        url, data=body, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION
        }
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def find_deal_page(name: str, db_id: str, token: str) -> dict:
    """Search Deals DB for a page matching the name."""
    data = notion_req(
        f"https://api.notion.com/v1/databases/{db_id}/query",
        {"page_size": 20}, token
    )
    name_lower = name.lower()
    for page in data.get("results", []):
        title = page["properties"].get("Deal", {}).get("title", [{}])
        page_name = title[0].get("plain_text", "") if title else ""
        if name_lower in page_name.lower():
            return page
    return {}

def get_existing_content(page_id: str, token: str) -> str:
    """Get existing page content as text."""
    try:
        data = notion_req(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            None, token, method="GET"
        )
        lines = []
        for block in data.get("results", []):
            btype = block.get("type", "")
            content = block.get(btype, {})
            rich = content.get("rich_text", [])
            text = "".join(r.get("plain_text", "") for r in rich)
            if text.strip():
                lines.append(text)
        return "\n".join(lines)
    except:
        return ""

SYSTEM = """You are filling in a deal/client page in Notion for Agentlyfe, a digital marketing agency.

Generate professional, specific content for each section based on what you know about the client.
Be concise but thorough. Write in plain text, no markdown formatting.
Each section should have 2-5 lines of actual useful content, not placeholders."""

def generate_deal_content(deal_name: str, deal_props: dict, context: dict) -> dict:
    """Generate content for all sections of the deal page."""
    api_key = ANTHROPIC_KEY_F.read_text().strip()

    # Get client info from context
    clients = context.get("clients", {})
    client_info = ""
    for cname, cdata in clients.items():
        if cname.lower() in deal_name.lower() or deal_name.lower() in cname.lower():
            client_info = f"{cname}: {cdata.get('details', '')}"
            break

    # Get deal properties
    stage = deal_props.get("Stage", {}).get("select", {})
    stage_name = stage.get("name", "") if stage else ""
    value = deal_props.get("Value", {}).get("number", 0) or 0
    billing = deal_props.get("Billing type", {}).get("select", {})
    billing_name = billing.get("name", "") if billing else ""
    close_date = deal_props.get("Expected close date", {}).get("date", {})
    close_str = close_date.get("start", "") if close_date else ""
    next_step_prop = deal_props.get("Next step", {}).get("rich_text", [])
    next_step = next_step_prop[0].get("plain_text", "") if next_step_prop else ""

    prompt = f"""Fill in a deal page for: {deal_name}

Deal data from CRM:
- Stage: {stage_name}
- Value: €{value}
- Billing: {billing_name}
- Expected close: {close_str}
- Next step noted: {next_step}

Client context from business records:
{client_info if client_info else "No additional context available"}

Agency context:
- Agentlyfe offers: free website build → €500 acceptance fee → monthly retainer
- Services: Google Ads, Meta Ads, SEO, website builds
- Fee structure: minimum €400/month or 10% of ad spend

Generate content for each section. Return ONLY valid JSON:
{{
  "deal_overview": "2-3 sentences describing the deal, what service, value, current status",
  "client_snapshot": "2-3 sentences about who the client is, their business, their market",
  "what_they_need": "2-3 sentences about their problem and what we are solving",
  "proposed_solution": "2-3 sentences about scope and deliverables",
  "pricing_terms": "pricing breakdown with amounts and payment terms",
  "active_campaigns": "what is currently live or being set up, or N/A if pre-sale",
  "execution_sop": ["task 1", "task 2", "task 3", "task 4", "task 5"],
  "next_steps": "who does what by when - specific actions",
  "risks": "1-2 key risks or objections to be aware of",
  "internal_notes": "brief internal note about this deal status and strategy"
}}"""

    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1000,
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

def make_text_block(text: str, style="paragraph") -> dict:
    return {
        "object": "block",
        "type": style,
        style: {
            "rich_text": [{"type": "text", "text": {"content": text}}]
        }
    }

def make_heading(text: str, level=2) -> dict:
    htype = f"heading_{level}"
    return {
        "object": "block",
        "type": htype,
        htype: {
            "rich_text": [{"type": "text", "text": {"content": text}}]
        }
    }

def make_todo(text: str, checked=False) -> dict:
    return {
        "object": "block",
        "type": "to_do",
        "to_do": {
            "rich_text": [{"type": "text", "text": {"content": text}}],
            "checked": checked
        }
    }

def make_divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}

def build_blocks(content: dict, deal_name: str) -> list:
    """Build Notion blocks from generated content."""
    blocks = []
    now = datetime.now(SPAIN_TZ).strftime("%d %b %Y")

    blocks.append(make_text_block(f"Last updated by COMMAND: {now}", "paragraph"))
    blocks.append(make_divider())

    # Deal Overview
    blocks.append(make_heading("🧠 DEAL OVERVIEW", 2))
    blocks.append(make_text_block(content.get("deal_overview", "")))
    blocks.append(make_divider())

    # Client Snapshot
    blocks.append(make_heading("👤 CLIENT SNAPSHOT", 2))
    blocks.append(make_text_block(content.get("client_snapshot", "")))
    blocks.append(make_divider())

    # What They Need
    blocks.append(make_heading("🎯 WHAT THEY NEED", 2))
    blocks.append(make_text_block(content.get("what_they_need", "")))
    blocks.append(make_divider())

    # Proposed Solution
    blocks.append(make_heading("🧩 PROPOSED SOLUTION", 2))
    blocks.append(make_text_block(content.get("proposed_solution", "")))
    blocks.append(make_divider())

    # Pricing
    blocks.append(make_heading("💰 PRICING & TERMS", 2))
    blocks.append(make_text_block(content.get("pricing_terms", "")))
    blocks.append(make_divider())

    # Active Campaigns
    blocks.append(make_heading("🚀 ACTIVE CAMPAIGNS", 2))
    blocks.append(make_text_block(content.get("active_campaigns", "No active campaigns yet.")))
    blocks.append(make_divider())

    # Execution SOP
    blocks.append(make_heading("📋 EXECUTION SOP — THIS MONTH", 2))
    sop_items = content.get("execution_sop", [])
    for item in sop_items:
        blocks.append(make_todo(item))
    blocks.append(make_divider())

    # Monthly Checklist
    blocks.append(make_heading("📅 MONTHLY CHECKLIST", 2))
    for item in [
        "Campaign optimised",
        "Performance report sent",
        "Ad spend checked vs budget",
        "Invoice sent",
        "Payment received",
        "Next month planned"
    ]:
        blocks.append(make_todo(item))
    blocks.append(make_divider())

    # Next Steps
    blocks.append(make_heading("📌 NEXT STEPS", 2))
    blocks.append(make_text_block(content.get("next_steps", "")))
    blocks.append(make_divider())

    # Risks
    blocks.append(make_heading("⚠️ RISKS & OBJECTIONS", 2))
    blocks.append(make_text_block(content.get("risks", "")))
    blocks.append(make_divider())

    # Call Log
    blocks.append(make_heading("📞 CALL LOG", 2))
    blocks.append(make_text_block(f"{now} — (add notes here)"))
    blocks.append(make_divider())

    # Assets
    blocks.append(make_heading("📁 ASSETS", 2))
    blocks.append(make_text_block("Website: \nAd Account ID: \nContract: \nBrand assets: "))
    blocks.append(make_divider())

    # Internal Notes
    blocks.append(make_heading("🔒 INTERNAL NOTES", 2))
    blocks.append(make_text_block(content.get("internal_notes", "")))

    return blocks

def clear_page_content(page_id: str, token: str):
    """Delete all existing blocks from the page."""
    try:
        data = notion_req(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            None, token, method="GET"
        )
        for block in data.get("results", []):
            try:
                notion_req(
                    f"https://api.notion.com/v1/blocks/{block['id']}",
                    None, token, method="DELETE"
                )
            except:
                pass
    except:
        pass

def append_blocks(page_id: str, blocks: list, token: str):
    """Append blocks to page in batches of 100."""
    for i in range(0, len(blocks), 90):
        batch = blocks[i:i+90]
        notion_req(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            {"children": batch}, token
        )

def fill_deal(deal_name: str) -> str:
    secrets = load_secrets()
    token   = secrets.get("NOTION_TOKEN")
    db_id   = secrets.get("NOTION_DEALS_DB_ID")

    if not token or not db_id:
        return "❌ Missing Notion credentials."

    print(f"  Searching for deal: {deal_name}")
    page = find_deal_page(deal_name, db_id, token)
    if not page:
        return f"❌ Deal not found: '{deal_name}'. Check the name matches your Deals database."

    page_id   = page["id"]
    page_name = page["properties"].get("Deal", {}).get("title", [{}])
    full_name = page_name[0].get("plain_text", deal_name) if page_name else deal_name
    print(f"  Found: {full_name} ({page_id})")

    print(f"  Generating content with Claude...")
    context = load_context()
    content = generate_deal_content(full_name, page["properties"], context)

    print(f"  Clearing existing page content...")
    clear_page_content(page_id, token)

    print(f"  Writing new content to Notion...")
    blocks = build_blocks(content, full_name)
    append_blocks(page_id, blocks, token)

    notion_url = f"https://notion.so/{page_id.replace('-', '')}"
    return (
        f"✅ Deal page filled: {full_name}\n"
        f"📋 Sections written: Overview, Client snapshot, What they need, "
        f"Proposed solution, Pricing, Active campaigns, Execution SOP, "
        f"Monthly checklist, Next steps, Risks, Call log, Assets\n"
        f"🔗 {notion_url}"
    )

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 fill_deal.py \"Client Name\"")
        sys.exit(1)

    deal = " ".join(sys.argv[1:])
    print(fill_deal(deal))
