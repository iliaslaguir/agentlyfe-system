#!/usr/bin/env python3
"""
OpenClaw Config Generator
Usage: python3 config_generator.py us
Generates a full country config using Claude, initializes master/progress/output files.
"""

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIGS         = ROOT / "configs"
MASTERS         = ROOT / "masters"
STATE           = ROOT / "state"
OUTPUTS         = ROOT / "outputs"
ANTHROPIC_KEY_F = CONFIGS / "secrets" / "anthropic_key.txt"
DROPBOX_AB = Path.home() / "Dropbox" / "leads_ab"

COUNTRY_NAMES = {
    "us": "United States",
    "au": "Australia",
    "ca": "Canada",
    "ie": "Ireland",
    "nz": "New Zealand",
    "uk": "United Kingdom",
    "fi": "Finland",
}

def _resolve_country_name(code: str) -> str:
    """Return full country name — uses lookup table or title-cases the code itself."""
    return COUNTRY_NAMES.get(code, code.replace("_", " ").title())

def _resolve_country_suffix(code: str) -> str:
    """Return the suffix used in Google Places queries (e.g. 'USA', 'UK', 'Germany')."""
    return COUNTRY_SUFFIXES.get(code, _resolve_country_name(code))

NICHES = ["builders", "electricians", "plumbers", "roofers", "hvac", "painters", "landscapers", "pest_control", "barbershops"]

SYSTEM = """You are a lead generation strategist for a digital marketing agency.

The agency's offer: Free website build for small trade businesses → €500 acceptance fee → monthly marketing retainer.

TARGET PROFILE:
- Small/solo trade businesses (1-10 employees), owner-operated
- High ticket per job: plumbers, roofers, electricians, HVAC, builders
- No website (Priority A) or bad website score under 60 (Priority B)
- Owner answers the phone directly — not a chain or franchise
- One job pays back the €500 site fee immediately

CITY SELECTION LOGIC (replicate exactly):
- Affluent mid-size cities (NOT major metros — too competitive, agencies dominate)
- High homeownership rates = high demand for tradespeople
- Wealthy enough that average job value is high (£/$/€1000-10000+)
- Small enough that most trade businesses are owner-operated
- Low enough digital adoption that many still have no/bad websites
- Examples of PERFECT UK cities: Bath, Harrogate, Winchester, Guildford, Canterbury, Cheltenham, York

KEYWORD LOGIC:
- Use local market terminology (US says "roofing contractor" not "roofer")
- Include emergency variants (high intent, owner-operated)
- Include residential variants (not commercial chains)
- 3-4 keywords per niche including empty string for base search

Respond ONLY with valid JSON, no preamble, no markdown, no backticks."""

PROMPT_TEMPLATE = """Generate a complete OpenClaw config for {country_name} ({country_code}).

Pick exactly 8-10 cities that best match our targeting criteria for {country_name}.
Use the correct local terminology for each niche in {country_name}.

Return ONLY this exact JSON structure (fill in the values):

{{
  "country_code": "{country_code}",
  "country_name": "{country_name}",
  "cities": [
    "City1 {country_suffix}",
    "City2 {country_suffix}"
  ],
  "niche_keywords": {{
    "builders": ["", "keyword2", "keyword3", "keyword4"],
    "electricians": ["", "keyword2", "keyword3", "keyword4"],
    "plumbers": ["", "keyword2", "keyword3", "keyword4"],
    "roofers": ["", "keyword2", "keyword3", "keyword4"],
    "hvac": ["", "keyword2", "keyword3", "keyword4"]
  }},
  "max_results_per_search": 20,
  "generate_email_for_priorities": ["A", "B"],
  "default_city_batch_size": 3,
  "master_file": "masters/{country_code}_master.txt",
  "progress_file": "state/{country_code}_progress.json",
  "output_dir": "outputs/{country_code}",
  "export_ab_only_to_dropbox": true,
  "dropbox_ab_base_dir": "~/Dropbox/leads_ab"
}}"""

COUNTRY_SUFFIXES = {
    "us": "USA",
    "au": "Australia",
    "ca": "Canada",
    "ie": "Ireland",
    "nz": "New Zealand",
    "uk": "UK",
    "fi": "Finland",
}


def generate_config_with_claude(country_code: str) -> dict:
    api_key = ANTHROPIC_KEY_F.read_text().strip()
    country_name = _resolve_country_name(country_code)
    country_suffix = _resolve_country_suffix(country_code)

    prompt = PROMPT_TEMPLATE.format(
        country_code=country_code,
        country_name=country_name,
        country_suffix=country_suffix,
    )

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

    # Strip markdown if Claude adds it despite instructions
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    return json.loads(raw)


def init_master_file(country_code: str) -> Path:
    path = MASTERS / f"{country_code}_master.txt"
    if not path.exists():
        path.touch()
        print(f"  Created master file: {path}")
    else:
        print(f"  Master file exists: {path} ({sum(1 for _ in path.open())} entries)")
    return path


def init_progress_file(country_code: str, config: dict) -> Path:
    path = STATE / f"{country_code}_progress.json"

    if path.exists():
        print(f"  Progress file exists: {path}")
        return path

    # Build empty progress structure matching UK format exactly
    niche_progress = {}
    for niche in NICHES:
        niche_progress[niche] = {
            "completed_cities": [],
            "completed": False,
            "last_run": None
        }

    progress = {
        "country_code": country_code,
        "country_name": COUNTRY_NAMES[country_code],
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "niche_progress": niche_progress
    }

    path.write_text(json.dumps(progress, indent=2))
    print(f"  Created progress file: {path}")
    return path


def init_output_dirs(country_code: str) -> None:
    base = OUTPUTS / country_code
    base.mkdir(parents=True, exist_ok=True)

    dropbox_base = DROPBOX_AB / country_code
    for niche in NICHES:
        niche_dir = dropbox_base / niche
        niche_dir.mkdir(parents=True, exist_ok=True)

    print(f"  Output dirs ready: {base}")
    print(f"  Dropbox dirs ready: {dropbox_base}")


def save_config(country_code: str, config: dict) -> Path:
    path = CONFIGS / f"{country_code}.json"

    if path.exists():
        backup = CONFIGS / f"{country_code}.json.bak"
        path.rename(backup)
        print(f"  Backed up existing config to {backup.name}")

    path.write_text(json.dumps(config, indent=2))
    print(f"  Config saved: {path}")
    return path


def print_summary(country_code: str, config: dict) -> None:
    print(f"\n{'='*50}")
    print(f"CONFIG READY: {config['country_name']} ({country_code.upper()})")
    print(f"{'='*50}")
    print(f"Cities ({len(config['cities'])}):")
    for c in config['cities']:
        print(f"  • {c}")
    print(f"\nNiches: {', '.join(config['niche_keywords'].keys())}")
    print(f"\nSample keywords:")
    for niche, kws in config['niche_keywords'].items():
        print(f"  {niche}: {[k for k in kws if k][:2]}")
    print(f"\nReady to scrape. Run:")
    print(f"  python3 ops_router.py scrape {country_code} builders")
    print(f"  python3 ops_router.py scrape {country_code} electricians")
    print(f"  python3 ops_router.py scrape {country_code} plumbers")
    print(f"  python3 ops_router.py scrape {country_code} roofers")
    print(f"  python3 ops_router.py scrape {country_code} hvac")
    print(f"{'='*50}\n")


def generate(country_code: str) -> None:
    country_code = country_code.lower().strip().replace(" ", "_")

    print(f"\nGenerating config for {_resolve_country_name(country_code)}...")
    print("  Asking Claude for best cities and keywords...")

    config = generate_config_with_claude(country_code)

    print("  Initializing file structure...")
    init_output_dirs(country_code)
    init_master_file(country_code)
    init_progress_file(country_code, config)
    save_config(country_code, config)

    print_summary(country_code, config)


def generate_all() -> None:
    countries = list(COUNTRY_NAMES.keys())
    print(f"Generating configs for: {', '.join(countries)}\n")
    for country_code in countries:
        generate(country_code)
        print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 config_generator.py us        # single country")
        print("  python3 config_generator.py all       # all countries")
        sys.exit(1)

    arg = sys.argv[1].lower()

    if arg == "all":
        generate_all()
    else:
        generate(arg)
