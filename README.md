# Agentlyfe — Universal Lead Generation System

Built by [Ilias Laguir](https://www.youtube.com/@iliaslaguir).

A one-command lead-gen system that works for **any offer**, not just websites.
Tell it what you sell, pick a country, and it designs your entire pipeline:
the verticals to target, the cities to search, the keywords to use,
the scoring rubric that buckets leads into A/B/C, and the cold-email pitch
angle. Then it scrapes Google Places, scores every lead against your offer,
and exports priority leads to CSV / Notion.

```
   █████  ██████  ███████ ███    ██ ████████ ██   ██   ██ ███████ ███████
  ██   ██ ██      ██      ████   ██    ██    ██    ██ ██  ██      ██
  ███████ ██  ███ █████   ██ ██  ██    ██    ██     ███   █████   █████
  ██   ██ ██   ██ ██      ██  ██ ██    ██    ██      ██   ██      ██
  ██   ██  ██████ ███████ ██   ████    ██    ██████  ██   ██      ███████
```

---

## Quick Start

### One-line install
```bash
curl -sSL https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/install.sh | bash
```

The installer walks you through every API key with links + step-by-step
instructions (no jargon), then asks what you're selling and where, and
auto-generates your config.

### Try without installing for real (test mode)
```bash
bash <(curl -sSL https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/install.sh) --test
```
Routes everything to `/tmp/agentlyfe-test-<pid>/` — kick the tires, then
`rm -rf /tmp/agentlyfe-test-<pid>` to leave zero residue.

---

## How it works

```
You: "I sell luxury saunas to high-end hotels and resorts in Spain"
                            ↓
config_generator.py asks Claude to design:
  • verticals     — luxury_hotels, wellness_resorts, golf_clubs, ...
  • cities        — Marbella, Ibiza, Madrid, Barcelona, ...
  • keywords      — Spanish & English search terms
  • pitch angle   — saved for cold-email generation
  • scoring rubric — what makes a hot lead vs cold (offer-aware)
                            ↓
scraper.py hits Google Places → for each business:
  • check website (does it exist? what does it say?)
  • check Google Places types (lodging? spa? gym?)
  • score against your rubric → A+ / A / B / C
                            ↓
                  CSV + Notion + cold emails
```

The scoring rubric lives in `configs/scoring_rubric.json` — plain JSON
you can hand-edit any time. No restart, no code changes.

---

## Use cases

### Full system (my Skool community runs on this)
The whole pipeline — scraper, Notion sync, Telegram bot, daily briefings,
deal manager. One install, then `python3 scripts/ops_router.py scrape <country> <vertical>`
or message your Telegram bot.

### Individual scripts (Notion freebies)
Every script is self-contained and curl-downloadable for use in other
projects:

```bash
# Just the scraper
curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/scripts/scraper.py

# Just the email finder
curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/scripts/email_discovery.py

# Just the offer-aware scoring module
curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/scripts/_scoring.py

# Just the Telegram bot
curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/scripts/telegram_bot.py
```

### Quick API-key setup (without cloning)
```bash
curl -sSL https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/setup_keys.sh | bash
```

---

## API keys you'll need

| Key | What it does | Get it at | Cost |
|---|---|---|---|
| Anthropic | Generates rubric, writes cold emails, daily briefings | [console.anthropic.com](https://console.anthropic.com/settings/keys) | $5 lasts months |
| Google Places | Finds the businesses | [console.cloud.google.com](https://console.cloud.google.com/apis/library/places.googleapis.com) | $200 free/month |
| Notion (optional) | CRM for scraped leads | [notion.so/my-integrations](https://www.notion.so/my-integrations) | Free |
| Telegram (optional) | Mobile control | DM `@BotFather` in Telegram | Free |

The installer walks you through each one with exact URLs and ~2-5 min instructions.

---

## Editing your scoring rubric

After install, your offer-tailored rubric is at `configs/scoring_rubric.json`.
Open it in any text editor:

```json
{
  "tiers": [
    {
      "priority": "A",
      "label": "Hot — perfect-fit lead, no current solution visible",
      "signals": {
        "name_contains_any": ["hotel", "resort", "spa"],
        "name_contains_none": ["hostel", "budget"],
        "place_types_any": ["lodging", "spa"],
        "website_contains_none": ["sauna installed", "klafs", "tylo"]
      }
    },
    {
      "priority": "B", "label": "Warm",
      "signals": { "place_types_any": ["lodging", "gym"] }
    },
    {
      "priority": "C", "label": "Cold catch-all",
      "signals": {}
    }
  ]
}
```

**Identity signals** (`name_contains_any` + `place_types_any`) are OR-ed —
a lead matches if EITHER its name contains a keyword OR its Google Places
type matches. Disqualifiers (`*_contains_none`) are AND-ed — none may
appear. Catch-all = empty `signals: {}` at the bottom.

After editing, no restart needed. Next scrape picks it up.

---

## Where do my leads end up?

You pick the folder during install. Default is `~/agentlyfe-leads/`. Every
scrape produces two CSVs there, organised by country and vertical:

```
<your-leads-folder>/
└── us/
    └── general_dentists/
        ├── us_general_dentists_<timestamp>_share.csv   ← lean, share-ready
        └── us_general_dentists_<timestamp>_ab.csv      ← full schema (for Notion sync)
```

Three retrieval modes — pick whichever fits how you work:

1. **Local file** — open the CSV in Numbers / Excel / Google Sheets directly.
2. **Auto-sync to phone/laptop** — point the leads folder at a synced folder
   (e.g. `~/Dropbox/agentlyfe-leads`, `~/Library/Mobile Documents/com~apple~CloudDocs/agentlyfe-leads`,
   `~/Google Drive/agentlyfe-leads`) and the CSVs appear everywhere automatically.
3. **scp from a VPS** —
   ```bash
   scp clawd@your-vps:~/agentlyfe-leads/us/general_dentists/*.csv ~/Downloads/
   ```

Notion sync is **optional** — the CSVs always exist whether or not you connect Notion.

To change the folder later: edit `configs/leads_folder.txt` to a new absolute
path, or `export LEADS_FOLDER=/some/other/path` before running scripts.

---

## Common commands

```bash
# Where am I in the pipeline
python3 scripts/ops_router.py where us

# Scrape next 3 cities for a vertical
python3 scripts/ops_router.py scrape spain luxury_hotels

# Scrape next 5 cities
python3 scripts/ops_router.py scrape spain luxury_hotels 5

# Suggest the next vertical to work on
python3 scripts/ops_router.py next us

# Sync new A/B leads to Notion
python3 scripts/ops_router.py sync luxury_hotels spain notion

# Add a single lead manually (Telegram bot uses this)
python3 scripts/ops_router.py add "Hotel Ritz, Madrid Spain, +34911234567"

# Ask the assistant a question (uses your offer + pipeline state as context)
python3 scripts/ops_router.py ask "what's my best move today?"
```

---

## Folder structure

```
agentlyfe-system/
├── install.sh                      ← installer wizard
├── setup_keys.sh                   ← key-only setup (for individual scripts)
├── configs/
│   ├── scoring_rubric.json         ← edit this to tune A/B/C scoring
│   ├── business_context.json       ← your offer + pitch angle
│   ├── secrets/                    ← API keys (gitignored)
│   └── <country>.json              ← per-country verticals + cities
├── scripts/
│   ├── ops_router.py               ← main entrypoint
│   ├── config_generator.py         ← runs Claude to design new country config
│   ├── scraper.py                  ← Google Places scraper
│   ├── _scoring.py                 ← offer-aware lead scorer
│   ├── _secrets.py                 ← loads keys from configs/secrets/
│   ├── _niches.py                  ← dynamic niche/country resolver
│   ├── add_lead.py                 ← manually add one lead
│   ├── email_discovery.py          ← find contact emails
│   ├── notion_sync_manager.py      ← sync leads to Notion
│   ├── telegram_bot.py             ← Telegram control surface
│   ├── morning_briefing.py         ← daily AI briefing
│   ├── dashboard.py                ← web dashboard
│   └── ...
├── outputs/                        ← per-country scrape CSVs
├── state/                          ← scrape progress per country
└── masters/                        ← deduplication keys per country
```

---

## License

MIT — use it, fork it, sell systems built on top of it.

---

## Support

- Skool community (walkthroughs, troubleshooting, build-along)
- YouTube: [@iliaslaguir](https://www.youtube.com/@iliaslaguir)
- Issues / PRs: [github.com/iliaslaguir/agentlyfe-system](https://github.com/iliaslaguir/agentlyfe-system)
