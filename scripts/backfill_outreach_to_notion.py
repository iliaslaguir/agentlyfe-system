import csv
import os
from pathlib import Path
from typing import Dict, Iterable

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / "configs" / "secrets" / "notion.env"
NOTION_VERSION = "2022-06-28"


def load_env_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing env file: {path}")
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip()


def notion_headers() -> Dict[str, str]:
    token = os.environ["NOTION_TOKEN"]
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def normalize_db_id(raw: str) -> str:
    raw = raw.strip()
    if "-" in raw:
        return raw
    if len(raw) == 32:
        return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"
    return raw


def row_value(row: Dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def text_prop(value: str) -> Dict:
    return {"rich_text": [{"type": "text", "text": {"content": value[:2000]}}]} if value else {"rich_text": []}


def select_prop(value: str) -> Dict:
    return {"select": {"name": value}} if value else {"select": None}


def url_prop(value: str) -> Dict:
    return {"url": value or None}


def email_prop(value: str) -> Dict:
    return {"email": value or None}


def query_pages(database_id: str) -> tuple[dict[str, str], dict[str, str]]:
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    by_lead_key: dict[str, str] = {}
    by_name: dict[str, str] = {}
    has_more = True
    next_cursor = None

    while has_more:
        payload = {}
        if next_cursor:
            payload["start_cursor"] = next_cursor

        resp = requests.post(url, headers=notion_headers(), json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for row in data.get("results", []):
            page_id = row.get("id")
            props = row.get("properties", {})

            if not page_id:
                continue

            title_items = props.get("Business Name", {}).get("title", [])
            name = "".join(part.get("plain_text", "") for part in title_items).strip()
            if name:
                by_name[name.lower()] = page_id

            lead_key_items = props.get("Lead Key", {}).get("rich_text", [])
            lead_key = "".join(part.get("plain_text", "") for part in lead_key_items).strip()
            if lead_key:
                by_lead_key[lead_key] = page_id

        has_more = data.get("has_more", False)
        next_cursor = data.get("next_cursor")

    return by_lead_key, by_name


def update_page(page_id: str, props: Dict) -> None:
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {"properties": props}
    resp = requests.patch(url, headers=notion_headers(), json=payload, timeout=30)
    resp.raise_for_status()


def build_update_properties(row: Dict[str, str]) -> Dict:
    outreach_channel = row_value(row, "outreach_channel")
    email_found = row_value(row, "email_found", "email")
    email_status = row_value(row, "email_status")
    contact_page_url = row_value(row, "contact_page_url")
    email_discovery_stage = row_value(row, "email_discovery_stage")
    research_notes = row_value(row, "research_notes")

    return {
        "Outreach Channel": select_prop(outreach_channel),
        "Email Found": email_prop(email_found),
        "Email Status": select_prop(email_status),
        "Contact Page URL": url_prop(contact_page_url),
        "Email Discovery Stage": select_prop(email_discovery_stage),
        "Research Notes": text_prop(research_notes),
    }


def iter_ab_rows(csv_path: Path) -> Iterable[Dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("priority") in {"A", "B"}:
                yield row


def main() -> None:
    import argparse
    import importlib.util

    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Path to A/B CSV file")
    args = parser.parse_args()

    load_env_file(ENV_FILE)
    database_id = normalize_db_id(os.environ["NOTION_LEADS_DB_ID"])
    csv_path = Path(args.csv)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    sync_script = ROOT / "scripts" / "sync_ab_to_notion.py"
    spec = importlib.util.spec_from_file_location("syncmod", sync_script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    page_map_by_key, page_map_by_name = query_pages(database_id)

    updated = 0
    skipped = 0
    matched_by_key = 0
    matched_by_name = 0

    for row in iter_ab_rows(csv_path):
        business_name = row_value(row, "name", "business_name", "Business Name").strip()
        if not business_name:
            skipped += 1
            continue

        lead_key = mod.build_lead_key(row)
        page_id = page_map_by_key.get(lead_key)

        if page_id:
            matched_by_key += 1
        else:
            page_id = page_map_by_name.get(business_name.lower())
            if page_id:
                matched_by_name += 1

        if not page_id:
            skipped += 1
            continue

        props = build_update_properties(row)
        update_page(page_id, props)
        updated += 1

    print(f"Updated: {updated}")
    print(f"Skipped: {skipped}")
    print(f"Matched by Lead Key: {matched_by_key}")
    print(f"Matched by Name: {matched_by_name}")


if __name__ == "__main__":
    main()
