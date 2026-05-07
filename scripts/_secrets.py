"""Shared helper: load secrets from configs/secrets/ into os.environ.

The wizard saves keys to:
  configs/secrets/notion.env       (KEY=value lines, including GOOGLE_PLACES_API_KEY)
  configs/secrets/anthropic_key.txt (just the key, one line)

But scripts historically read from os.environ via names like GOOGLE_API_KEY
and ANTHROPIC_API_KEY. This loader bridges the gap so a fresh install
"just works" without the user having to source any file manually.

Usage in any script that reads env vars:
    from _secrets import load_secrets; load_secrets()
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRETS_DIR = ROOT / "configs" / "secrets"

_loaded = False


def load_secrets() -> None:
    """Idempotent — safe to call from every script entry point."""
    global _loaded
    if _loaded:
        return

    _load_env_file(SECRETS_DIR / "notion.env")
    _load_anthropic_key(SECRETS_DIR / "anthropic_key.txt")
    _alias_google_key()

    _loaded = True


def _set_if_empty(key: str, value: str) -> None:
    """Set os.environ[key] only if the var is unset OR empty.

    Plain os.environ.setdefault won't override an empty-string env var, but a
    real key in our secrets file should always win over an inherited empty
    value from the parent shell.
    """
    current = os.environ.get(key, "")
    if not current and value:
        os.environ[key] = value


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value and not value.startswith("YOUR_"):
                _set_if_empty(key, value)
    except Exception:
        pass


def _load_anthropic_key(path: Path) -> None:
    if not path.exists():
        return
    try:
        key = path.read_text().strip()
        if key and key.startswith("sk-ant-"):
            _set_if_empty("ANTHROPIC_API_KEY", key)
    except Exception:
        pass


def _alias_google_key() -> None:
    # Wizard writes GOOGLE_PLACES_API_KEY; legacy code reads GOOGLE_API_KEY.
    # Mirror in both directions so either name works.
    places = os.environ.get("GOOGLE_PLACES_API_KEY", "")
    legacy = os.environ.get("GOOGLE_API_KEY", "")
    if places and not legacy:
        os.environ["GOOGLE_API_KEY"] = places
    elif legacy and not places:
        os.environ["GOOGLE_PLACES_API_KEY"] = legacy
