import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_json(path: str):
    return json.loads(Path(path).read_text())


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


def get_pending_cities(config: dict, progress: dict, niche: str):
    completed = set(progress["niche_progress"][niche]["completed_cities"])
    return [city for city in config["cities"] if city not in completed]


def completion_counts(config: dict, progress: dict, niche: str):
    completed = len(progress["niche_progress"][niche]["completed_cities"])
    total = len(config["cities"])
    remaining = total - completed
    return completed, remaining, total


def pct(part: int, whole: int):
    if whole == 0:
        return 0.0
    return round((part / whole) * 100, 1)


def print_country_status(config: dict, progress: dict):
    print(f"Country: {config['country_name']} ({config['country_code']})")
    print(f"Last updated: {progress.get('last_updated')}")
    print("")
    for niche in config["niche_keywords"].keys():
        completed, remaining, total = completion_counts(config, progress, niche)
        done_flag = progress["niche_progress"][niche]["completed"]
        print(
            f"- {niche}: {completed}/{total} cities complete | "
            f"remaining {remaining} | completed={done_flag} | "
            f"last_run={progress['niche_progress'][niche]['last_run']}"
        )


def print_niche_status(config: dict, progress: dict, niche: str):
    if niche not in config["niche_keywords"]:
        raise ValueError(f"Niche '{niche}' not found in config")
    completed, remaining, total = completion_counts(config, progress, niche)
    pending = get_pending_cities(config, progress, niche)

    print(f"Country: {config['country_name']} ({config['country_code']})")
    print(f"Niche: {niche}")
    print(f"Completed: {completed}/{total}")
    print(f"Remaining: {remaining}")
    print(f"Completed flag: {progress['niche_progress'][niche]['completed']}")
    print(f"Last run: {progress['niche_progress'][niche]['last_run']}")
    print("Completed cities:")
    for city in progress["niche_progress"][niche]["completed_cities"]:
        print(f"- {city}")
    print("Pending cities:")
    for city in pending:
        print(f"- {city}")


def print_next_cities(config: dict, progress: dict, niche: str, count: int):
    if niche not in config["niche_keywords"]:
        raise ValueError(f"Niche '{niche}' not found in config")
    pending = get_pending_cities(config, progress, niche)
    selected = pending[:count]

    print(f"Next {count} cities for {niche} in {config['country_name']}:")
    if not selected:
        print("- none, niche is complete")
        return
    for city in selected:
        print(f"- {city}")


def suggest_next_niche(config: dict, progress: dict):
    candidates = []
    for niche in config["niche_keywords"].keys():
        completed, remaining, total = completion_counts(config, progress, niche)
        if remaining > 0:
            candidates.append((completed, niche, remaining, total))
    if not candidates:
        print(f"All niches are complete in {config['country_name']}.")
        return
    candidates.sort(key=lambda x: (x[0], x[1]))
    completed, niche, remaining, total = candidates[0]

    print(f"Suggested next niche: {niche}")
    print(f"Reason: only {completed}/{total} cities completed so far")
    print("Suggested next cities:")
    for city in get_pending_cities(config, progress, niche)[: config.get("default_city_batch_size", 3)]:
        print(f"- {city}")


def collect_csv_stats(config: dict):
    output_dir = Path(config["output_dir"])
    csv_files = sorted(output_dir.glob(f"{config['country_code']}_*.csv"))

    totals = {"total": 0, "A+": 0, "A": 0, "B": 0, "C": 0}
    by_niche = defaultdict(lambda: {"total": 0, "A+": 0, "A": 0, "B": 0, "C": 0})

    for csv_file in csv_files:
        with csv_file.open(newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                niche = row.get("niche", "").strip()
                priority = row.get("priority", "").strip()

                totals["total"] += 1
                by_niche[niche]["total"] += 1

                if priority in {"A+", "A", "B", "C"}:
                    totals[priority] += 1
                    by_niche[niche][priority] += 1

    return totals, by_niche


def print_summary(config: dict):
    totals, by_niche = collect_csv_stats(config)

    aplus = totals["A+"]
    actionable = aplus + totals["A"] + totals["B"]
    print(f"{config['country_name']} summary")
    print(
        f"Total: {totals['total']} leads | "
        f"A+ {aplus} | "
        f"A {totals['A']} | "
        f"B {totals['B']} | "
        f"C {totals['C']} | "
        f"Actionable (A+/A/B): {actionable} | {pct(actionable, totals['total'])}%"
    )
    print("")
    print("Niches:")

    ranked = []
    for niche in sorted(by_niche.keys()):
        stats = by_niche[niche]
        ab_count = stats["A+"] + stats["A"] + stats["B"]
        ab_pct = pct(ab_count, stats["total"])
        a_pct = pct(stats["A+"] + stats["A"], stats["total"])
        ranked.append((ab_pct, stats["A+"] + stats["A"], niche, stats, ab_count))

        print(
            f"- {niche.title()}: {stats['total']} leads | "
            f"A+ {stats['A+']} | A {stats['A']} | B {stats['B']} | C {stats['C']} | "
            f"Actionable {ab_count} | {ab_pct}%"
        )

    if ranked:
        ranked.sort(key=lambda x: (-x[0], -x[1], x[2]))
        best = ranked[0]
        best_niche = best[2].title()
        print("")
        print(f"Insight: {best_niche} is the strongest tested niche so far by actionable lead quality.")
        print(f"Recommendation: keep {best_niche.lower()} as the current benchmark and compare the next untested niche against it.")


def print_city_breakdown(config: dict, progress: dict, niche: str):
    if niche not in config["niche_keywords"]:
        raise ValueError(f"Niche '{niche}' not found in config")

    output_dir = Path(config["output_dir"])
    csv_files = sorted(output_dir.glob(f"{config['country_code']}_*.csv"))

    by_city = defaultdict(lambda: {"total": 0, "A+": 0, "A": 0, "B": 0, "C": 0})

    for csv_file in csv_files:
        with csv_file.open(newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_niche = row.get("niche", "").strip()
                city = row.get("city", "").strip()
                priority = row.get("priority", "").strip()

                if row_niche != niche:
                    continue

                by_city[city]["total"] += 1
                if priority in {"A+", "A", "B", "C"}:
                    by_city[city][priority] += 1

    ranked = []
    for city, stats in by_city.items():
        ab_count = stats["A"] + stats["B"]
        ranked.append((
            pct(ab_count, stats["total"]),
            ab_count,
            stats["A"],
            stats["total"],
            city,
            stats
        ))

    ranked.sort(key=lambda x: (-x[0], -x[1], -x[2], -x[3], x[4]))

    print(f"{config['country_name']} city breakdown — {niche.title()}")
    if not ranked:
        print("No data yet for this niche.")
        return

    for idx, (_, _, _, _, city, stats) in enumerate(ranked, start=1):
        ab_count = stats["A"] + stats["B"]
        print(
            f"{idx}. {city}: {stats['total']} leads | "
            f"A {stats['A']} | {pct(stats['A'], stats['total'])}% | "
            f"A+B {ab_count} | {pct(ab_count, stats['total'])}%"
        )

    print("")
    best_city = ranked[0][4]
    best_stats = ranked[0][5]
    best_ab_count = best_stats["A"] + best_stats["B"]
    completed, remaining, total = completion_counts(config, progress, niche)
    pending = get_pending_cities(config, progress, niche)

    if progress["niche_progress"][niche]["completed"]:
        print(
            f"Insight: {best_city} is the strongest completed {niche} city so far "
            f"({pct(best_stats['A'], best_stats['total'])}% A, {pct(best_ab_count, best_stats['total'])}% A+B)."
        )
        print(
            f"Recommendation: {niche.title()} in {config['country_name']} is already complete. "
            f"Use {best_city} as the benchmark city, not as the next action."
        )
    else:
        next_cities = pending[: config.get("default_city_batch_size", 3)]
        next_label = ", ".join(next_cities) if next_cities else "none"
        print(
            f"Insight: {best_city} is the strongest proven {niche} city so far "
            f"({pct(best_stats['A'], best_stats['total'])}% A, {pct(best_ab_count, best_stats['total'])}% A+B)."
        )
        print(
            f"Recommendation: next pending cities are {next_label}. "
            f"Use {best_city} as the benchmark while continuing the remaining cities."
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to country config json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show country-wide progress status")
    subparsers.add_parser("summary", help="Show lead quality summary from output CSVs")
    subparsers.add_parser("suggest-next-niche", help="Suggest the next niche to scrape")

    niche_status = subparsers.add_parser("niche-status", help="Show status for a single niche")
    niche_status.add_argument("--niche", required=True)

    next_cities = subparsers.add_parser("next-cities", help="Show next pending cities for a niche")
    next_cities.add_argument("--niche", required=True)
    next_cities.add_argument("--count", type=int, default=3)

    city_breakdown = subparsers.add_parser("city-breakdown", help="Show ranked city stats for a niche")
    city_breakdown.add_argument("--niche", required=True)

    args = parser.parse_args()
    config = _resolve_config_paths(load_json(args.config))
    progress = load_json(config["progress_file"])

    if args.command == "status":
        print_country_status(config, progress)
    elif args.command == "summary":
        print_summary(config)
    elif args.command == "niche-status":
        print_niche_status(config, progress, args.niche)
    elif args.command == "next-cities":
        print_next_cities(config, progress, args.niche, args.count)
    elif args.command == "suggest-next-niche":
        suggest_next_niche(config, progress)
    elif args.command == "city-breakdown":
        print_city_breakdown(config, progress, args.niche)


if __name__ == "__main__":
    main()
