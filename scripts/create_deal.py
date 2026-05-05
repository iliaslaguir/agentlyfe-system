#!/usr/bin/env python3
"""
OpenClaw Deal Creator
Creates a new deal in Notion with AI-generated content.

Usage:
  python3 create_deal.py "Acme Roofing, John, Google Ads retainer, $1500/month"
  python3 create_deal.py "Bright Plumbing, website build, $500 one-time"
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

# ── CLAUDE DEAL ANALYSIS ──────────────────────────────────
SYSTEM = """You are a CRM assistant for Agentlyfe, a digital marketing agency.

Agency context:
- Offer: Free website build → €500 acceptance fee → monthly retainer
- Fee structure: minimum €400/month AND/OR 10% of ad spend
- Services: Google Ads, Meta Ads, SEO, website builds, full retainers

Billing type options: One-time, Monthly, One-time + Monthly, One-time + Comission, One-time + Monthly + Comission

Stage options: New, Contacted, Qualified, Proposal sent, Negotiation, Lost, Won

Respond ONLY with valid JSON, no preamble."""

def analyze_deal_with_claude(raw_input: str, context: dict) -> dict:
    api_key = ANTHROPIC_KEY_F.read_text().strip()

    # Get client context
    clients = context.get("clients", {})
    client_context = ""
    for cname, cdata in clients.items():
        if any(word.lower() in raw_input.lower() for word in cname.split()):
            client_context = f"{cname}: {cdata.get('details', '')} [Status: {cdata.get('status', '')}]"
            break

    now = datetime.now(SPAIN_TZ).strftime("%Y-%m-%d")

    prompt = f"""Analyze this deal input and generate all required fields.

Input: "{raw_input}"

Known client context: {client_context if client_context else "No existing context"}
Today's date: {now}

Return ONLY this JSON:
{{
  "deal_name": "descriptive deal name e.g. 'Acme Roofing Google Ads Setup'",
  "value": 500,
  "billing_type": "One-time|Monthly|One-time + Monthly|One-time + Comission|One-time + Monthly + Comission",
  "stage": "New|Contacted|Qualified|Proposal sent|Negotiation|Lost|Won",
  "expected_close_date": "YYYY-MM-DD (estimate 2-4 weeks from today if not specified)",
  "next_step": "specific next action to take",
  "website_draft": "",
  "deal_overview": "2-3 sentences: what this deal is, value, current status",
  "client_snapshot": "2-3 sentences: who the client is, their business, their market",
  "what_they_need": "2-3 sentences: their problem and what we are solving",
  "proposed_solution": "2-3 sentences: scope and deliverables",
  "pricing_terms": "full pricing breakdown with amounts",
  "active_campaigns": "what is live or N/A if pre-sale",
  "execution_sop": ["step 1", "step 2", "step 3", "step 4", "step 5"],
  "next_steps_detail": "who does what by when",
  "risks": "key risks or objections",
  "internal_notes": "internal strategy note"
}}"""

    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1200,
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

# ── NOTION BLOCKS ─────────────────────────────────────────
def make_heading(text: str, level=2) -> dict:
    htype = f"heading_{level}"
    return {"object": "block", "type": htype,
            htype: {"rich_text": [{"type": "text", "text": {"content": text}}]}}

def make_text(text: str) -> dict:
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": str(text)}}]}}

def make_todo(text: str) -> dict:
    return {"object": "block", "type": "to_do",
            "to_do": {"rich_text": [{"type": "text", "text": {"content": text}}], "checked": False}}

def make_divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}

def build_page_blocks(deal: dict) -> list:
    now = datetime.now(SPAIN_TZ).strftime("%d %b %Y %H:%M")
    blocks = []

    blocks.append(make_text(f"Created by COMMAND: {now}"))
    blocks.append(make_divider())

    blocks.append(make_heading("🧠 DEAL OVERVIEW", 2))
    blocks.append(make_text(deal.get("deal_overview", "")))
    blocks.append(make_divider())

    blocks.append(make_heading("👤 CLIENT SNAPSHOT", 2))
    blocks.append(make_text(deal.get("client_snapshot", "")))
    blocks.append(make_divider())

    blocks.append(make_heading("🎯 WHAT THEY NEED", 2))
    blocks.append(make_text(deal.get("what_they_need", "")))
    blocks.append(make_divider())

    blocks.append(make_heading("🧩 PROPOSED SOLUTION", 2))
    blocks.append(make_text(deal.get("proposed_solution", "")))
    blocks.append(make_divider())

    blocks.append(make_heading("💰 PRICING & TERMS", 2))
    blocks.append(make_text(deal.get("pricing_terms", "")))
    blocks.append(make_divider())

    blocks.append(make_heading("🚀 ACTIVE CAMPAIGNS", 2))
    blocks.append(make_text(deal.get("active_campaigns", "No active campaigns yet.")))
    blocks.append(make_divider())

    blocks.append(make_heading("📋 EXECUTION SOP — THIS MONTH", 2))
    for item in deal.get("execution_sop", []):
        blocks.append(make_todo(item))
    blocks.append(make_divider())

    blocks.append(make_heading("📅 MONTHLY CHECKLIST", 2))
    for item in ["Campaign optimised", "Performance report sent",
                 "Ad spend checked vs budget", "Invoice sent",
                 "Payment received", "Next month planned"]:
        blocks.append(make_todo(item))
    blocks.append(make_divider())

    blocks.append(make_heading("📌 NEXT STEPS", 2))
    blocks.append(make_text(deal.get("next_steps_detail", "")))
    blocks.append(make_divider())

    blocks.append(make_heading("⚠️ RISKS & OBJECTIONS", 2))
    blocks.append(make_text(deal.get("risks", "")))
    blocks.append(make_divider())

    blocks.append(make_heading("📞 CALL LOG", 2))
    blocks.append(make_text(f"{datetime.now(SPAIN_TZ).strftime('%d %b %Y')} — (add call notes here)"))
    blocks.append(make_divider())

    blocks.append(make_heading("📁 ASSETS", 2))
    blocks.append(make_text("Website: \nAd Account ID: \nContract: \nBrand assets: "))
    blocks.append(make_divider())

    blocks.append(make_heading("🔒 INTERNAL NOTES", 2))
    blocks.append(make_text(deal.get("internal_notes", "")))

    return blocks

# ── CREATE DEAL IN NOTION ─────────────────────────────────
def create_notion_deal(deal: dict, db_id: str, token: str) -> str:
    """Create the deal page with properties."""
    props = {
        "Deal": {"title": [{"type": "text", "text": {"content": deal["deal_name"]}}]},
        "Stage": {"status": {"name": deal.get("stage", "New")}},
        "Billing type": {"select": {"name": deal.get("billing_type", "One-time")}},
        "Next step": {"rich_text": [{"type": "text", "text": {"content": deal.get("next_step", "")}}]},
    }

    if deal.get("value"):
        try:
            props["Value"] = {"number": float(str(deal["value"]).replace("€", "").replace(",", "").strip())}
        except:
            pass

    if deal.get("expected_close_date"):
        props["Expected close date"] = {"date": {"start": deal["expected_close_date"]}}

    if deal.get("website_draft"):
        props["Website Draft"] = {"url": deal["website_draft"]}

    payload = {
        "parent": {"database_id": db_id},
        "properties": props,
        "children": build_page_blocks(deal)
    }

    result = notion_req("https://api.notion.com/v1/pages", payload, token)
    return result.get("id", "")

# ── MAIN ──────────────────────────────────────────────────
def create_deal(raw_input: str) -> str:
    secrets = load_secrets()
    token   = secrets.get("NOTION_TOKEN")
    db_id   = secrets.get("NOTION_DEALS_DB_ID")

    if not token or not db_id:
        return "❌ Missing Notion credentials."

    print(f"  Analyzing deal: {raw_input}")
    context = load_context()
    deal    = analyze_deal_with_claude(raw_input, context)
    print(f"  Deal: {deal['deal_name']} | Stage: {deal['stage']} | Value: €{deal['value']}")

    print(f"  Creating in Notion...")
    page_id = create_notion_deal(deal, db_id, token)

    if not page_id:
        return "❌ Failed to create deal in Notion."

    notion_url = f"https://notion.so/{page_id.replace('-', '')}"
    return (
        f"✅ Deal created: {deal['deal_name']}\n"
        f"📊 Stage: {deal['stage']}\n"
        f"💰 Value: €{deal['value']} ({deal['billing_type']})\n"
        f"📅 Expected close: {deal['expected_close_date']}\n"
        f"➡️ Next step: {deal['next_step']}\n"
        f"🔗 {notion_url}"
    )

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 create_deal.py \"Client name, service, value\"")
        print("Example: python3 create_deal.py \"Acme Roofing, Google Ads retainer, $1500/month\"")
        sys.exit(1)

    raw = " ".join(sys.argv[1:])
    print(create_deal(raw))
