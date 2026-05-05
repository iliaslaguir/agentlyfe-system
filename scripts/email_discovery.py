import csv
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

STANDARD_EMAIL_RE = re.compile(r'([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})', re.I)

OBFUSCATED_PATTERNS = [
    re.compile(r'([A-Z0-9._%+\-]+)\s*\[\s*at\s*\]\s*([A-Z0-9.\-]+\.[A-Z]{2,})', re.I),
    re.compile(r'([A-Z0-9._%+\-]+)\s*\(\s*at\s*\)\s*([A-Z0-9.\-]+\.[A-Z]{2,})', re.I),
    re.compile(r'([A-Z0-9._%+\-]+)\s+at\s+([A-Z0-9.\-]+\.[A-Z]{2,})', re.I),
    re.compile(r'([A-Z0-9._%+\-]+)\s*@\s*([A-Z0-9.\-]+)\s*\.\s*([A-Z]{2,})', re.I),
]

PRIORITY_HINTS = [
    "contact", "about", "team", "privacy", "terms", "imprint", "legal", "company", "support"
]

FALLBACK_SLUGS = [
    "/contact",
    "/contact-us",
    "/about",
    "/about-us",
    "/team",
    "/privacy",
    "/privacy-policy",
    "/terms",
    "/terms-and-conditions",
    "/imprint",
]


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def same_domain(base: str, target: str) -> bool:
    try:
        return urlparse(base).netloc.replace("www.", "") == urlparse(target).netloc.replace("www.", "")
    except Exception:
        return False


def fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        if r.status_code >= 400:
            return None
        return r.text
    except Exception:
        return None


def extract_standard_emails(text: str) -> list[str]:
    emails = STANDARD_EMAIL_RE.findall(text or "")
    out = []
    for e in emails:
        e = e.strip().lower()
        if e not in out:
            out.append(e)
    return out


def extract_obfuscated_emails(text: str) -> list[str]:
    text = text or ""
    found = []

    for pat in OBFUSCATED_PATTERNS:
        for m in pat.findall(text):
            if len(m) == 2:
                email = f"{m[0]}@{m[1]}".lower()
            elif len(m) == 3:
                email = f"{m[0]}@{m[1]}.{m[2]}".lower()
            else:
                continue
            if email not in found:
                found.append(email)

    return found


def extract_mailto_emails(soup: BeautifulSoup) -> list[str]:
    found = []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if href.lower().startswith("mailto:"):
            email = href[7:].split("?")[0].strip().lower()
            if email and email not in found:
                found.append(email)
    return found


def extract_all_emails(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    found = []
    for email in extract_mailto_emails(soup) + extract_standard_emails(html) + extract_standard_emails(text) + extract_obfuscated_emails(text):
        if email not in found:
            found.append(email)
    return found


def candidate_pages(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found = []
    seen = set()

    def add(u: str):
        if not u:
            return
        if u in seen:
            return
        if not same_domain(base_url, u):
            return
        seen.add(u)
        found.append(u)

    add(base_url)

    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        text = a.get_text(" ", strip=True).lower()
        href_lower = href.lower()
        full = urljoin(base_url, href)

        if any(h in text for h in PRIORITY_HINTS) or any(h in href_lower for h in PRIORITY_HINTS):
            add(full)

    for slug in FALLBACK_SLUGS:
        add(urljoin(base_url, slug))

    return found[:20]


def discover_on_site(website: str) -> tuple[str, str, str, str]:
    site = normalize_url(website)
    if not site:
        return "", "No Website", "", "No website provided"

    home_html = fetch(site)
    if not home_html:
        return "", "Website Unreachable", "", "Homepage fetch failed"

    pages = candidate_pages(site, home_html)

    checked = 0
    for page in pages:
        html = fetch(page)
        if not html:
            continue
        checked += 1
        emails = extract_all_emails(html)
        if emails:
            return emails[0], "Email Found Layer 2", page, f"Found after checking {checked} pages"

    soup = BeautifulSoup(home_html, "html.parser")
    if soup.find("form"):
        return "", "Contact Form Only", site, f"No public email found after checking {checked or 1} pages"

    return "", "No Public Email Found", site, f"No public email found after checking {checked or 1} pages"


def process_csv(input_csv: Path, output_csv: Path):
    with input_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])

    extra_fields = [
        "layer2_email_found",
        "layer2_email_status",
        "layer2_source",
        "layer2_notes",
    ]
    for field in extra_fields:
        if field not in fieldnames:
            fieldnames.append(field)

    for row in rows:
        outreach_channel = (row.get("outreach_channel") or "").strip()
        email_status = (row.get("email_status") or "").strip()
        website = row.get("website", "") or ""

        if outreach_channel != "Email" or email_status not in {"No Public Email Found", "Contact Form Only", "Website Unreachable"}:
            continue

        found, status, source, notes = discover_on_site(website)
        row["layer2_email_found"] = found
        row["layer2_email_status"] = status
        row["layer2_source"] = source
        row["layer2_notes"] = notes

        print(f'{row.get("name","Unknown")}: {status} {found}')

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Done. Output: {output_csv}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Path to enriched _ab CSV")
    args = parser.parse_args()

    input_csv = Path(args.csv)
    if not input_csv.exists():
        raise FileNotFoundError(f"CSV not found: {input_csv}")

    output_csv = input_csv.with_name(input_csv.stem + "_layer2.csv")
    process_csv(input_csv, output_csv)


if __name__ == "__main__":
    main()
