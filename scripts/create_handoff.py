#!/usr/bin/env python3
"""
Session Handoff Generator
Creates a structured markdown summary of the current session state.
Run: python3 scripts/create_handoff.py
Or via Telegram: handoff
"""

import json
import re
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPAIN_TZ = timezone(timedelta(hours=2))
COUNTRIES = ["us", "uk", "au", "ca", "ie", "nz"]
NICHES    = ["builders", "electricians", "plumbers", "roofers", "hvac"]
HANDOFF_DIR = ROOT / "handoff"
CLAUDE_MD   = ROOT / "CLAUDE.md"


def now_spain():
    return datetime.now(SPAIN_TZ)


def load_json(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def master_count(cc):
    f = ROOT / "masters" / f"{cc}_master.txt"
    if not f.exists():
        return 0
    try:
        return sum(1 for l in f.open() if l.strip())
    except Exception:
        return 0


def latest_csv(cc):
    d = ROOT / "outputs" / cc
    if not d.exists():
        return None
    csvs = sorted(d.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)
    return csvs[0] if csvs else None


def git_changes_today():
    """List files changed in git today."""
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "log", "--since=midnight", "--oneline", "--name-only", "--format=%s"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() if result.stdout.strip() else None
    except Exception:
        return None


def load_previous_open_items():
    """Carry forward open items from the most recent handoff."""
    if not HANDOFF_DIR.exists():
        return []
    files = sorted(HANDOFF_DIR.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)
    if not files:
        return []
    try:
        text = files[0].read_text()
        # extract lines under "## Open / Pending"
        in_section = False
        items = []
        for line in text.splitlines():
            if line.startswith("## Open / Pending"):
                in_section = True
                continue
            if in_section:
                if line.startswith("## "):
                    break
                if line.strip().startswith("- ["):
                    items.append(line.strip())
        return items
    except Exception:
        return []


def update_claude_md(handoff_path: Path):
    """Update CLAUDE.md to reference the latest handoff file."""
    try:
        text = CLAUDE_MD.read_text()
        section = f"\n## Latest Handoff\nSee `{handoff_path.relative_to(ROOT)}` for the most recent session summary.\n"
        if "## Latest Handoff" in text:
            # Replace existing section
            text = re.sub(r'\n## Latest Handoff\n.*?(?=\n## |\Z)', section, text, flags=re.DOTALL)
        else:
            text = text.rstrip() + "\n" + section
        CLAUDE_MD.write_text(text)
    except Exception as e:
        print(f"  Warning: could not update CLAUDE.md: {e}")


def generate():
    HANDOFF_DIR.mkdir(exist_ok=True)
    now = now_spain()
    ts  = now.strftime("%Y-%m-%d_%H%M")
    fname = f"session_{ts}.md"
    out_path = HANDOFF_DIR / fname

    ctx = load_json(ROOT / "configs" / "business_context.json")
    clients = ctx.get("clients", {})
    strategy = ctx.get("strategy", {})

    lines = []
    lines.append(f"# Session Handoff — {now.strftime('%Y-%m-%d %H:%M')} (Spain)")
    lines.append("")

    # ── SYSTEM STATE ─────────────────────────────────────
    lines.append("## System State")
    lines.append("")

    for cc in COUNTRIES:
        p = load_json(ROOT / "state" / f"{cc}_progress.json")
        mc = master_count(cc)
        niche_p = p.get("niche_progress", {})
        niches_done = sum(1 for nd in niche_p.values() if nd.get("completed"))
        last_run = None
        for nd in niche_p.values():
            lr = nd.get("last_run")
            if lr and (not last_run or lr > last_run):
                last_run = lr
        csv = latest_csv(cc)
        csv_info = csv.name if csv else "none"
        lines.append(f"- **{cc.upper()}**: {mc} leads · {niches_done}/5 niches · last scraped: {last_run[:10] if last_run else 'never'} · latest CSV: {csv_info}")

    lines.append("")

    # ── CLIENTS ──────────────────────────────────────────
    lines.append("## Client Pipeline")
    lines.append("")
    mrr = 0
    for name, data in clients.items():
        status = data.get("status", "?")
        details = data.get("details", "")
        lines.append(f"- **{name}** [{status}]: {details}")
        if status == "ACTIVE":
            m = re.search(r'[€$](\d+)', details)
            if m:
                mrr += int(m.group(1))
    lines.append(f"\n**Current MRR: €{mrr}/month** · Target: €2,500 retainer / €5,000 total")
    lines.append("")

    # ── OPEN ITEMS ───────────────────────────────────────
    lines.append("## Open / Pending")
    lines.append("")
    prev_items = load_previous_open_items()
    if prev_items:
        for item in prev_items:
            lines.append(item)
    else:
        lines.append("- [ ] _(add open items here)_")
    lines.append("")

    # ── RECENT CHANGES ───────────────────────────────────
    lines.append("## Recent Git Changes")
    lines.append("")
    git_log = git_changes_today()
    if git_log:
        for line in git_log.splitlines()[:20]:
            lines.append(f"    {line}")
    else:
        lines.append("_(no git commits today, or git not tracking changes)_")
    lines.append("")

    # ── NEXT SESSION SHOULD START WITH ──────────────────
    lines.append("## Next Session Should Start With")
    lines.append("")
    # Auto-suggest based on state
    suggestions = []
    for cc in COUNTRIES:
        p = load_json(ROOT / "state" / f"{cc}_progress.json")
        niche_p = p.get("niche_progress", {})
        for niche, nd in niche_p.items():
            if not nd.get("completed") and nd.get("last_run"):
                try:
                    cfg = load_json(ROOT / "configs" / f"{cc}.json")
                    total = len(cfg.get("cities", []))
                    done = len(nd.get("completed_cities", []))
                    if done < total:
                        suggestions.append(f'Send `scrape {cc} {niche}` to Telegram bot to continue ({done}/{total} cities done)')
                        break
                except Exception:
                    pass
        if suggestions:
            break

    if not suggestions:
        suggestions.append("Check `status` in Telegram bot for current state")
        suggestions.append("Run morning briefing: `briefing` in Telegram")

    for s in suggestions[:3]:
        lines.append(f"1. {s}")
    lines.append("")

    # ── QUICK COMMANDS ───────────────────────────────────
    lines.append("## Quick Reference Commands (Telegram)")
    lines.append("")
    lines.append("| Command | Action |")
    lines.append("|---|---|")
    lines.append("| `status` | Show lead counts per country |")
    lines.append("| `scrape us roofers` | Scrape next 3 US roofer cities |")
    lines.append("| `sync us notion` | Sync US A/B leads to Notion |")
    lines.append("| `briefing` | Run morning briefing |")
    lines.append("| `ask [question]` | Ask Claude anything |")
    lines.append("| `handoff` | Generate new session handoff |")
    lines.append("")

    # Write file
    out_path.write_text("\n".join(lines))

    # Update CLAUDE.md
    update_claude_md(out_path)

    return out_path, fname


def main():
    print("⬡ Generating session handoff...")
    path, fname = generate()
    print(f"✅ Saved: {path}")
    print(f"✅ CLAUDE.md updated to reference: {fname}")
    print(f"\nNext session will automatically pick up context from this file.")


if __name__ == "__main__":
    main()
