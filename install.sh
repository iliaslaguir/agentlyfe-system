#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Agentlyfe System — Installer
# Usage: curl -sSL https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/install.sh | bash
# ─────────────────────────────────────────────────────────────────────────────
set -e

REPO_URL="https://github.com/iliaslaguir/agentlyfe-system.git"
INSTALL_DIR="$HOME/agentlyfe-system"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║         Agentlyfe System — Installing...             ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── 1. Check Python version ───────────────────────────────────────────────────
PYTHON=$(command -v python3 || true)
if [ -z "$PYTHON" ]; then
  echo "❌  Python 3 not found. Install Python 3.10+ and re-run."
  exit 1
fi

PY_VER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
PY_MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
  echo "❌  Python $PY_VER found, but 3.10+ is required."
  exit 1
fi
echo "✅  Python $PY_VER"

# ── 2. Check git ──────────────────────────────────────────────────────────────
if ! command -v git &> /dev/null; then
  echo "❌  git not found. Install git and re-run."
  exit 1
fi
echo "✅  git $(git --version | awk '{print $3}')"

# ── 3. Clone repo ─────────────────────────────────────────────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "📦  Repo already cloned — pulling latest..."
  git -C "$INSTALL_DIR" pull --ff-only
else
  echo "📦  Cloning repo to $INSTALL_DIR..."
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ── 4. Install Python dependencies ────────────────────────────────────────────
echo ""
echo "📦  Installing Python packages..."
$PYTHON -m pip install --quiet --upgrade pip
$PYTHON -m pip install --quiet -r requirements.txt
echo "✅  Dependencies installed"

# ── 5. Set up secrets ─────────────────────────────────────────────────────────
SECRETS_DIR="$INSTALL_DIR/configs/secrets"

if [ ! -f "$SECRETS_DIR/notion.env" ]; then
  cp "$SECRETS_DIR/notion.env.example" "$SECRETS_DIR/notion.env"
  echo ""
  echo "🔑  Created configs/secrets/notion.env from template."
  echo "    → Open it and fill in your API keys before running any script."
fi

if [ ! -f "$SECRETS_DIR/anthropic_key.txt" ]; then
  cp "$SECRETS_DIR/anthropic_key.txt.example" "$SECRETS_DIR/anthropic_key.txt"
  echo "🔑  Created configs/secrets/anthropic_key.txt from template."
  echo "    → Paste your Anthropic API key into that file."
fi

# ── 6. Create required directories ────────────────────────────────────────────
mkdir -p "$INSTALL_DIR/outputs" "$INSTALL_DIR/state" "$INSTALL_DIR/masters" "$INSTALL_DIR/inputs"
echo "✅  Directory structure ready"

# ── 7. Done ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║            ✅  Installation complete!                ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1. Fill in your API keys:"
echo "       $SECRETS_DIR/notion.env"
echo "       $SECRETS_DIR/anthropic_key.txt"
echo ""
echo "  2. Generate a country config:"
echo "       cd $INSTALL_DIR"
echo "       python3 scripts/config_generator.py us"
echo ""
echo "  3. Run your first scrape:"
echo "       python3 scripts/ops_router.py scrape roofers 3 us"
echo ""
echo "  4. Sync to Notion:"
echo "       python3 scripts/ops_router.py sync roofers us notion"
echo ""
echo "  See README.md for the full guide."
echo ""
