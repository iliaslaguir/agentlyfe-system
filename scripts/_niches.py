"""Shared helper: load the union of all niches across generated configs.

The system used to ship a hardcoded list of trade-business niches. After the
universal-offer pivot, niches are whatever Claude generated for the active
configs — could be 'general_dentists', 'med_spas', 'roofers', etc. depending
on what the user is selling.

Any script that needs to validate a niche token (router, telegram bot, sync
manager, dashboard) imports `niches()` to get the current set.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIGS = ROOT / "configs"

# Legacy fallback — used only when no config files exist yet.
_FALLBACK = {
    "builders", "electricians", "plumbers", "roofers", "hvac",
    "painters", "landscapers", "pest_control", "barbershops",
}


def niches() -> set[str]:
    """Union of all niche keys across configs/{country}.json files."""
    found: set[str] = set()
    if not CONFIGS.exists():
        return _FALLBACK
    for path in CONFIGS.glob("*.json"):
        if path.name in {"business_context.json", "dashboard_state.json"}:
            continue
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict) and isinstance(data.get("niche_keywords"), dict):
                found.update(data["niche_keywords"].keys())
        except Exception:
            continue
    return found or _FALLBACK


def countries() -> set[str]:
    """Codes for every config file present."""
    found: set[str] = set()
    if not CONFIGS.exists():
        return set()
    for path in CONFIGS.glob("*.json"):
        if path.name in {"business_context.json", "dashboard_state.json"}:
            continue
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict) and data.get("country_code"):
                found.add(data["country_code"])
        except Exception:
            continue
    return found
