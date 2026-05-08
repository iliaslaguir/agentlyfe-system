"""Cross-platform 'open this file/folder' helper.

Tries the native OS handler so a non-technical user doesn't have to navigate
the terminal:
  - macOS    → `open <path>`        (Finder)
  - Linux    → `xdg-open <path>`    (Nautilus / Dolphin / GNOME Files)
  - Windows  → `os.startfile(path)` (Explorer)

Falls back to printing a clickable `file://` URL when no GUI is available
(SSH session into a headless VPS, CI, etc.). Most modern terminals
(iTerm2, Warp, VS Code Terminal, GNOME Terminal, Windows Terminal) treat
file:// URLs as cmd-clickable.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path


def is_remote_session() -> bool:
    """Best-effort: are we likely in an SSH session on a server?"""
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"):
        return True
    if not os.environ.get("DISPLAY") and sys.platform.startswith("linux"):
        # No X / Wayland — likely a headless server
        return True
    return False


def open_path(path) -> bool:
    """Open `path` (file or folder) in the native OS handler.
    Returns True on success, False if no handler was available.
    """
    p = str(Path(path).expanduser().resolve())
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", p], check=False)
            return True
        if sys.platform == "win32":
            os.startfile(p)  # type: ignore[attr-defined]
            return True
        if sys.platform.startswith("linux") and shutil.which("xdg-open") and not is_remote_session():
            subprocess.run(["xdg-open", p], check=False, stderr=subprocess.DEVNULL)
            return True
    except Exception:
        pass
    return False


def print_access_help(path) -> None:
    """Tell the user how to actually look at `path` based on their setup."""
    p = Path(path).expanduser().resolve()

    print()
    print(f"📂  File:  {p}")
    print()

    if is_remote_session():
        # Likely SSH'd into a VPS — give the scp recipe
        host = os.environ.get("SSH_CONNECTION", "").split()[0] if os.environ.get("SSH_CONNECTION") else "your-vps"
        user = os.environ.get("USER", "user")
        print("To download to your laptop:")
        print(f"  scp {user}@<your-vps-ip>:{p} ~/Downloads/")
        print()
        print("Or, if you have Dropbox/iCloud/Google Drive synced on the VPS,")
        print("set the leads folder to that synced path during install — files")
        print("then appear on your phone/laptop automatically.")
    else:
        # Local machine — try to open it
        if open_path(p):
            print("(Opening in your file manager…)")
        else:
            # Last-ditch: print the file:// URL — many terminals make it clickable
            print(f"Open this URL (cmd/ctrl-click in most terminals):")
            print(f"  file://{p}")
