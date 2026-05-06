#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Agentlyfe System — Installer
# Usage: curl -sSL https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/install.sh | bash
# ─────────────────────────────────────────────────────────────────────────────
set -e

# When piped through `curl ... | bash`, stdin is the script — `read` would
# eat script lines instead of waiting for the user. Re-attach stdin to the
# user's terminal so prompts work. The redirect itself can fail in
# sandboxed shells with no controlling terminal — swallow that error.
if [ ! -t 0 ]; then
  exec < /dev/tty 2>/dev/null || true
fi

# After any redirect, confirm we actually have an interactive terminal.
# If not (CI, sandboxed shells, etc.), skip prompts entirely and write
# placeholder secrets — the user can re-run install.sh interactively
# or hand-edit configs/secrets/ later.
NONINTERACTIVE=0
if [ ! -t 0 ]; then
  echo "⚠️   No interactive terminal detected. Running non-interactive install."
  echo "     Run install.sh again from a real terminal, or edit"
  echo "     configs/secrets/ manually after install completes."
  NONINTERACTIVE=1
fi

# Helper: prompt-or-skip. Reads into the var name passed as $2, defaults to ""
# when non-interactive.
prompt() {
  local _msg="$1" _var="$2" _val=""
  if [ "$NONINTERACTIVE" = "1" ]; then
    eval "$_var=\"\""
    return
  fi
  read -p "$_msg" _val
  eval "$_var=\"$(echo "$_val" | tr -d '[:space:]')\""
}

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

# ── 5. Create required directories ────────────────────────────────────────────
mkdir -p "$INSTALL_DIR/outputs" "$INSTALL_DIR/state" "$INSTALL_DIR/masters" "$INSTALL_DIR/inputs"
echo "✅  Directory structure ready"

# ── 6. Setup wizard ───────────────────────────────────────────────────────────
SECRETS_DIR="$INSTALL_DIR/configs/secrets"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║              🔑  API Key Setup                       ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "You'll need API keys to use the system."
echo "Press Enter to skip optional fields."
echo ""

# ── 6a. Anthropic API key (required) ─────────────────────────────────────────
ANTHROPIC_KEY=""
if [ -f "$SECRETS_DIR/anthropic_key.txt" ] && [ -s "$SECRETS_DIR/anthropic_key.txt" ]; then
  EXISTING=$(cat "$SECRETS_DIR/anthropic_key.txt" | tr -d '[:space:]')
  if [ "${EXISTING:0:7}" = "sk-ant-" ]; then
    echo "✅  Anthropic API key already set."
    ANTHROPIC_KEY="$EXISTING"
  fi
fi
if [ -z "$ANTHROPIC_KEY" ]; then
  prompt "🔑  Anthropic API key (sk-ant-...): " ANTHROPIC_KEY
fi

if [ -z "$ANTHROPIC_KEY" ]; then
  echo "⚠️   No Anthropic key entered. AI features will not work."
  echo "     Get one at: https://console.anthropic.com"
  ANTHROPIC_KEY="YOUR_ANTHROPIC_API_KEY_HERE"
fi

echo "$ANTHROPIC_KEY" > "$SECRETS_DIR/anthropic_key.txt"
echo "✅  Anthropic key saved."

# ── 6b. Google Places API key (required for scraping) ────────────────────────
echo ""
prompt "🔑  Google Places API key (required for scraping): " GOOGLE_KEY
if [ -z "$GOOGLE_KEY" ]; then
  echo "⚠️   No Google Places key entered. Scraping will not work."
  echo "     Get one at: https://console.cloud.google.com → Places API"
  GOOGLE_KEY="YOUR_GOOGLE_PLACES_API_KEY_HERE"
fi

# ── 6c. Notion credentials (optional) ────────────────────────────────────────
echo ""
echo "Notion integration (optional — needed to sync leads to Notion CRM):"
prompt "   Notion integration token (secret_...): " NOTION_TOKEN
NOTION_LEADS_DB_ID=""
NOTION_DEALS_DB_ID=""
if [ -n "$NOTION_TOKEN" ]; then
  prompt "   Notion Leads database ID: " NOTION_LEADS_DB_ID
  prompt "   Notion Deals database ID (optional): " NOTION_DEALS_DB_ID
fi

# ── 6d. Telegram bot (optional) ──────────────────────────────────────────────
echo ""
echo "Telegram bot (optional — for remote command interface on mobile):"
prompt "   Telegram bot token: " TELEGRAM_TOKEN
TELEGRAM_CHAT_ID=""
if [ -n "$TELEGRAM_TOKEN" ]; then
  prompt "   Telegram chat ID: " TELEGRAM_CHAT_ID
fi

# ── 6e. Write notion.env ─────────────────────────────────────────────────────
cat > "$SECRETS_DIR/notion.env" <<EOF
NOTION_TOKEN=${NOTION_TOKEN:-YOUR_NOTION_TOKEN_HERE}
NOTION_LEADS_DB_ID=${NOTION_LEADS_DB_ID:-YOUR_LEADS_DB_ID_HERE}
NOTION_DEALS_DB_ID=${NOTION_DEALS_DB_ID:-YOUR_DEALS_DB_ID_HERE}
TELEGRAM_TOKEN=${TELEGRAM_TOKEN:-YOUR_TELEGRAM_BOT_TOKEN_HERE}
TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID:-YOUR_TELEGRAM_CHAT_ID_HERE}
GOOGLE_PLACES_API_KEY=${GOOGLE_KEY}
EOF
echo "✅  Secrets saved to configs/secrets/"

# ── 7. Country config generation ─────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║              🌍  Country Setup                       ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "Which country do you want to scrape leads in?"
echo "Examples: us, uk, au, ca, ie, nz, germany, south africa, india"
echo ""
prompt "Country [default: us]: " COUNTRY_INPUT
COUNTRY_INPUT=$(echo "${COUNTRY_INPUT:-us}" | tr '[:upper:]' '[:lower:]')

if [ "${ANTHROPIC_KEY:0:7}" = "sk-ant-" ]; then
  echo ""
  echo "🤖  Generating $COUNTRY_INPUT config with Claude..."
  echo "    (This calls the Anthropic API to pick best cities + keywords)"
  echo ""
  $PYTHON scripts/config_generator.py "$COUNTRY_INPUT" && \
    echo "✅  Config generated for $COUNTRY_INPUT" || \
    echo "⚠️   Config generation failed — run manually: python3 scripts/config_generator.py $COUNTRY_INPUT"
else
  echo ""
  echo "⚠️   Skipping config generation (no valid Anthropic key)."
  echo "     Run later: python3 scripts/config_generator.py $COUNTRY_INPUT"
fi

# ── 8. Done ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║            ✅  Setup complete!                       ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "Your first scrape:"
echo "  cd $INSTALL_DIR"
echo "  python3 scripts/ops_router.py scrape $COUNTRY_INPUT roofers"
echo ""
echo "Sync to Notion (after scraping):"
echo "  python3 scripts/ops_router.py sync roofers $COUNTRY_INPUT notion"
echo ""
echo "See README.md for the full command reference."
echo ""
