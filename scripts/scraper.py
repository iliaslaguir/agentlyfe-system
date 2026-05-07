import argparse
import csv
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, quote as url_quote

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _secrets import load_secrets
load_secrets()

import anthropic
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
LEGACY_KEYS_FILE = ROOT / "scripts" / "scraper.py.bak"


def load_legacy_key(name: str):
    if not LEGACY_KEYS_FILE.exists():
        return None
    text = LEGACY_KEYS_FILE.read_text()
    match = re.search(rf'^{name}\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else None


GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or load_legacy_key("GOOGLE_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or load_legacy_key("ANTHROPIC_API_KEY")



EMAIL_RE = re.compile(r'([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})', re.I)
CONTACT_HINTS = ["contact", "about", "team", "reach", "get-in-touch"]

# ── EMAIL VALIDATION ──────────────────────────────────────
_BAD_TLDS = {
    'jpg','jpeg','png','gif','webp','svg','ico','bmp','pdf','js','css',
    'php','html','htm','xml','json','woff','woff2','ttf','eot','mp4',
    'mp3','zip','tar','gz','exe','dmg','apk',
}
_BAD_LOCAL = {
    'noreply','no-reply','donotreply','do-not-reply','bounce','mailer-daemon',
    'postmaster','abuse','spam','unsubscribe','newsletter','notifications',
    'notification','automated','auto','robot','bot','updates','alert','alerts',
}
_BAD_DOMAINS = {
    'example.com','test.com','domain.com','yourdomain.com','yourcompany.com',
    'email.com','sentry.io','wixpress.com','squarespace.com','wordpress.com',
    'mailchimp.com','sendgrid.net','amazonaws.com','cloudfront.net',
}

def is_valid_email(email: str) -> bool:
    if not email or '@' not in email:
        return False
    local, _, domain = email.rpartition('@')
    if not local or not domain or '.' not in domain:
        return False
    tld = domain.rsplit('.', 1)[-1].lower()
    if tld in _BAD_TLDS or len(tld) < 2 or len(tld) > 6:
        return False
    if local.lower() in _BAD_LOCAL:
        return False
    if domain.lower() in _BAD_DOMAINS:
        return False
    # Reject anything that looks like a URL fragment or file path
    if re.search(r'[/\\=?&]', email):
        return False
    return True


def normalize_site_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def extract_emails_from_text(text: str) -> list[str]:
    emails = EMAIL_RE.findall(text or "")
    cleaned = []
    for e in emails:
        e = e.strip().lower()
        if e not in cleaned and is_valid_email(e):
            cleaned.append(e)
    return cleaned


def fetch_page(url: str, headers: dict) -> str | None:
    try:
        resp = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
        if resp.status_code >= 400:
            return None
        return resp.text
    except Exception:
        return None


def find_contact_page(base_url: str, html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True).lower()
        href_lower = href.lower()
        if any(h in text for h in CONTACT_HINTS) or any(h in href_lower for h in CONTACT_HINTS):
            return urljoin(base_url, href)
    return ""


def has_contact_form(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    if soup.find("form"):
        return True
    text = soup.get_text(" ", strip=True).lower()
    return (
        "contact us" in text
        or "get in touch" in text
        or "send us a message" in text
    )


def enrich_public_email(website: str) -> tuple[str, str, str]:
    site = normalize_site_url(website)
    if not site:
        return "", "Not Applicable", ""

    home_html, working_url = fetch_best_page(site)
    if not home_html:
        return "", "Website Unreachable", ""

    home_emails = extract_emails_from_text(home_html)
    if home_emails:
        return home_emails[0], "Email Found", working_url or site

    contact_page = find_contact_page(working_url or site, home_html)
    if contact_page:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
        }
        contact_html = fetch_page(contact_page, headers)
        if contact_html:
            contact_emails = extract_emails_from_text(contact_html)
            if contact_emails:
                return contact_emails[0], "Email Found", contact_page
            if has_contact_form(contact_html):
                return "", "Contact Form Only", contact_page

    if has_contact_form(home_html):
        return "", "Contact Form Only", working_url or site

    return "", "No Public Email Found", contact_page or working_url or site


def classify_outreach(priority: str, website: str) -> tuple[str, str, str, str, str]:
    p = (priority or "").strip().upper()
    has_website = bool((website or "").strip())

    if p == "A" and not has_website:
        return "Call", "", "Not Applicable", "", "Not Needed"

    if p == "A+" and has_website:
        # Running ads + poor CTA → email-first (they're digitally aware, already spending)
        email_found, email_status, contact_page_url = enrich_public_email(website)
        if email_status == "Email Found":
            return "Email", email_found, email_status, contact_page_url, "Layer 1 Found"
        if email_status in ("No Public Email Found", "Contact Form Only", "Website Unreachable"):
            return "Mixed", "", email_status, contact_page_url, "Layer 2 Needed"
        return "Mixed", email_found, email_status, contact_page_url, "Layer 1 Pending"

    if p == "B" and has_website:
        email_found, email_status, contact_page_url = enrich_public_email(website)
        if email_status == "Email Found":
            return "Email", email_found, email_status, contact_page_url, "Layer 1 Found"
        if email_status in ("No Public Email Found", "Contact Form Only", "Website Unreachable"):
            return "Email", "", email_status, contact_page_url, "Layer 2 Needed"
        return "Email", email_found, email_status, contact_page_url, "Layer 1 Pending"

    if p == "B" and not has_website:
        return "Call", "", "Not Applicable", "", "Not Needed"

    if p == "A" and has_website:
        email_found, email_status, contact_page_url = enrich_public_email(website)
        if email_status == "Email Found":
            return "Mixed", email_found, email_status, contact_page_url, "Layer 1 Found"
        return "Call", "", email_status if email_status else "Not Applicable", contact_page_url, "Not Needed"

    return "Call", "", "Not Applicable", "", "Not Needed"


def build_site_candidates(url: str) -> list[str]:
    raw = (url or "").strip()
    if not raw:
        return []

    candidates = []
    seen = set()

    def add(u: str):
        u = u.strip()
        if u and u not in seen:
            seen.add(u)
            candidates.append(u)

    add(raw)

    normalized = normalize_site_url(raw)
    if normalized:
        add(normalized)

        if normalized.startswith("https://"):
            add("http://" + normalized[len("https://"):])
        elif normalized.startswith("http://"):
            add("https://" + normalized[len("http://"):])

        no_scheme = normalized.replace("https://", "").replace("http://", "")
        if no_scheme.startswith("www."):
            add("https://" + no_scheme[4:])
            add("http://" + no_scheme[4:])
        else:
            add("https://www." + no_scheme)
            add("http://www." + no_scheme)

    return candidates


def fetch_best_page(url: str) -> tuple[str | None, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    last_tried = ""
    for candidate in build_site_candidates(url):
        last_tried = candidate
        html = fetch_page(candidate, headers)
        if html:
            return html, candidate

    return None, last_tried


def load_json(path: str):
    return json.loads(Path(path).read_text())


def save_json(path: str, data: dict):
    Path(path).write_text(json.dumps(data, indent=2))


def search_places(full_query: str, max_results: int = 60):
    # Google Places API v1 caps each page at 20 results. To get up to ~60,
    # we follow nextPageToken for up to 2 extra pages.
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is missing")

    results = []
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.websiteUri,places.nationalPhoneNumber,places.googleMapsUri,places.businessStatus,places.userRatingCount,places.rating,nextPageToken"
    }
    body = {
        "textQuery": full_query,
        "maxResultCount": 20,
    }

    page_token = None
    for _ in range(3):  # max 3 pages = 60 results
        if page_token:
            body["pageToken"] = page_token
        response = requests.post(url, headers=headers, json=body, timeout=20)
        response.raise_for_status()
        data = response.json()

        for place in data.get("places", []):
            status = place.get("businessStatus", "OPERATIONAL")
            if status != "OPERATIONAL":
                continue
            results.append({
                "name": place.get("displayName", {}).get("text", ""),
                "address": place.get("formattedAddress", ""),
                "website": place.get("websiteUri", ""),
                "phone": place.get("nationalPhoneNumber", ""),
                "maps_url": place.get("googleMapsUri", ""),
                "review_count": int(place.get("userRatingCount", 0) or 0),
                "rating": float(place.get("rating", 0) or 0),
            })
            if len(results) >= max_results:
                return results

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return results


def check_website(url: str):
    if not url:
        return {"has_website": False, "score": 0, "issue": "No website", "raw_html": ""}

    html, working_url = fetch_best_page(url)
    if not html:
        return {"has_website": True, "score": 40, "issue": "Could not verify site", "raw_html": ""}

    raw_html = html
    html = html.lower()
    score = 100
    issues = []

    if "viewport" not in html:
        score -= 40
        issues.append("not mobile friendly")
    if len(html) < 3000:
        score -= 30
        issues.append("very thin content")
    if html.count("<table") > 3:
        score -= 20
        issues.append("outdated table layout")

    return {
        "has_website": True,
        "score": score,
        "issue": ", ".join(issues) if issues else "decent site",
        "raw_html": raw_html,
    }


def check_ads_signals(html: str) -> dict:
    """
    Detect ad tracking pixels and score CTA quality.
    Uses only the already-fetched HTML — no extra network calls.
    """
    if not html:
        return {"ads_detected": False, "pixel_types": "", "cta_quality": 0, "cta_issues": "No HTML"}

    lower = html.lower()

    # ── Pixel detection ──────────────────────────────────────
    pixels = []
    if re.search(r'AW-\d{7,}', html) or "googleadservices.com" in lower:
        pixels.append("Google Ads")
    if re.search(r'fbq\(', lower) or (
        "connect.facebook.net" in lower and "fbevents" in lower
    ):
        pixels.append("Meta Pixel")
    if re.search(r'googletagmanager\.com/gtm\.js', lower):
        pixels.append("GTM")
    if "analytics.tiktok.com" in lower or re.search(r'ttq\.load\(', lower):
        pixels.append("TikTok")

    ads_detected = bool(pixels)
    pixel_types = ", ".join(pixels)

    # ── CTA quality scoring ───────────────────────────────────
    score = 0
    missing = []

    cta_keywords = ["get quote", "free quote", "book now", "schedule", "get estimate",
                    "request a quote", "request quote", "get a quote", "free estimate",
                    "call now", "call us today"]
    if any(kw in lower for kw in cta_keywords):
        score += 25
    else:
        missing.append("no quote/book CTA")

    # Phone near top: check first 25% of HTML
    top_section = lower[:max(len(lower) // 4, 2000)]
    if "tel:" in top_section or re.search(r'\b\d{3}[\s.\-]\d{3}[\s.\-]\d{4}\b', top_section):
        score += 25
    else:
        missing.append("phone buried or missing near top")

    if "<form" in lower and ("type=\"submit\"" in lower or "type='submit'" in lower
                              or "submit" in lower):
        score += 25
    else:
        missing.append("no contact form")

    trust_keywords = ["years experience", "years in business", "licensed", "insured",
                      "5-star", "five star", "family owned", "locally owned"]
    if any(kw in lower for kw in trust_keywords):
        score += 25
    else:
        missing.append("no trust signals")

    cta_issues = ", ".join(missing) if missing else "CTAs look solid"

    return {
        "ads_detected": ads_detected,
        "pixel_types":  pixel_types,
        "cta_quality":  score,
        "cta_issues":   cta_issues,
    }


def fetch_meta_ads(business_name: str) -> str:
    """Scrape Meta Ad Library public page with Brave headless. No auth required."""
    try:
        encoded_name = url_quote(business_name)
        url = (
            f"https://www.facebook.com/ads/library/"
            f"?active_status=active&ad_type=all&country=US"
            f"&q={encoded_name}&search_type=keyword_unordered"
        )
        cmd = [
            "/usr/bin/brave-browser",
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--virtual-time-budget=8000",
            "--dump-dom",
            url,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        if proc.returncode != 0 or not proc.stdout:
            return ""
        soup = BeautifulSoup(proc.stdout, "html.parser")
        text = soup.get_text(" ", strip=True)
        # If the page didn't render any actual ads, bail out
        # "Library ID:" appears on every real ad card
        if "Library ID:" not in text and "Started running" not in text:
            return ""
        return text[:2000]
    except Exception:
        return ""


def fetch_google_ads(business_name: str) -> str:
    try:
        encoded_name = url_quote(business_name)
        cmd = [
            "/usr/bin/brave-browser",
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--virtual-time-budget=5000",
            "--dump-dom",
            f"https://adstransparency.google.com/?region=anywhere&query={encoded_name}",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0 or not proc.stdout:
            return ""
        soup = BeautifulSoup(proc.stdout, "html.parser")
        text = soup.get_text(" ", strip=True)
        return text[:2000] if text else ""
    except Exception:
        return ""


def score_ads_with_claude(business_name: str, niche: str, ad_copy: str) -> dict:
    if not ANTHROPIC_API_KEY:
        return {"score": 50, "weaknesses": "Claude unavailable"}
    if not ad_copy:
        return {"score": 50, "weaknesses": "No ad copy to analyze"}
    try:
        import urllib.request as _urllib_request
        weakness_list = (
            "generic headline, no price anchor, no urgency, CTA mismatch, "
            "no social proof, no local relevance, no offer specificity, no trust signals"
        )
        prompt = (
            f"You are a direct-response ad analyst. Score these {niche} ads for '{business_name}' "
            f"on a scale of 0-100 (0=terrible, 100=elite). "
            f"Identify weaknesses from this list only: {weakness_list}. "
            f"Respond ONLY with valid JSON: {{\"score\": int, \"weaknesses\": \"comma-separated string\"}}\n\n"
            f"Ad copy:\n{ad_copy[:1500]}"
        )
        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 150,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = _urllib_request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
        )
        with _urllib_request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        raw = data["content"][0]["text"].strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        score = max(0, min(100, int(result.get("score", 50))))
        return {"score": score, "weaknesses": str(result.get("weaknesses", ""))}
    except Exception:
        return {"score": 50, "weaknesses": "Parse error"}


def check_live_ads(business_name: str, niche: str) -> dict:
    _empty = {
        "live_ads_found": False,
        "live_ad_platforms": "",
        "ad_copy_sample": "",
        "ad_score": 0,
        "ad_weaknesses": "",
    }
    try:
        meta_text = fetch_meta_ads(business_name)
        google_text = fetch_google_ads(business_name)

        platforms = []
        ad_copy_parts = []

        if meta_text:
            platforms.append("Meta")
            ad_copy_parts.append(meta_text[:500])

        if google_text:
            platforms.append("Google")
            ad_copy_parts.append(google_text[:500])

        if not platforms:
            return _empty

        ad_copy_sample = " | ".join(ad_copy_parts)[:500]
        scored = score_ads_with_claude(business_name, niche, ad_copy_sample)

        return {
            "live_ads_found": True,
            "live_ad_platforms": ", ".join(platforms),
            "ad_copy_sample": ad_copy_sample,
            "ad_score": scored["score"],
            "ad_weaknesses": scored["weaknesses"],
        }
    except Exception:
        return _empty


def generate_email(business_name: str, issue: str, has_website: bool, ads_data: dict = None, live_ads_data: dict = None):
    if not ANTHROPIC_API_KEY:
        return "ANTHROPIC_API_KEY missing - email not generated"

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    if ads_data and ads_data.get("ads_detected"):
        if live_ads_data and live_ads_data.get("live_ads_found") and live_ads_data.get("ad_weaknesses"):
            prompt = (
                f"Write a 3-sentence cold email from Jake at Agentlyfe to {business_name}. "
                f"They are spending on {live_ads_data['live_ad_platforms']} ads but their actual live ads have these specific problems: {live_ads_data['ad_weaknesses']}. "
                f"They are paying for ads that won't convert. "
                f"Offer to fix their landing page and ad copy for free — they only pay 500 euros if they love it. "
                f"Be direct, reference the specific waste, no fluff, no links."
            )
        else:
            prompt = (
                f"Write a 3-sentence cold email from Jake at Agentlyfe to {business_name}. "
                f"They are running {ads_data['pixel_types']} but their site is losing them money: {ads_data['cta_issues']}. "
                f"They are paying for traffic that isn't converting. "
                f"Offer to fix their landing page for free — they only pay 500 euros if they love it. "
                f"Be direct, reference the waste, no fluff, no links."
            )
    elif has_website:
        prompt = (
            f"Write a 3-sentence cold email from Jake at Agentlyfe to {business_name}. "
            f"Their website has issues: {issue}. Offer to rebuild it for free, they only pay 500 euros if they love it. "
            f"Be conversational, no fluff, no links."
        )
    else:
        prompt = (
            f"Write a 3-sentence cold email from Jake at Agentlyfe to {business_name}. "
            f"They have no website. Offer to build one for free, they only pay 500 euros if they love it. "
            f"Be conversational, no fluff, no links."
        )

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


def make_master_key(name: str, address: str) -> str:
    """Normalised dedup key — case-insensitive, whitespace-collapsed."""
    name    = re.sub(r'\s+', ' ', (name    or "").strip().lower())
    address = re.sub(r'\s+', ' ', (address or "").strip().lower())
    return f"{name}|{address}"


def load_scraped(master_file: str):
    path = Path(master_file)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return set()
    keys = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        # Normalise legacy keys that were stored raw
        if "|" in line:
            parts = line.split("|", 1)
            keys.add(make_master_key(parts[0], parts[1]))
        else:
            keys.add(line.lower())
    return keys


def save_scraped(master_file: str, key: str):
    with open(master_file, "a") as handle:
        handle.write(key + "\n")


def load_progress(progress_file: str, config: dict):
    path = Path(progress_file)

    if path.exists() and path.stat().st_size > 0:
        progress = json.loads(path.read_text())
    else:
        progress = {
            "country_code": config["country_code"],
            "country_name": config["country_name"],
            "last_updated": None,
            "niche_progress": {}
        }

    progress.setdefault("country_code", config["country_code"])
    progress.setdefault("country_name", config["country_name"])
    progress.setdefault("last_updated", None)
    progress.setdefault("niche_progress", {})

    for niche in config["niche_keywords"].keys():
        entry = progress["niche_progress"].setdefault(niche, {})
        entry.setdefault("completed_cities", [])
        entry.setdefault("completed", False)
        entry.setdefault("last_run", None)

    return progress


def get_pending_cities(config: dict, progress: dict, niche: str):
    completed = set(progress["niche_progress"][niche]["completed_cities"])
    return [city for city in config["cities"] if city not in completed]


def update_progress(progress: dict, config: dict, niche: str, successful_cities: list):
    entry = progress["niche_progress"][niche]
    existing = entry["completed_cities"]

    for city in successful_cities:
        if city not in existing:
            existing.append(city)

    timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    entry["last_run"] = timestamp
    entry["completed"] = len(existing) >= len(config["cities"])
    progress["last_updated"] = timestamp


def build_queries_for_city(niche: str, city: str, niche_keywords: dict):
    keywords = niche_keywords[niche]
    queries = []

    for keyword in keywords:
        term = niche if keyword == "" else keyword
        queries.append(f"{term} in {city}")

    return queries


def select_cities(config: dict, progress: dict, niche: str, next_count: int = None, explicit_cities: list = None):
    if explicit_cities:
        return explicit_cities

    pending = get_pending_cities(config, progress, niche)
    count = next_count or config.get("default_city_batch_size", 3)
    return pending[:count]


def export_ab_rows_to_dropbox(config: dict, niche: str, timestamp: str, fieldnames: list, ab_rows: list,
                              output_file: Path = None):
    if not config.get("export_ab_only_to_dropbox"):
        return None

    base_dir = config.get("dropbox_ab_base_dir")
    if not base_dir:
        return None

    # Fallback: if ab_rows is empty but the output CSV exists, read A/B rows from disk.
    # This recovers cleanly from crashes that interrupted the in-memory collection.
    if not ab_rows and output_file and Path(output_file).exists():
        with open(output_file, newline="") as f:
            for row in csv.DictReader(f):
                if row.get("priority") in {"A+", "A", "B"}:
                    ab_rows.append(row)

    export_dir = Path(base_dir) / config["country_code"] / niche
    export_dir.mkdir(parents=True, exist_ok=True)

    export_file = export_dir / f"{config['country_code']}_{niche}_{timestamp}_ab.csv"

    with open(export_file, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(ab_rows)

    return export_file


def _resolve_config_paths(config: dict) -> dict:
    """Resolve relative paths in config against ROOT so configs are portable."""
    for key in ("master_file", "progress_file", "output_dir"):
        if key in config and not Path(config[key]).is_absolute():
            config[key] = str(ROOT / config[key])
    if "dropbox_ab_base_dir" in config:
        v = config["dropbox_ab_base_dir"]
        if v.startswith("~"):
            config["dropbox_ab_base_dir"] = str(Path(v).expanduser())
        elif not Path(v).is_absolute():
            config["dropbox_ab_base_dir"] = str(ROOT / v)
    return config


def run_scrape(config_path: str, niche: str, next_count: int = None, explicit_cities: list = None, dry_run: bool = False):
    config = _resolve_config_paths(load_json(config_path))
    progress = load_progress(config["progress_file"], config)

    if niche not in config["niche_keywords"]:
        raise ValueError(f"Niche '{niche}' not found in config")

    selected_cities = select_cities(config, progress, niche, next_count=next_count, explicit_cities=explicit_cities)
    pending_before = get_pending_cities(config, progress, niche)

    print(f"Country: {config['country_name']}")
    print(f"Niche: {niche}")
    print(f"Pending before run: {pending_before}")
    print(f"Selected cities: {selected_cities}")

    if not selected_cities:
        print(f"Niche '{niche}' is already complete across all configured cities.")
        return

    if dry_run:
        print("\nDry run search plan:")
        for city in selected_cities:
            for query in build_queries_for_city(niche, city, config["niche_keywords"]):
                print(f"- {query}")
        return

    scraped = load_scraped(config["master_file"])
    priorities_to_email = set(config["generate_email_for_priorities"])

    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"{config['country_code']}_{niche}_{timestamp}.csv"

    fieldnames = [
        "niche",
        "country_code",
        "city",
        "search_term",
        "name",
        "address",
        "phone",
        "website",
        "has_website",
        "website_score",
        "issue",
        "ads_detected",
        "pixel_types",
        "cta_quality",
        "cta_issues",
        "priority",
        "outreach_channel",
        "email_found",
        "email_status",
        "contact_page_url",
        "email_discovery_stage",
        "email_draft",
        "maps_url",
        "live_ads_found",
        "live_ad_platforms",
        "ad_copy_sample",
        "ad_score",
        "ad_weaknesses",
        "meta_ads_url",
        "google_ads_url",
        "review_count",
        "rating",
    ]

    successful_cities = []
    ab_rows = []

    with open(output_file, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for city in selected_cities:
            print(f"\nProcessing city: {city}")
            city_ok = True
            new_rows = 0

            for search_term in build_queries_for_city(niche, city, config["niche_keywords"]):
                print(f"  Searching: {search_term}")

                try:
                    places = search_places(search_term, config["max_results_per_search"])
                except Exception as exc:
                    print(f"  Search failed for '{search_term}': {exc}")
                    city_ok = False
                    break

                print(f"  Found {len(places)} businesses")

                for biz in places:
                    key = make_master_key(biz["name"], biz["address"])
                    if key in scraped:
                        continue

                    website_data = check_website(biz["website"])
                    ads_data = check_ads_signals(website_data.get("raw_html", ""))

                    if ads_data["ads_detected"]:
                        live_ads_data = check_live_ads(biz["name"], niche)
                    else:
                        live_ads_data = {
                            "live_ads_found": False,
                            "live_ad_platforms": "",
                            "ad_copy_sample": "",
                            "ad_score": 0,
                            "ad_weaknesses": "",
                        }

                    # A+ = CONFIRMED running bad ads AND broken funnel (no site OR poor site).
                    # Pixel presence alone (ads_detected) is NOT enough — must have live_ads_found=True
                    # (confirmed via Meta Ad Library or Google Ads Transparency scrape).
                    # Stale pixels from old campaigns do not qualify. Good website (score >= 60) stays C.
                    _confirmed_running_ads = live_ads_data["live_ads_found"] is True
                    _bad_ads = _confirmed_running_ads and (
                        live_ads_data["ad_score"] < 50
                        or ads_data["cta_quality"] < 50
                    )
                    if not website_data["has_website"]:
                        priority = "A+" if _bad_ads else "A"
                    elif website_data["score"] < 60:
                        priority = "A+" if _bad_ads else "B"
                    else:
                        priority = "C"  # Good website: never A+, regardless of ads

                    # Demote A -> B if business has fewer than 5 Google reviews.
                    # Low-review leads are either new/unestablished or low-traffic,
                    # not worth prime outreach slots even when they have no site.
                    if priority == "A" and biz.get("review_count", 0) < 5:
                        priority = "B"

                    # Ad library direct links (only when ads detected)
                    if ads_data["ads_detected"]:
                        meta_ads_url   = (
                            f"https://www.facebook.com/ads/library/?active_status=active"
                            f"&ad_type=all&country=US&q={url_quote(biz['name'])}"
                            f"&search_type=keyword_unordered"
                        )
                        google_ads_url = (
                            f"https://adstransparency.google.com/?region=anywhere"
                            f"&query={url_quote(biz['name'])}"
                        )
                    else:
                        meta_ads_url   = ""
                        google_ads_url = ""

                    if priority in priorities_to_email or priority == "A+":
                        email = generate_email(
                            biz["name"], website_data["issue"], website_data["has_website"],
                            ads_data if priority == "A+" else None,
                            live_ads_data if priority == "A+" else None,
                        )
                    else:
                        email = "Site looks decent - skip"

                    outreach_channel, email_found, email_status, contact_page_url, email_discovery_stage = classify_outreach(
                        priority,
                        biz["website"],
                    )

                    row = {
                        "niche": niche,
                        "country_code": config["country_code"],
                        "city": city,
                        "search_term": search_term,
                        "name": biz["name"],
                        "address": biz["address"],
                        "phone": biz["phone"],
                        "website": biz["website"],
                        "has_website": website_data["has_website"],
                        "website_score": website_data["score"],
                        "issue": website_data["issue"],
                        "ads_detected": ads_data["ads_detected"],
                        "pixel_types":  ads_data["pixel_types"],
                        "cta_quality":  ads_data["cta_quality"],
                        "cta_issues":   ads_data["cta_issues"],
                        "priority": priority,
                        "outreach_channel": outreach_channel,
                        "email_found": email_found,
                        "email_status": email_status,
                        "contact_page_url": contact_page_url,
                        "email_discovery_stage": email_discovery_stage,
                        "email_draft": email,
                        "maps_url": biz["maps_url"],
                        "live_ads_found":    live_ads_data["live_ads_found"],
                        "live_ad_platforms": live_ads_data["live_ad_platforms"],
                        "ad_copy_sample":    live_ads_data["ad_copy_sample"],
                        "ad_score":          live_ads_data["ad_score"],
                        "ad_weaknesses":     live_ads_data["ad_weaknesses"],
                        "meta_ads_url":      meta_ads_url,
                        "google_ads_url":    google_ads_url,
                        "review_count":      biz.get("review_count", 0),
                        "rating":            biz.get("rating", 0),
                    }

                    writer.writerow(row)

                    if priority in {"A", "A+", "B"}:
                        ab_rows.append(row)

                    save_scraped(config["master_file"], key)
                    scraped.add(key)
                    new_rows += 1

            print(f"  New leads saved for {city}: {new_rows}")

            if city_ok:
                successful_cities.append(city)

    # Always run cleanup — even if the scrape loop crashed partway through.
    try:
        update_progress(progress, config, niche, successful_cities)
        save_json(config["progress_file"], progress)
    except Exception as exc:
        print(f"WARNING: failed to update progress file: {exc}")

    try:
        ab_export_file = export_ab_rows_to_dropbox(
            config, niche, timestamp, fieldnames, ab_rows, output_file=output_file
        )
    except Exception as exc:
        print(f"WARNING: failed to export A/B rows to Dropbox: {exc}")
        ab_export_file = None

    remaining = get_pending_cities(config, progress, niche)

    print(f"\nDone. Output file: {output_file}")
    if ab_export_file:
        print(f"A/B Dropbox export: {ab_export_file}")
    print(f"A/B lead count exported: {len(ab_rows)}")
    print(f"Cities marked complete this run: {successful_cities}")
    print(f"Remaining cities for {niche}: {remaining}")
    print(f"Niche completed across all cities: {progress['niche_progress'][niche]['completed']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to country config json")
    parser.add_argument("--niche", required=True, help="Niche to run, e.g. plumbers")
    parser.add_argument("--next", dest="next_count", type=int, help="Run next N pending cities for this niche")
    parser.add_argument("--cities", nargs="*", help="Explicit city list to run")
    parser.add_argument("--dry-run", action="store_true", help="Show planned searches without calling APIs")
    args = parser.parse_args()

    run_scrape(
        config_path=args.config,
        niche=args.niche,
        next_count=args.next_count,
        explicit_cities=args.cities,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()
