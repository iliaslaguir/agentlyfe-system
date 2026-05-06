#!/usr/bin/env python3
"""
Universal Config Generator
Usage:
  python3 config_generator.py <country> "<offer description>"
  python3 config_generator.py us "AI receptionists for dental clinics"
  python3 config_generator.py spain "Free website + monthly marketing for trades"

If no offer is given, reads `offer` from configs/business_context.json,
or falls back to the legacy "free website for trades" default.

Claude analyses the offer, decides ideal customer profile, and generates:
  - target verticals (niches) for that offer
  - cities / regions that fit
  - search keywords per vertical (in local language)
  - pitch angle the cold-email/call generator can re-use later
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
CONTEXT_FILE    = CONFIGS / "business_context.json"
DROPBOX_AB = Path.home() / "Dropbox" / "leads_ab"

COUNTRY_NAMES = {
    "us": "United States", "au": "Australia", "ca": "Canada",
    "ie": "Ireland", "nz": "New Zealand", "uk": "United Kingdom",
    "fi": "Finland",
}
COUNTRY_SUFFIXES = {
    "us": "USA", "au": "Australia", "ca": "Canada",
    "ie": "Ireland", "nz": "New Zealand", "uk": "UK", "fi": "Finland",
}

DEFAULT_OFFER = "Free website build for small local trade businesses with no/bad website, then a monthly marketing retainer."


def _resolve_country_name(code: str) -> str:
    return COUNTRY_NAMES.get(code, code.replace("_", " ").title())


def _resolve_country_suffix(code: str) -> str:
    return COUNTRY_SUFFIXES.get(code, _resolve_country_name(code))


def _load_offer_from_context() -> str:
    if CONTEXT_FILE.exists():
        try:
            ctx = json.loads(CONTEXT_FILE.read_text())
            if ctx.get("offer"):
                return ctx["offer"]
        except Exception:
            pass
    return DEFAULT_OFFER


SYSTEM = """You are a lead-generation strategist.

You are given an OFFER (what the user is selling) and a COUNTRY.
Your job: design the ideal go-to-market lead-gen config for THAT offer in THAT country.

Think first: who buys this offer? What kinds of businesses or individuals?
Then translate that into 5-9 concrete VERTICALS (niches) we can search for on Google Places.
Each vertical name must be a short snake_case identifier (e.g. "general_dentists", "med_spas",
"hvac_contractors") — usable in commands and filenames.

For each vertical, generate 3-5 Google Places search KEYWORDS in the local language and
terminology of the country. Always include "" (empty string) as the first keyword so the
vertical-name itself is used as a base search.

Pick 8-10 CITIES in the chosen country that maximise the value of this specific offer.
Logic depends on the offer:
  - For local services / website / marketing offers → affluent mid-size cities, owner-operated
    businesses, low-competition vs major metros.
  - For B2B SaaS / consulting → cities with the right industry density.
  - For consumer products → cities matching buyer demographics.
  Adapt — don't blindly default to UK trades cities.

Also produce a one-paragraph PITCH ANGLE that the cold-email generator will re-use later.
It should explain: what specific pain we hit, what we deliver, what's the ask, why now.
Keep it grounded in the offer the user described, not generic.

Respond with JSON only — no preamble, no markdown, no backticks."""


PROMPT_TEMPLATE = """Country: {country_name} ({country_code})
Offer: {offer}

Return ONLY this JSON:

{{
  "country_code": "{country_code}",
  "country_name": "{country_name}",
  "offer": "{offer_escaped}",
  "target_profile": "1-2 sentence description of the ideal buyer for this offer in {country_name}",
  "pitch_angle": "1 paragraph — pain we hit, what we deliver, ask, why now",
  "cities": [
    "City1 {country_suffix}",
    "City2 {country_suffix}"
  ],
  "niche_keywords": {{
    "vertical_one": ["", "keyword2", "keyword3", "keyword4"],
    "vertical_two": ["", "keyword2", "keyword3", "keyword4"]
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


def generate_config_with_claude(country_code: str, offer: str) -> dict:
    api_key = ANTHROPIC_KEY_F.read_text().strip()
    country_name = _resolve_country_name(country_code)
    country_suffix = _resolve_country_suffix(country_code)

    prompt = PROMPT_TEMPLATE.format(
        country_code=country_code,
        country_name=country_name,
        country_suffix=country_suffix,
        offer=offer,
        offer_escaped=offer.replace('"', '\\"'),
    )

    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1500,
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

    with urllib.request.urlopen(req, timeout=45) as r:
        data = json.loads(r.read())

    raw = data["content"][0]["text"].strip()
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

    niches = list(config.get("niche_keywords", {}).keys())
    niche_progress = {n: {"completed_cities": [], "completed": False, "last_run": None} for n in niches}

    progress = {
        "country_code": country_code,
        "country_name": _resolve_country_name(country_code),
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "niche_progress": niche_progress
    }

    path.write_text(json.dumps(progress, indent=2))
    print(f"  Created progress file: {path}")
    return path


def init_output_dirs(country_code: str, config: dict) -> None:
    base = OUTPUTS / country_code
    base.mkdir(parents=True, exist_ok=True)

    niches = list(config.get("niche_keywords", {}).keys())
    dropbox_base = DROPBOX_AB / country_code
    for niche in niches:
        (dropbox_base / niche).mkdir(parents=True, exist_ok=True)

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


def update_business_context(offer: str, config: dict) -> None:
    """Save offer + pitch angle into business_context.json so other scripts can use them."""
    ctx = {}
    if CONTEXT_FILE.exists():
        try:
            ctx = json.loads(CONTEXT_FILE.read_text())
        except Exception:
            ctx = {}

    ctx["offer"] = offer
    ctx["target_profile"] = config.get("target_profile", "")
    ctx["pitch_angle"] = config.get("pitch_angle", "")
    ctx.setdefault("clients", {})
    ctx.setdefault("projects", {})
    ctx.setdefault("notes", [])
    ctx["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONTEXT_FILE.write_text(json.dumps(ctx, indent=2))
    print(f"  Saved offer + pitch angle to {CONTEXT_FILE.name}")


def print_summary(country_code: str, config: dict) -> None:
    print(f"\n{'='*60}")
    print(f"CONFIG READY: {config['country_name']} ({country_code.upper()})")
    print(f"{'='*60}")
    print(f"\nOffer:\n  {config.get('offer', '(none)')}")
    print(f"\nTarget profile:\n  {config.get('target_profile', '(none)')}")
    print(f"\nPitch angle:\n  {config.get('pitch_angle', '(none)')[:200]}...")
    print(f"\nCities ({len(config.get('cities', []))}):")
    for c in config.get('cities', []):
        print(f"  • {c}")
    niches = list(config.get('niche_keywords', {}).keys())
    print(f"\nVerticals ({len(niches)}):")
    for n in niches:
        kws = [k for k in config['niche_keywords'][n] if k][:3]
        print(f"  • {n}  ({', '.join(kws)})")
    print(f"\nReady to scrape. Run e.g.:")
    if niches:
        print(f"  python3 scripts/ops_router.py scrape {country_code} {niches[0]}")
    print(f"{'='*60}\n")


def generate(country_code: str, offer: str | None = None) -> None:
    country_code = country_code.lower().strip().replace(" ", "_")
    if not offer:
        offer = _load_offer_from_context()

    print(f"\nGenerating config for {_resolve_country_name(country_code)}...")
    print(f"  Offer: {offer[:120]}{'...' if len(offer) > 120 else ''}")
    print("  Asking Claude for ideal verticals, cities and keywords...")

    config = generate_config_with_claude(country_code, offer)

    print("  Initializing file structure...")
    init_output_dirs(country_code, config)
    init_master_file(country_code)
    init_progress_file(country_code, config)
    save_config(country_code, config)
    update_business_context(offer, config)

    print_summary(country_code, config)


def generate_all(offer: str | None = None) -> None:
    countries = list(COUNTRY_NAMES.keys())
    print(f"Generating configs for: {', '.join(countries)}\n")
    for country_code in countries:
        generate(country_code, offer)
        print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print('  python3 config_generator.py <country> "<offer>"')
        print('  python3 config_generator.py us "AI receptionists for dental clinics"')
        print('  python3 config_generator.py all "..."   # all countries')
        sys.exit(1)

    arg = sys.argv[1].lower()
    offer_arg = " ".join(sys.argv[2:]).strip() or None

    if arg == "all":
        generate_all(offer_arg)
    else:
        generate(arg, offer_arg)
