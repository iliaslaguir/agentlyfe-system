# Agentlyfe System

AI-assisted lead scraping + Notion CRM for local business outreach. Scrape Google Places, auto-prioritize leads (A+/A/B/C), sync to Notion, and run daily briefings — all from the command line or Telegram.

Built by [Ilias Laguir](https://www.youtube.com/@iliaslaguir) · Join the [Skool community](https://skool.com) for walkthroughs and support.

---

## Features

| Feature | What it does |
|---|---|
| 🔍 **Google Places Scraper** | 60 results/query, 3-page pagination, multi-country |
| 🏆 **Lead Prioritization** | Auto A+/A/B/C scoring (website, ads, reviews, social) |
| 📋 **Notion Sync** | One command pushes leads into your free Notion CRM |
| 📱 **Telegram Bot** | Run scrapes and check pipeline from your phone |
| 🌅 **Morning Briefing** | Daily AI summary of pipeline status + action items |
| 🗺 **Multi-Country** | Generate configs for any country with `config_generator.py` |
| 🔔 **Completion Alerts** | Telegram ping when a scrape finishes |
| ⏰ **Timezone Sorting** | Group leads by timezone so you call at the right time |
| 📧 **Email Discovery** | Find contact emails for scraped businesses |
| 🏙 **City Tier System** | Target wealthy suburbs before lower-value areas |

---

## Prerequisites

- Python 3.10+
- [Google Places API key](https://developers.google.com/maps/documentation/places/web-service/get-api-key) (New Places API)
- [Notion integration token](https://www.notion.so/my-integrations) + a Leads database
- [Anthropic API key](https://console.anthropic.com/) (for morning briefing + AI features)
- Telegram bot token (optional, for `telegram_bot.py`)

---

## Install

### One-liner (recommended)

```bash
curl -sSL https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/install.sh | bash
```

This clones the repo, installs dependencies, and creates your secrets template files.

### Manual install

```bash
git clone https://github.com/iliaslaguir/agentlyfe-system.git
cd agentlyfe-system
pip install -r requirements.txt
cp configs/secrets/notion.env.example configs/secrets/notion.env
cp configs/secrets/anthropic_key.txt.example configs/secrets/anthropic_key.txt
mkdir -p outputs state masters inputs
```

---

## Setup

### 1. Fill in your API keys

Edit `configs/secrets/notion.env`:

```env
NOTION_TOKEN=secret_...
NOTION_LEADS_DB_ID=your-database-id
TELEGRAM_TOKEN=your-bot-token          # optional
TELEGRAM_CHAT_ID=your-chat-id          # optional
GOOGLE_PLACES_API_KEY=your-key
```

Edit `configs/secrets/anthropic_key.txt`:

```
sk-ant-your-key-here
```

### 2. Generate a country config

```bash
python3 scripts/config_generator.py us
```

This creates `configs/us.json` with a city list and niche keywords. Edit the cities array to target the areas you want.

See `configs/example_country.json` for the config structure.

---

## Workflow

```
generate config → scrape niche → sync to Notion → morning briefing → outreach
```

```bash
# 1. Generate config for your target country
python3 scripts/config_generator.py us

# 2. Scrape 3 cities of roofers
python3 scripts/ops_router.py scrape roofers 3 us

# 3. Sync A/B leads to Notion
python3 scripts/ops_router.py sync roofers us notion

# 4. Run morning briefing
python3 scripts/morning_briefing.py

# 5. Check scrape progress
python3 scripts/ops_router.py where us
```

---

## Script Reference

### `scripts/ops_router.py` — Main CLI
The entry point for all commands.

```bash
python3 scripts/ops_router.py scrape <niche> <n> <country>   # scrape n cities
python3 scripts/ops_router.py sync <niche> <country> notion  # sync to Notion
python3 scripts/ops_router.py where <country>                 # scrape progress
python3 scripts/ops_router.py summary <country>              # lead quality summary
python3 scripts/ops_router.py next <country>                 # suggest next niche
python3 scripts/ops_router.py ask "your question"            # AI assistant
```

---

### `scripts/scraper.py` — Google Places Scraper
Searches Google Places for local businesses, scores each lead, and outputs a CSV.

**Priority scoring:**
- **A+** — has website + running paid ads (Meta/Google) + 5+ reviews
- **A** — has website + 5+ reviews, no ads detected
- **B** — has website but <5 reviews, or no website but has ads
- **C** — no website, no ads

```bash
# Individual download
curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/scripts/scraper.py

# Run directly
python3 scripts/scraper.py --config configs/us.json --niche roofers --next 3
```

---

### `scripts/sync_ab_to_notion.py` — Notion Sync
Pushes A/B priority leads from CSV outputs into your Notion Leads database.

```bash
curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/scripts/sync_ab_to_notion.py

python3 scripts/sync_ab_to_notion.py --config configs/us.json --niche roofers
```

---

### `scripts/telegram_bot.py` — Telegram Bot Interface
Run scrapes, check status, and get notifications from your phone.

```bash
curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/scripts/telegram_bot.py

python3 scripts/telegram_bot.py
```

**Commands (in Telegram):**
```
/scrape roofers 3 us
/sync roofers us notion
/where us
/summary us
/next us
/briefing
```

---

### `scripts/morning_briefing.py` — Daily AI Briefing
Reads your Notion pipeline and generates a prioritized daily action plan using Claude.

```bash
curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/scripts/morning_briefing.py

python3 scripts/morning_briefing.py
```

---

### `scripts/notion_sync_manager.py` — Sync State Manager
Tracks which leads have been synced to avoid duplicates.

---

### `scripts/config_generator.py` — Country Config Generator
Generates a `configs/{country}.json` with city lists and niche keywords for any country.

```bash
curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/scripts/config_generator.py

python3 scripts/config_generator.py us     # generate US config
python3 scripts/config_generator.py uk     # generate UK config
python3 scripts/config_generator.py all    # generate all countries
```

---

### `scripts/email_discovery.py` — Email Finder
Finds contact email addresses for leads in your CSV outputs.

```bash
curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/scripts/email_discovery.py
```

---

### `scripts/market_prep.py` — Market Analysis
Analyses a country config and suggests which niches and cities to target first.

```bash
python3 scripts/market_prep.py --config configs/us.json
```

---

### `scripts/add_lead.py` — Manual Lead Entry
Manually add a lead to your Notion database without scraping.

```bash
curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/scripts/add_lead.py
```

---

### `scripts/scrape_completion_notify.py` — Completion Notifier
Watches a running scrape process and sends a Telegram summary when it finishes. Launched automatically by `telegram_bot.py`.

---

### `scripts/backfill_tz_tier.py` — Timezone Backfill
One-time script to backfill Timezone and City Tier properties on existing Notion leads.

```bash
python3 scripts/backfill_tz_tier.py
```

---

### `scripts/dashboard.py` — Local Web Dashboard
Flask-based dashboard showing scrape progress and lead stats. Opens in browser.

```bash
python3 scripts/dashboard.py
# → http://localhost:5000
```

---

### `scripts/create_deal.py` / `scripts/fill_deal.py` — Deal Management
Create and fill deal records in Notion when a prospect converts.

---

## Individual Script Downloads

Copy-paste any of these into your terminal to grab a single script:

```bash
# Scraper
curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/scripts/scraper.py

# Notion sync
curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/scripts/sync_ab_to_notion.py

# Telegram bot
curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/scripts/telegram_bot.py

# Morning briefing
curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/scripts/morning_briefing.py

# Config generator
curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/scripts/config_generator.py

# Email discovery
curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/scripts/email_discovery.py

# Main CLI router
curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/scripts/ops_router.py

# Dashboard
curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/scripts/dashboard.py
```

---

## OpenClaw vs Standalone

| | Standalone | OpenClaw |
|---|---|---|
| Run scripts | ✅ CLI | ✅ CLI + Telegram |
| Telegram bot | ✅ Run manually | ✅ Managed service |
| Scheduling | Manual cron | Built-in |
| Claude Code | ✅ Works with CLAUDE.md | ✅ Native |

Both work. OpenClaw ([openclaw.io](https://openclaw.io)) is a managed runtime that adds process supervision, scheduling, and multi-agent orchestration on top of these scripts.

---

## Directory Structure

```
agentlyfe-system/
├── scripts/          Python scripts (the core system)
├── configs/          Country configs + city metadata
│   └── secrets/      API keys (gitignored — fill in yourself)
├── agents/           AI agent role prompts
├── outputs/          Scraped CSV files (gitignored)
├── state/            Scrape progress state (gitignored)
├── masters/          City master lists (gitignored)
├── CLAUDE.md         Claude Code context file
├── COMMANDS.md       Full command reference
└── install.sh        One-line installer
```

---

## Support

- 🎥 YouTube: [@iliaslaguir](https://www.youtube.com/@iliaslaguir)
- 💬 Skool community: [link]
- 🆓 Notion freebies: [link]
