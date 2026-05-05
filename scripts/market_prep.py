import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return json.loads(path.read_text())


def normalize_country_code(raw: str) -> str:
    return raw.strip().lower()


def config_path_for(country: str) -> Path:
    return ROOT / "configs" / f"{country}.json"


def load_config(country: str) -> Dict[str, Any]:
    return load_json(config_path_for(country))


def resolve_path(path_value: str) -> Path:
    p = Path(path_value)
    if p.is_absolute():
        return p
    return ROOT / path_value


def load_progress(config: Dict[str, Any]) -> Dict[str, Any]:
    return load_json(resolve_path(config["progress_file"]))


def get_supported_niches(config: Dict[str, Any]) -> List[str]:
    niche_keywords = config.get("niche_keywords") or {}
    return [str(n).strip().lower() for n in niche_keywords.keys() if str(n).strip()]


def get_country_label(config: Dict[str, Any], country_code: str) -> str:
    return config.get("country_name") or country_code.upper()


def all_cities(config: Dict[str, Any]) -> List[str]:
    return config.get("cities", [])


def completed_cities(progress: Dict[str, Any], niche: str) -> List[str]:
    return progress.get("niche_progress", {}).get(niche, {}).get("completed_cities", [])


def pending_cities(config: Dict[str, Any], progress: Dict[str, Any], niche: str) -> List[str]:
    done = set(completed_cities(progress, niche))
    return [city for city in all_cities(config) if city not in done]


def niche_completed(progress: Dict[str, Any], niche: str) -> bool:
    return bool(progress.get("niche_progress", {}).get(niche, {}).get("completed", False))


def niche_last_run(progress: Dict[str, Any], niche: str):
    return progress.get("niche_progress", {}).get(niche, {}).get("last_run")


def niche_summary(config: Dict[str, Any], progress: Dict[str, Any], niche: str) -> Dict[str, Any]:
    total = len(all_cities(config))
    done = len(completed_cities(progress, niche))
    pending = len(pending_cities(config, progress, niche))
    return {
        "niche": niche,
        "total_cities": total,
        "completed_cities": done,
        "pending_cities": pending,
        "completed_flag": niche_completed(progress, niche),
        "last_run": niche_last_run(progress, niche),
    }


def choose_next_niche(config: Dict[str, Any], progress: Dict[str, Any], niches: List[str]) -> Dict[str, Any]:
    summaries = [niche_summary(config, progress, n) for n in niches]

    # Prefer completely untouched niches first
    untouched = [s for s in summaries if s["completed_cities"] == 0]
    if untouched:
        untouched.sort(key=lambda x: x["niche"])
        chosen = untouched[0]
        return {
            "mode": "untested",
            "summary": chosen,
            "reason": "Untested niche should be sampled before expanding further.",
        }

    # Then prefer partially completed niches
    partial = [s for s in summaries if s["pending_cities"] > 0]
    if partial:
        partial.sort(key=lambda x: (x["completed_cities"], x["niche"]))
        chosen = partial[0]
        return {
            "mode": "continue_partial",
            "summary": chosen,
            "reason": "Continue the niche that has started but still has pending cities.",
        }

    raise RuntimeError("No niches available to choose from.")


def scrape_command(country: str, niche: str, count: int) -> str:
    return (
        f"python3 {ROOT / 'scripts' / 'scraper.py'} "
        f"--config {ROOT / 'configs' / f'{country}.json'} "
        f"--niche {niche} --next {count}"
    )


def print_prep(country: str, config: Dict[str, Any], progress: Dict[str, Any], niche: str, count: int) -> None:
    country_label = get_country_label(config, country)
    summary = niche_summary(config, progress, niche)
    pending = pending_cities(config, progress, niche)[:count]
    completed = completed_cities(progress, niche)

    print(f"Market prep — {country_label}")
    print(f"Niche: {niche}")
    print(
        f"Progress: {summary['completed_cities']}/{summary['total_cities']} cities completed | "
        f"Pending: {summary['pending_cities']} | "
        f"Completed flag: {summary['completed_flag']}"
    )
    print(f"Last run: {summary['last_run']}")

    if completed:
        print("Completed cities:")
        for city in completed:
            print(f"- {city}")

    if pending:
        print("Recommended next cities:")
        for i, city in enumerate(pending, start=1):
            print(f"{i}. {city}")
    else:
        print("Recommended next cities: none pending")

    print("Ready scrape command:")
    print(scrape_command(country, niche, count))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", required=True, help="Country code, e.g. uk")
    parser.add_argument("--niche", help="Optional niche override")
    parser.add_argument("--count", type=int, default=3, help="Number of next cities to prepare")
    args = parser.parse_args()

    country = normalize_country_code(args.country)
    config = load_config(country)
    progress = load_progress(config)
    niches = get_supported_niches(config)

    if args.niche:
        niche = args.niche.strip().lower()
        if niche not in niches:
            raise ValueError(f"Unsupported niche '{niche}' for {country}. Supported: {', '.join(niches)}")
        print_prep(country, config, progress, niche, args.count)
        return

    choice = choose_next_niche(config, progress, niches)
    chosen = choice["summary"]["niche"]
    country_label = get_country_label(config, country)

    print(f"Market prep — {country_label}")
    print(f"Decision mode: {choice['mode']}")
    print(f"Reason: {choice['reason']}")
    print(
        f"Chosen niche: {chosen} | "
        f"{choice['summary']['completed_cities']}/{choice['summary']['total_cities']} cities completed | "
        f"{choice['summary']['pending_cities']} pending"
    )
    print()

    print_prep(country, config, progress, chosen, args.count)


if __name__ == "__main__":
    main()
