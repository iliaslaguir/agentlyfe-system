# CLAUDE.md — Agentlyfe System

This file gives Claude Code context when working inside this repo.
Edit it to reflect your own business — the version shipped is a generic template.

## What this system is
A lead-scraping + Notion CRM stack for cold outreach to local businesses.
Scrapes Google Places, scores each lead (A+/A/B/C), syncs to Notion, runs daily AI briefings.

## Source of truth
**Lead/client status = Notion**, not local files.
Don't hardcode client names, MRR, or pipeline state in this file — query Notion when asked.

When asked about pipeline / status / clients:
- Query Notion's Leads database, never guess
- Active leads = Status != "Won" AND Status != "Lost"
- Clients = Status == "Won"
- Dead leads = Status == "Lost"

## System Root
`Path(__file__).resolve().parent.parent` — every script resolves paths from its own location, so the repo is portable.

## APIs and Integrations
- Anthropic API (Claude) — morning briefing, ask-claude AI helpers
- Google Places API (New Places API, v1) — business discovery
- Notion API — lead CRM
- Telegram Bot API — optional command interface
- Dropbox — optional A/B lead CSV export

## Scripts (scripts/)
- `ops_router.py` — CLI entry point, routes all commands
- `scraper.py` — Google Places scraper + lead prioritization
- `scrape_manager.py` — scrape state, summaries, suggestions
- `config_generator.py` — generate country configs
- `market_prep.py` — market prep / niche suggestions
- `morning_briefing.py` — daily AI briefing (reads `configs/business_context.json`)
- `email_discovery.py` — find emails for leads
- `add_lead.py` — manually add a lead
- `sync_ab_to_notion.py` — sync A/B leads to Notion
- `notion_sync_manager.py` — sync state manager
- `backfill_outreach_to_notion.py` — backfill outreach data
- `backfill_tz_tier.py` — backfill timezone + city tier
- `create_deal.py`, `fill_deal.py` — deal management
- `dashboard.py` — Flask local dashboard
- `telegram_bot.py` — Telegram command interface
- `scrape_completion_notify.py` — Telegram ping when scrape finishes
- `maintenance/` — optional shell scripts for VPS housekeeping

## Configs (configs/)
- `<country>.json` — per-country city + niche config (generate via `config_generator.py`)
- `business_context.json` — your clients/projects/notes (used by morning briefing)
- `<country>_city_meta.json` — optional city tier + timezone metadata
- `secrets/notion.env` — API keys (gitignored)
- `secrets/anthropic_key.txt` — Anthropic API key (gitignored)

## State (state/)
- `<country>_progress.json` — per-country scrape progress
- `notion_sync_log.json` — sync state
- `telegram_offset.txt` — Telegram polling offset

## Country & Niche Codes (defaults)
- Countries: `us`, `uk`, `au`, `ca`, `ie`, `nz`, `fi`
- Niches: `builders`, `electricians`, `plumbers`, `roofers`, `hvac`, `painters`, `landscapers`, `pest_control`, `barbershops`

Add more by editing your country config JSON.

## Command Spine (full list in COMMANDS.md)
```
python3 scripts/ops_router.py scrape <niche> <n> <country>
python3 scripts/ops_router.py sync <niche> <country> notion
python3 scripts/ops_router.py where <country>
python3 scripts/ops_router.py summary <country>
python3 scripts/ops_router.py next <country>
python3 scripts/ops_router.py ask "your question"
```

## When fixing bugs
- Preserve existing logic unless it IS the bug
- Never touch `configs/secrets/`
- Don't introduce new dependencies without good reason — `requirements.txt` should stay minimal
- If unsure, ask
