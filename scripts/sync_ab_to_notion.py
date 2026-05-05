import csv
import os
import re
from pathlib import Path
from typing import Dict, Iterable, Optional

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / "configs" / "secrets" / "notion.env"
NOTION_VERSION = "2022-06-28"
US_CITY_META_FILE = ROOT / "configs" / "us_city_meta.json"

_TZ_LABEL = {
    "America/New_York": "Eastern",
    "America/Chicago": "Central",
    "America/Denver": "Mountain",
    "America/Phoenix": "Mountain",
    "America/Los_Angeles": "Pacific",
}


def _load_us_city_meta() -> Dict[str, Dict[str, str]]:
    import json
    if not US_CITY_META_FILE.exists():
        return {}
    try:
        return json.loads(US_CITY_META_FILE.read_text()).get("cities", {})
    except Exception:
        return {}


_US_CITY_META_CACHE: Optional[Dict[str, Dict[str, str]]] = None


def lookup_city_meta(city: str, country: str) -> Dict[str, str]:
    """Return {'timezone': ..., 'tier': ...} for a US city, else empty dict."""
    global _US_CITY_META_CACHE
    if country.lower() != "us" or not city:
        return {}
    if _US_CITY_META_CACHE is None:
        _US_CITY_META_CACHE = _load_us_city_meta()
    # Try exact match, then prefix match (handles "Richmond Virginia USA" variants)
    meta = _US_CITY_META_CACHE.get(city)
    if not meta:
        for k, v in _US_CITY_META_CACHE.items():
            if city.lower().startswith(k.split()[0].lower()) and k in _US_CITY_META_CACHE:
                meta = v
                break
    if not meta:
        return {}
    return {
        "timezone": _TZ_LABEL.get(meta.get("tz", ""), ""),
        "tier": meta.get("tier", ""),
    }


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


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value


def normalize_phone(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def normalize_website(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = value.rstrip("/")
    return value


def build_lead_key(row: Dict[str, str]) -> str:
    name = slugify(row_value(row, "name", "business_name", "Business Name"))
    website = normalize_website(row_value(row, "website"))
    phone = normalize_phone(row_value(row, "phone"))
    city = slugify(row_value(row, "city"))

    if website:
        return f"{name}|{website}"
    if phone:
        return f"{name}|{phone}"
    return f"{name}|{city}"


def query_existing_keys_and_names(database_id: str) -> tuple[set[str], set[str]]:
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    keys = set()
    names = set()
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
            props = row.get("properties", {})

            title_prop = props.get("Business Name", {})
            title_items = title_prop.get("title", [])
            if title_items:
                name = "".join(part.get("plain_text", "") for part in title_items).strip()
                if name:
                    names.add(name.lower())

            lead_key_prop = props.get("Lead Key", {})
            rt_items = lead_key_prop.get("rich_text", [])
            if rt_items:
                key = "".join(part.get("plain_text", "") for part in rt_items).strip()
                if key:
                    keys.add(key)

        has_more = data.get("has_more", False)
        next_cursor = data.get("next_cursor")

    return keys, names


def text_prop(value: str) -> Dict:
    return {"rich_text": [{"type": "text", "text": {"content": value[:2000]}}]} if value else {"rich_text": []}


def title_prop(value: str) -> Dict:
    return {"title": [{"type": "text", "text": {"content": value[:2000]}}]}


def select_prop(value: str) -> Dict:
    return {"select": {"name": value}} if value else {"select": None}


def checkbox_prop(value: bool) -> Dict:
    return {"checkbox": bool(value)}


def phone_prop(value: str) -> Dict:
    return {"phone_number": value or None}


def url_prop(value: str) -> Dict:
    return {"url": value or None}


def email_prop(value: str) -> Dict:
    return {"email": value or None}


def number_prop(value: Optional[str]) -> Dict:
    if value in (None, "", "None"):
        return {"number": None}
    try:
        return {"number": float(value)}
    except ValueError:
        return {"number": None}


def _ads_props(row: Dict[str, str]) -> Dict:
    """
    Optional ad-signal fields. Returns empty dict if values are absent,
    so sync works on old CSVs that predate this feature and on Notion DBs
    that haven't had these properties added yet.
    """
    props = {}
    try:
        ads_raw = str(row.get("ads_detected", "")).lower()
        if ads_raw in ("true", "false"):
            props["Ads Detected"] = checkbox_prop(ads_raw == "true")
        if row.get("pixel_types"):
            props["Pixel Types"] = text_prop(str(row["pixel_types"])[:200])
        cta_q = row.get("cta_quality", "")
        if cta_q != "":
            props["CTA Quality"] = number_prop(cta_q)
        if row.get("cta_issues"):
            props["CTA Issues"] = text_prop(str(row["cta_issues"])[:200])
        if row.get("meta_ads_url"):
            props["Meta Ads URL"] = url_prop(str(row["meta_ads_url"]))
        if row.get("google_ads_url"):
            props["Google Ads URL"] = url_prop(str(row["google_ads_url"]))
    except Exception:
        pass
    return props


def build_properties(row: Dict[str, str]) -> Dict:
    business_name = row_value(row, "name", "business_name", "Business Name")
    priority = row_value(row, "priority")
    niche = row_value(row, "niche")
    city = row_value(row, "city")
    country = row_value(row, "country_code", "country") or "uk"
    phone = row_value(row, "phone")
    website = row_value(row, "website")
    maps_url = row_value(row, "maps_url", "google_maps_url")
    issue = row_value(row, "issue", "problem")
    email_draft = row_value(row, "email_draft", "email_text")
    source = row_value(row, "search_term", "source")
    website_score = row_value(row, "website_score")
    lead_key = build_lead_key(row)

    outreach_channel = row_value(row, "outreach_channel")
    email_found = row_value(row, "email_found", "email")
    email_status = row_value(row, "email_status")
    contact_page_url = row_value(row, "contact_page_url")
    email_discovery_stage = row_value(row, "email_discovery_stage")

    return {
        "Business Name": title_prop(business_name),
        "Lead Key": text_prop(lead_key),
        "Priority": select_prop(priority),
        "Stage": {"status": {"name": "New"}},
        "CALL BUCKET": select_prop("None"),
        "Call Priority": select_prop("Normal"),
        "Next Action": select_prop("Send First Message"),
        "Phone": phone_prop(phone),
        "Email": text_prop(email_found),
        "Website": url_prop(website),
        "Maps URL": url_prop(maps_url),
        "Niche": select_prop(niche),
        "Country": select_prop(country),
        "City": text_prop(city),
        "Industry": select_prop(niche),
        "Source": select_prop(source),
        "Issue": text_prop(issue),
        "Outreach Channel": select_prop(outreach_channel),
        "Email Found": email_prop(email_found),
        "Email Status": select_prop(email_status),
        "Contact Page URL": url_prop(contact_page_url),
        "Email Discovery Stage": select_prop(email_discovery_stage),
        "Email Draft": text_prop(email_draft),
        "Email Sent At": {"date": None},
        "Follow-Up Due": {"date": None},
        "Link Sent": checkbox_prop(False),
        "Paid": checkbox_prop(False),
        "Call Notes": text_prop(""),
        "Internal Notes": text_prop(""),
        "Website Score": number_prop(website_score),
        "Last Contacted": {"date": None},
        **_ads_props(row),
        **_live_ads_props(row),
        **_tz_tier_props(city, country),
        **_review_props(row),
    }


def _tz_tier_props(city: str, country: str) -> Dict:
    meta = lookup_city_meta(city, country)
    props: Dict = {}
    if meta.get("timezone"):
        props["Timezone"] = select_prop(meta["timezone"])
    if meta.get("tier"):
        props["City Tier"] = select_prop(meta["tier"])
    return props


def _review_props(row: Dict[str, str]) -> Dict:
    props: Dict = {}
    rc = row.get("review_count", "")
    if rc != "" and rc is not None:
        try:
            props["Review Count"] = {"number": int(float(rc))}
        except (ValueError, TypeError):
            pass
    return props


def _live_ads_props(row: Dict[str, str]) -> Dict:
    """
    Optional live-ad fields. Returns empty dict if values are absent,
    so sync works on old CSVs and Notion DBs that don't have these properties yet.
    """
    props = {}
    try:
        live_raw = str(row.get("live_ads_found", "")).lower()
        if live_raw in ("true", "false"):
            props["Live Ads Found"] = checkbox_prop(live_raw == "true")
        if row.get("live_ad_platforms"):
            props["Live Ad Platforms"] = text_prop(str(row["live_ad_platforms"])[:200])
        if row.get("ad_copy_sample"):
            props["Ad Copy Sample"] = text_prop(str(row["ad_copy_sample"])[:500])
        ad_score = row.get("ad_score", "")
        if ad_score != "":
            props["Ad Score"] = number_prop(ad_score)
        if row.get("ad_weaknesses"):
            props["Ad Weaknesses"] = text_prop(str(row["ad_weaknesses"])[:500])
    except Exception:
        pass
    return props


_OPTIONAL_PROPS = {
    "Ads Detected", "Pixel Types", "CTA Quality", "CTA Issues",
    "Live Ads Found", "Live Ad Platforms", "Ad Copy Sample", "Ad Score", "Ad Weaknesses",
    "Meta Ads URL", "Google Ads URL",
}

def create_page(database_id: str, props: Dict) -> None:
    url = "https://api.notion.com/v1/pages"
    payload = {
        "parent": {"database_id": database_id},
        "properties": props,
    }
    resp = requests.post(url, headers=notion_headers(), json=payload, timeout=30)
    if resp.status_code == 400 and "is not a property that exists" in resp.json().get("message", ""):
        # Notion DB doesn't have the optional ad-signal properties yet — strip and retry
        for key in _OPTIONAL_PROPS:
            props.pop(key, None)
        resp = requests.post(url, headers=notion_headers(), json=payload, timeout=30)
    resp.raise_for_status()


def iter_ab_rows(csv_path: Path) -> Iterable[Dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("priority") in {"A", "A+", "B"}:
                yield row


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Path to CSV file containing leads")
    args = parser.parse_args()

    load_env_file(ENV_FILE)

    database_id = normalize_db_id(os.environ["NOTION_LEADS_DB_ID"])
    csv_path = Path(args.csv)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    existing_keys, existing_names = query_existing_keys_and_names(database_id)
    inserted = 0
    skipped = 0

    for row in iter_ab_rows(csv_path):
        business_name = row_value(row, "name", "business_name", "Business Name").strip()
        if not business_name:
            skipped += 1
            continue

        lead_key = build_lead_key(row)
        if lead_key in existing_keys or business_name.lower() in existing_names:
            skipped += 1
            continue

        props = build_properties(row)
        create_page(database_id, props)
        existing_keys.add(lead_key)
        existing_names.add(business_name.lower())
        inserted += 1

    print(f"Inserted: {inserted}")
    print(f"Skipped: {skipped}")


if __name__ == "__main__":
    main()
