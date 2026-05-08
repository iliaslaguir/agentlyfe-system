#!/usr/bin/env python3
"""Take an existing full-schema scrape CSV and produce a lean share-ready
CSV with regenerated cold-email drafts based on the CURRENT offer in
configs/business_context.json.

Use this when:
  - You scraped before the offer-aware email gen landed and the email_drafts
    pitch the wrong product.
  - You changed the offer (config_generator regenerated business_context.json)
    and want to re-pitch existing leads without re-scraping (saves Google
    Places quota).

Usage:
  python3 scripts/regenerate_share_csv.py outputs/spain/spain_luxury_hotels_20260507_012224.csv
  python3 scripts/regenerate_share_csv.py outputs/spain/spain_luxury_hotels_20260507_012224.csv --no-emails
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _secrets import load_secrets
load_secrets()

# Import after secrets are loaded so generate_email picks up the env vars
from scraper import generate_email  # type: ignore

LEAN_COLUMNS = [
    "business_name",
    "priority",
    "city",
    "phone",
    "email",
    "rating",
    "review_count",
    "website",
    "google_maps_url",
    "cold_email",
    "notes",
    "status",
]


def regenerate(input_path: Path, output_path: Path, regen_emails: bool, only_priority: list[str]):
    rows = list(csv.DictReader(open(input_path)))
    print(f"Read {len(rows)} rows from {input_path.name}")

    target_rows = [r for r in rows if not only_priority or r.get("priority") in only_priority]
    print(f"Will export {len(target_rows)} rows (priorities: {only_priority or 'all'})")

    out_rows = []
    for i, r in enumerate(target_rows, 1):
        cold_email = r.get("email_draft", "")
        if regen_emails and r.get("priority") in {"A", "A+", "B"}:
            print(f"  [{i}/{len(target_rows)}] regenerating email for {r.get('name','')[:40]}...")
            try:
                ads_data = {
                    "ads_detected": str(r.get("ads_detected", "")).lower() == "true",
                    "pixel_types": r.get("pixel_types", ""),
                    "cta_issues": r.get("cta_issues", ""),
                    "cta_quality": int(r.get("cta_quality") or 0),
                } if r.get("ads_detected") else None
                live_ads_data = {
                    "live_ads_found": str(r.get("live_ads_found", "")).lower() == "true",
                    "live_ad_platforms": r.get("live_ad_platforms", ""),
                    "ad_weaknesses": r.get("ad_weaknesses", ""),
                    "ad_score": int(r.get("ad_score") or 0),
                } if r.get("live_ads_found") else None
                cold_email = generate_email(
                    business_name=r.get("name", ""),
                    issue=r.get("issue", ""),
                    has_website=str(r.get("has_website", "")).lower() == "true",
                    ads_data=ads_data,
                    live_ads_data=live_ads_data,
                )
            except Exception as e:
                print(f"     skipped (error: {str(e)[:80]})")
                cold_email = r.get("email_draft", "")

        out_rows.append({
            "business_name":  r.get("name", ""),
            "priority":       r.get("priority", ""),
            "city":           r.get("city", ""),
            "phone":          r.get("phone", ""),
            "email":          r.get("email_found", "") or r.get("email", ""),
            "rating":         r.get("rating", ""),
            "review_count":   r.get("review_count", ""),
            "website":        r.get("website", ""),
            "google_maps_url": r.get("maps_url", ""),
            "cold_email":     cold_email,
            "notes":          "",
            "status":         "",
        })

    with open(output_path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEAN_COLUMNS)
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"\nWrote {len(out_rows)} lean rows to {output_path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("input_csv", help="Path to a full-schema scrape CSV")
    p.add_argument("--output", help="Output path (default: same dir, *_share.csv)")
    p.add_argument("--no-emails", action="store_true", help="Skip email regen — keep originals (faster, free)")
    p.add_argument("--ab-only", action="store_true", help="Export only A+/A/B priority rows")
    args = p.parse_args()

    in_path = Path(args.input_csv)
    if not in_path.exists():
        print(f"Not found: {in_path}")
        sys.exit(1)

    out_path = Path(args.output) if args.output else in_path.with_name(in_path.stem + "_share.csv")
    only = ["A+", "A", "B"] if args.ab_only else []
    regenerate(in_path, out_path, regen_emails=not args.no_emails, only_priority=only)
