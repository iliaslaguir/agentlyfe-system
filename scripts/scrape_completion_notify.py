"""Watch a running scraper subprocess and send a Telegram summary when it exits.

Usage:
    python3 scrape_completion_notify.py <pid> <country> <niche> <log_path>

Reads TELEGRAM_TOKEN + TELEGRAM_CHAT_ID from configs/secrets/notion.env.
Parses end-of-log for A+/A/B counts. Works whether it started the process
or is attaching to an existing PID.
"""
import os
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / "configs" / "secrets" / "notion.env"


def load_env() -> None:
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def wait_for_exit(pid: int, poll: int = 10) -> None:
    while pid_running(pid):
        time.sleep(poll)


def parse_summary(log_text: str) -> dict:
    """Pull city count + priority counts + A/B row export line from log tail."""
    summary = {"cities": 0, "a_plus": 0, "a": 0, "b": 0, "export_line": "", "errors": 0}

    # Count "Processing city:" lines
    summary["cities"] = len(re.findall(r"^Processing city:", log_text, re.M))

    # Count priority lines from per-row output (if scraper prints it)
    # Otherwise fall back to counting new leads lines.
    for match in re.finditer(r"New leads saved for .+?: (\d+)", log_text):
        pass  # just totals; priorities come from the CSV after the fact

    # Look for any export/final summary line
    m = re.search(r"(Wrote A/B rows to Dropbox:.+)", log_text)
    if m:
        summary["export_line"] = m.group(1).strip()

    m = re.search(r"Done\. Output file:\s*(\S+)", log_text)
    if m:
        summary["csv_path"] = m.group(1).strip()

    summary["errors"] = len(re.findall(r"(?i)error|traceback|failed", log_text))
    return summary


def count_priorities_in_csv(csv_path: str) -> dict:
    import csv
    counts = {"A+": 0, "A": 0, "B": 0, "C": 0}
    try:
        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                p = row.get("priority", "")
                if p in counts:
                    counts[p] += 1
    except Exception:
        pass
    return counts


def send_telegram(text: str) -> None:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("Missing TELEGRAM_TOKEN / TELEGRAM_CHAT_ID; skipping send")
        return
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat, "text": text, "parse_mode": "HTML"},
        timeout=15,
    )
    if r.status_code >= 300:
        print(f"Telegram send failed: {r.status_code} {r.text[:200]}")


def main():
    if len(sys.argv) != 5:
        print("Usage: scrape_completion_notify.py <pid> <country> <niche> <log_path>")
        sys.exit(2)

    pid = int(sys.argv[1])
    country = sys.argv[2]
    niche = sys.argv[3]
    log_path = sys.argv[4]

    load_env()
    wait_for_exit(pid)

    log_text = ""
    try:
        log_text = Path(log_path).read_text(errors="ignore")
    except Exception:
        pass

    summary = parse_summary(log_text)
    priorities = {}
    if "csv_path" in summary:
        priorities = count_priorities_in_csv(summary["csv_path"])

    lines = [f"✅ <b>Scrape done</b> — {country} {niche}"]
    if summary["cities"]:
        lines.append(f"Cities processed: {summary['cities']}")
    if priorities:
        lines.append(
            f"A+: {priorities['A+']} · A: {priorities['A']} · B: {priorities['B']} · C: {priorities['C']}"
        )
    if summary.get("export_line"):
        lines.append(summary["export_line"])
    if summary["errors"]:
        lines.append(f"⚠ {summary['errors']} error/traceback lines in log — <code>{log_path}</code>")
    lines.append(f"Next: <code>sync {niche} {country} notion</code>")

    send_telegram("\n".join(lines))


if __name__ == "__main__":
    main()
