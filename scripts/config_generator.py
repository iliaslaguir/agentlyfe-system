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
import os
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

# Leads-folder resolution lives in _paths.py — honors install-time choice,
# env var override, and back-compat with old ~/Dropbox/leads_ab installs.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import leads_folder as _leads_folder
DROPBOX_AB = _leads_folder()

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

You also produce a SCORING RUBRIC tailored to this specific offer.
The rubric decides whether a scraped business is priority A (hot), B (warm), or C (cold).
A lead is hot when their pain is acute and our offer is an obvious fit.
A lead is cold when they already have a competing solution, are too small/big to care,
or otherwise don't fit our buyer profile.

The rubric is applied to lead data via simple deterministic checks
(no per-lead Claude calls), so signals must be concrete keywords, place-type strings,
website-content terms, review-count thresholds, etc.

Think first: who buys this offer? What kinds of businesses?
Then translate that into 5-9 concrete VERTICALS (niches) we can search for on Google Places.
Each vertical name must be a short snake_case identifier (e.g. "general_dentists", "med_spas").

For each vertical, generate 3-5 Google Places search KEYWORDS in the local language and
terminology of the country. Always include "" (empty string) as the first keyword.

Pick 8-10 CITIES that maximise the value of THIS specific offer in THAT country.

Produce a one-paragraph PITCH ANGLE the cold-email generator will reuse.

Respond with JSON only — no preamble, no markdown, no backticks."""


PROMPT_TEMPLATE = """Country: {country_name} ({country_code})
Offer: {offer}

Return ONLY this JSON. Replace every placeholder with concrete values for THIS offer.

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
  "dropbox_ab_base_dir": "~/Dropbox/leads_ab",
  "scoring_rubric": {{
    "instructions": "Edit this rubric to tune how leads bucket into A/B/C. Tiers checked top-to-bottom; the first tier whose ALL signals pass wins. Empty signals always pass — useful for a catch-all C bucket. After editing, no restart needed.",
    "tiers": [
      {{
        "priority": "A",
        "label": "Hot — short reason matching THIS offer",
        "signals": {{
          "name_contains_any": ["specific words a hot lead's name often contains"],
          "name_contains_none": ["words that disqualify (chain names, hostels, etc.)"],
          "place_types_any": ["lodging", "spa"],
          "website_required": null,
          "website_score_min": null,
          "website_score_max": null,
          "website_contains_any": [],
          "website_contains_none": ["evidence they ALREADY have what we sell"],
          "min_review_count": 0
        }}
      }},
      {{
        "priority": "B",
        "label": "Warm — short reason matching THIS offer",
        "signals": {{
          "name_contains_any": [],
          "website_contains_any": [],
          "website_contains_none": []
        }}
      }},
      {{
        "priority": "C",
        "label": "Cold — already has the solution we sell, or wrong fit",
        "signals": {{}}
      }}
    ]
  }}
}}

Rules for scoring_rubric — read carefully, this is what makes the rubric ACTUALLY work:

- Tier identity (name_contains_any + place_types_any) is OR-ed at runtime: a lead
  matches if EITHER its name has the keywords OR its Google Places type matches.
  So you don't need to make `name_contains_any` exhaustive — picking the right
  Google Places types like "lodging", "spa", "gym", "dentist", "lawyer", etc.
  catches chains that don't contain category words in their names.
- Keep `website_contains_any` MINIMAL or empty. Homepage HTML is only the first
  5000 chars and often lacks specific marketing copy. Relying on positive
  website-content matches makes Tier A unreachable in practice. Prefer
  `website_contains_none` (negative signals — "they DON'T already have what we sell")
  which is the strongest possible "hot lead" indicator.
- Tier A signals encode "perfect fit, no current solution visible". Use:
    name_contains_any / place_types_any  → identifies them as a target
    website_contains_none                → confirms they don't already have it
    (omit website_contains_any unless absolutely critical)
- Tier B signals encode "decent fit, partial or weaker current solution".
- Tier C is the catch-all, leave its signals empty {{}}.
- For website-pitch-style offers (selling websites/marketing), A=no website
  (`website_required: false`), B=bad website (`website_required: true, website_score_max: 60`).
- For non-website offers (saunas, AI tools, equipment, services), website existence
  is irrelevant — set `website_required: null` and rely on names+types+negative content.
- Use the OFFER to decide which signals matter."""


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

    today = datetime.now().strftime("%B %Y")
    system_with_date = (
        f"Today is {today}. If you reference a year in pitch language, use "
        f"{datetime.now().year} or later — never an earlier year.\n\n"
    ) + SYSTEM
    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 3000,
        "system": system_with_date,
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
    # Country config doesn't need to embed the rubric — it lives in its own file.
    config_to_save = {k: v for k, v in config.items() if k != "scoring_rubric"}
    path.write_text(json.dumps(config_to_save, indent=2))
    print(f"  Config saved: {path}")
    return path


def save_scoring_rubric(offer: str, config: dict) -> Path:
    """Save the offer-aware scoring rubric to its own file users can hand-edit."""
    rubric_path = CONFIGS / "scoring_rubric.json"
    rubric = config.get("scoring_rubric") or {}

    payload = {
        "offer": offer,
        "instructions": rubric.get(
            "instructions",
            "Edit this rubric to tune how leads bucket into A/B/C. Tiers are checked top-to-bottom; the first tier whose ALL signals pass wins. Empty signals always pass — useful for a catch-all. After editing, no restart needed.",
        ),
        "tiers": rubric.get("tiers", []),
    }

    if rubric_path.exists():
        backup = CONFIGS / "scoring_rubric.json.bak"
        rubric_path.rename(backup)
        print(f"  Backed up existing rubric to {backup.name}")

    rubric_path.write_text(json.dumps(payload, indent=2))
    print(f"  Scoring rubric saved: {rubric_path}")
    print(f"    (edit this file anytime to refine your A/B/C buckets)")
    return rubric_path


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
    rubric = config.get("scoring_rubric") or {}
    tiers = rubric.get("tiers") or []
    if tiers:
        print(f"\nScoring tiers (configs/scoring_rubric.json — edit anytime):")
        for t in tiers:
            print(f"  {t.get('priority', '?')}: {t.get('label', '')[:80]}")
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
    save_scoring_rubric(offer, config)
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
