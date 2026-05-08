"""Resolve the user's leads export folder.

The folder is where scraped lead CSVs land — `<leads_folder>/<country>/<niche>/...`.
The user picks this during install; they can put it anywhere (a plain folder,
~/Dropbox, ~/iCloud Drive, ~/Google Drive, an external mount, etc.) so the
files auto-sync to their phone/laptop if they want.

Resolution priority (first non-empty wins):
  1. LEADS_FOLDER env var                    — explicit override
  2. DROPBOX_AB_BASE_DIR env var             — legacy alias, kept for back-compat
  3. configs/leads_folder.txt                — written by install.sh wizard
  4. ~/agentlyfe-leads                       — neutral default for new installs
  5. ~/Dropbox/leads_ab                      — only if the user actually has it
                                               (back-compat for installs that
                                               predate this helper)
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEADS_FILE = ROOT / "configs" / "leads_folder.txt"
NEW_DEFAULT = Path.home() / "agentlyfe-leads"
LEGACY_DEFAULT = Path.home() / "Dropbox" / "leads_ab"


def leads_folder() -> Path:
    for var in ("LEADS_FOLDER", "DROPBOX_AB_BASE_DIR"):
        v = os.environ.get(var)
        if v:
            return Path(v).expanduser()

    if LEADS_FILE.exists():
        try:
            stored = LEADS_FILE.read_text().strip()
            if stored:
                return Path(stored).expanduser()
        except Exception:
            pass

    if LEGACY_DEFAULT.exists():
        return LEGACY_DEFAULT
    return NEW_DEFAULT
