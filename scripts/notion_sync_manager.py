import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent
DROPBOX_AB = Path.home() / "Dropbox" / "leads_ab"
SYNC_SCRIPT = ROOT / "scripts" / "sync_ab_to_notion.py"
SYNC_LOG = ROOT / "state" / "notion_sync_log.json"

COUNTRIES = {"uk", "us", "au", "ca", "ie", "nz", "fi"}
NICHES = {"builders", "electricians", "plumbers", "roofers", "hvac", "painters", "landscapers", "pest_control", "barbershops"}


def load_sync_log() -> set:
    """Return set of absolute CSV path strings that have already been synced."""
    if not SYNC_LOG.exists():
        return set()
    try:
        return set(json.loads(SYNC_LOG.read_text()))
    except Exception:
        return set()


def save_sync_log(synced: set) -> None:
    SYNC_LOG.write_text(json.dumps(sorted(synced), indent=2))


def find_all_csvs() -> List[Path]:
    return sorted(DROPBOX_AB.glob("**/*_ab.csv"))


def filter_csvs(country: str = None, niche: str = None, skip_synced: bool = True) -> List[Path]:
    synced = load_sync_log() if skip_synced else set()
    files = find_all_csvs()
    out = []
    for f in files:
        if skip_synced and str(f) in synced:
            continue
        parts = [p.lower() for p in f.parts]
        if country and country.lower() not in parts:
            continue
        if niche and niche.lower() not in parts:
            continue
        out.append(f)
    return out


def latest_csv(country: str = None, niche: str = None) -> Path | None:
    # latest always checks unsynced files only
    files = filter_csvs(country=country, niche=niche, skip_synced=True)
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def run_sync(csv_path: Path) -> Tuple[int, int, str]:
    cmd = ["python3", str(SYNC_SCRIPT), "--csv", str(csv_path)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    output = (res.stdout or "") + ("\n" + res.stderr if res.stderr else "")

    inserted = 0
    skipped = 0
    m1 = re.search(r"Inserted:\s*(\d+)", output)
    m2 = re.search(r"Skipped:\s*(\d+)", output)
    if m1:
        inserted = int(m1.group(1))
    if m2:
        skipped = int(m2.group(1))

    return inserted, skipped, output.strip()


def print_summary(results: List[Tuple[Path, int, int]]) -> None:
    total_inserted = sum(x[1] for x in results)
    total_skipped = sum(x[2] for x in results)
    print(f"Files processed: {len(results)}")
    print(f"Inserted total: {total_inserted}")
    print(f"Skipped total: {total_skipped}")
    print("")
    for path, ins, sk in results:
        print(f"- {path}: inserted {ins}, skipped {sk}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Sync all A/B CSV files")
    parser.add_argument("--latest", action="store_true", help="Sync only the newest matching file")
    parser.add_argument("--country", choices=sorted(COUNTRIES))
    parser.add_argument("--niche", choices=sorted(NICHES))
    args = parser.parse_args()

    if not args.all and not args.latest and not args.niche and not args.country:
        raise SystemExit("Specify --all, or provide filters like --niche/--country, or use --latest.")

    if args.latest:
        f = latest_csv(country=args.country, niche=args.niche)
        if not f:
            print("No matching A/B CSV found.")
            raise SystemExit(1)
        inserted, skipped, _ = run_sync(f)
        print("Latest sync complete")
        print(f"File: {f}")
        print(f"Inserted: {inserted}")
        print(f"Skipped: {skipped}")
        return

    if args.all:
        files = filter_csvs(country=args.country, niche=args.niche)
    else:
        files = filter_csvs(country=args.country, niche=args.niche)

    if not files:
        print("No matching A/B CSV files found.")
        raise SystemExit(1)

    synced_log = load_sync_log()
    results = []
    for f in files:
        inserted, skipped, _ = run_sync(f)
        results.append((f, inserted, skipped))
        # Mark as synced immediately after each file so re-running the command
        # never processes the same file twice, even if Notion API has a delay.
        synced_log.add(str(f))
        save_sync_log(synced_log)

    print_summary(results)


if __name__ == "__main__":
    main()
