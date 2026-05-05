"""Backfill Timezone + City Tier on existing US leads in Notion.

Reads configs/us_city_meta.json, queries the Leads DB for US leads, and patches
each page whose Timezone or City Tier is empty. Safe to re-run.
"""
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / "configs" / "secrets" / "notion.env"
META_FILE = ROOT / "configs" / "us_city_meta.json"
NOTION_VERSION = "2022-06-28"

TZ_LABEL = {
    "America/New_York": "Eastern",
    "America/Chicago": "Central",
    "America/Denver": "Mountain",
    "America/Phoenix": "Mountain",
    "America/Los_Angeles": "Pacific",
}


def load_env() -> None:
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def city_lookup() -> dict:
    raw = json.loads(META_FILE.read_text()).get("cities", {})
    # Build a normalized map: first-token lowercase -> meta, plus exact match
    out = {}
    for city, meta in raw.items():
        out[city.lower()] = meta
        out[city.split()[0].lower()] = meta
    return out


def match_city(city_value: str, lut: dict) -> dict:
    if not city_value:
        return {}
    v = city_value.lower().strip()
    if v in lut:
        return lut[v]
    first = v.split()[0] if v else ""
    return lut.get(first, {})


def query_us_leads(db_id: str):
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    payload = {
        "filter": {
            "property": "Country",
            "select": {"equals": "us"},
        },
        "page_size": 100,
    }
    while True:
        r = requests.post(url, headers=headers(), json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        for p in data.get("results", []):
            yield p
        if not data.get("has_more"):
            return
        payload["start_cursor"] = data["next_cursor"]


def patch_page(page_id: str, props: dict) -> None:
    url = f"https://api.notion.com/v1/pages/{page_id}"
    r = requests.patch(url, headers=headers(), json={"properties": props}, timeout=30)
    if r.status_code >= 300:
        print(f"  FAIL {page_id}: {r.status_code} {r.text[:200]}")
    else:
        print(f"  OK   {page_id}")


def get_prop(page: dict, name: str) -> dict:
    return page.get("properties", {}).get(name, {}) or {}


def text_of(prop: dict) -> str:
    if prop.get("type") == "rich_text":
        parts = prop.get("rich_text", [])
        return "".join(x.get("plain_text", "") for x in parts).strip()
    if prop.get("type") == "title":
        parts = prop.get("title", [])
        return "".join(x.get("plain_text", "") for x in parts).strip()
    return ""


def select_of(prop: dict) -> str:
    s = prop.get("select")
    return (s or {}).get("name", "") if s else ""


def main():
    load_env()
    db_id = os.environ["NOTION_LEADS_DB_ID"]
    lut = city_lookup()

    updated = skipped = 0
    for page in query_us_leads(db_id):
        city = text_of(get_prop(page, "City"))
        meta = match_city(city, lut)
        if not meta:
            skipped += 1
            continue

        desired_tz = TZ_LABEL.get(meta.get("tz", ""), "")
        desired_tier = meta.get("tier", "")

        current_tz = select_of(get_prop(page, "Timezone"))
        current_tier = select_of(get_prop(page, "City Tier"))

        props = {}
        if desired_tz and current_tz != desired_tz:
            props["Timezone"] = {"select": {"name": desired_tz}}
        if desired_tier and current_tier != desired_tier:
            props["City Tier"] = {"select": {"name": desired_tier}}

        if not props:
            skipped += 1
            continue

        patch_page(page["id"], props)
        updated += 1
        time.sleep(0.1)  # be polite

    print(f"\nDone. Updated: {updated}  Skipped: {skipped}")


if __name__ == "__main__":
    main()
