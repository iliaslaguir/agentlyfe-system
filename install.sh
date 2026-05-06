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
echo "You'll need a few API keys for this to work."
echo "Don't worry if you've never done this — links + instructions below."
echo "You can press Enter to skip any OPTIONAL field and add it later."
echo ""

# ── 6a. Anthropic API key (required) ─────────────────────────────────────────
echo "──────────────────────────────────────────────────────"
echo " 🤖  ANTHROPIC API KEY  (required — powers all the AI)"
echo "──────────────────────────────────────────────────────"
echo ""
echo "  This is what lets the system 'think'. Claude — the AI behind"
echo "  ChatGPT's main rival — picks your verticals, writes your cold"
echo "  emails, scores your leads."
echo ""
echo "  How to get one (takes ~2 min):"
echo "    1. Go to: https://console.anthropic.com/settings/keys"
echo "    2. Sign up / log in"
echo "    3. Click 'Create Key' → copy the key (starts with sk-ant-...)"
echo "    4. Add \$5 of credit at: https://console.anthropic.com/settings/billing"
echo "       (\$5 lasts a long time — every operation costs fractions of a cent)"
echo ""

ANTHROPIC_KEY=""
if [ -f "$SECRETS_DIR/anthropic_key.txt" ] && [ -s "$SECRETS_DIR/anthropic_key.txt" ]; then
  EXISTING=$(cat "$SECRETS_DIR/anthropic_key.txt" | tr -d '[:space:]')
  if [ "${EXISTING:0:7}" = "sk-ant-" ]; then
    echo "  ✅  Anthropic API key already set — reusing it."
    ANTHROPIC_KEY="$EXISTING"
  fi
fi
if [ -z "$ANTHROPIC_KEY" ]; then
  prompt "  Paste your Anthropic key here: " ANTHROPIC_KEY
fi

if [ -z "$ANTHROPIC_KEY" ]; then
  echo "  ⚠️   Skipped. AI features won't work until you add it."
  echo "       Edit: $SECRETS_DIR/anthropic_key.txt"
  ANTHROPIC_KEY="YOUR_ANTHROPIC_API_KEY_HERE"
fi

echo "$ANTHROPIC_KEY" > "$SECRETS_DIR/anthropic_key.txt"
echo "  ✅  Saved."
echo ""

# ── 6b. Google Places API key (required for scraping) ────────────────────────
echo "──────────────────────────────────────────────────────"
echo " 🗺️   GOOGLE PLACES API KEY  (required to find leads)"
echo "──────────────────────────────────────────────────────"
echo ""
echo "  This is how the system finds real businesses to contact —"
echo "  pulling from Google Maps (name, phone, website, address)."
echo "  Google gives \$200 free credit/month — plenty for most use."
echo ""
echo "  How to get one (~5 min, slightly fiddly the first time):"
echo "    1. Go to: https://console.cloud.google.com/"
echo "    2. Create a new project (top-left dropdown → New Project)"
echo "    3. Enable 'Places API (New)' here:"
echo "         https://console.cloud.google.com/apis/library/places.googleapis.com"
echo "    4. Create a key here:"
echo "         https://console.cloud.google.com/apis/credentials"
echo "         → Create Credentials → API key → copy it (starts with AIza...)"
echo "    5. (Optional but smart) Click 'Restrict key' → restrict to Places API"
echo ""
prompt "  Paste your Google Places key here: " GOOGLE_KEY
if [ -z "$GOOGLE_KEY" ]; then
  echo "  ⚠️   Skipped. Scraping won't work until you add it."
  echo "       Edit: $SECRETS_DIR/notion.env  (line GOOGLE_PLACES_API_KEY=)"
  GOOGLE_KEY="YOUR_GOOGLE_PLACES_API_KEY_HERE"
else
  echo "  ✅  Saved."
fi
echo ""

# ── 6c. Notion credentials (optional) ────────────────────────────────────────
echo "──────────────────────────────────────────────────────"
echo " 📋  NOTION CRM  (OPTIONAL — your lead database)"
echo "──────────────────────────────────────────────────────"
echo ""
echo "  Notion is where your leads live. Each scraped business becomes"
echo "  a row with phone, website, priority, AI-written email draft etc."
echo "  You can skip this and just use CSV exports if you prefer."
echo ""
echo "  How to set it up (~3 min):"
echo "    1. Duplicate the template database (link in the README)"
echo "    2. Create an integration here:"
echo "         https://www.notion.so/my-integrations"
echo "         → New integration → name it 'Lead System' → submit"
echo "         → copy the 'Internal Integration Secret' (starts with secret_)"
echo "    3. On your Leads database in Notion: ⋯ menu → Add connections →"
echo "         pick your integration"
echo "    4. To find the database ID: open the DB as a full page, look at"
echo "         the URL → notion.so/yourname/<DB_ID>?v=..."
echo "         The 32-character chunk before '?' is the database ID."
echo ""
echo "  Press Enter to skip and use CSV exports instead."
echo ""
prompt "  Notion integration token (secret_...): " NOTION_TOKEN
NOTION_LEADS_DB_ID=""
NOTION_DEALS_DB_ID=""
if [ -n "$NOTION_TOKEN" ]; then
  prompt "  Notion Leads database ID: " NOTION_LEADS_DB_ID
  prompt "  Notion Deals database ID (optional, press Enter to skip): " NOTION_DEALS_DB_ID
  echo "  ✅  Notion connected."
else
  echo "  ⏭️   Skipped — using CSV-only mode."
fi
echo ""

# ── 6d. Telegram bot (optional) ──────────────────────────────────────────────
echo "──────────────────────────────────────────────────────"
echo " 📱  TELEGRAM BOT  (OPTIONAL — control from your phone)"
echo "──────────────────────────────────────────────────────"
echo ""
echo "  Lets you DM the system from your phone:"
echo "    'scrape us roofers'  →  it scrapes 3 cities and replies."
echo "  Most people skip this on first install and add it later."
echo ""
echo "  How to set it up (~2 min):"
echo "    1. In Telegram, message @BotFather"
echo "    2. Send /newbot, give it a name + username, copy the BOT TOKEN"
echo "    3. Message YOUR new bot once (anything — say hi)"
echo "    4. Visit this URL in your browser (replace BOT_TOKEN):"
echo "         https://api.telegram.org/botBOT_TOKEN/getUpdates"
echo "    5. Find \"chat\":{\"id\": NUMBER ...} — that NUMBER is your chat ID"
echo ""
echo "  Press Enter to skip."
echo ""
prompt "  Telegram bot token: " TELEGRAM_TOKEN
TELEGRAM_CHAT_ID=""
if [ -n "$TELEGRAM_TOKEN" ]; then
  prompt "  Telegram chat ID: " TELEGRAM_CHAT_ID
  echo "  ✅  Telegram bot connected."
else
  echo "  ⏭️   Skipped — you can add it later by editing configs/secrets/notion.env"
fi
echo ""

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

# ── 7. Offer + country config generation ────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║              🎯  What are you selling?               ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "Tell Claude what you sell — in plain English, like you're"
echo "describing it to a friend at a dinner party."
echo ""
echo "Claude will use this to figure out:"
echo "  • who would buy it (the verticals to target)"
echo "  • where to look for them (the best cities)"
echo "  • what to search for on Google Maps (the keywords)"
echo "  • how to pitch it (the cold-email angle)"
echo ""
echo "Examples that work well:"
echo "  • 'AI receptionists for dental clinics that miss after-hours calls'"
echo "  • 'Free website + monthly marketing retainer for local trades'"
echo "  • 'Lead-gen done-for-you for solar installers paying \$100+ per FB lead'"
echo "  • 'Google Ads management — chiropractors only — \$1500/mo'"
echo ""
echo "More specific = better results."
echo ""
prompt "What are you selling? " OFFER_INPUT
if [ -z "$OFFER_INPUT" ]; then
  OFFER_INPUT="Free website build for small local trade businesses with no/bad website, then a monthly marketing retainer."
  echo "   (no offer entered — using a default trade-business example)"
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║              🌍  Country Setup                       ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "Which country do your IDEAL CUSTOMERS live in?"
echo "(Doesn't have to be where you live — just where the leads are.)"
echo ""
echo "Any country works. Common ones:"
echo "  us  uk  au  ca  ie  nz   — or type the full name: germany, spain,"
echo "  india, brazil, etc. Claude will figure out the right cities."
echo ""
prompt "Country [press Enter for 'us']: " COUNTRY_INPUT
COUNTRY_INPUT=$(echo "${COUNTRY_INPUT:-us}" | tr '[:upper:]' '[:lower:]')

if [ "${ANTHROPIC_KEY:0:7}" = "sk-ant-" ]; then
  echo ""
  echo "🤖  Asking Claude to design the lead-gen plan for your offer..."
  echo "    Country: $COUNTRY_INPUT"
  echo ""
  $PYTHON scripts/config_generator.py "$COUNTRY_INPUT" "$OFFER_INPUT" && \
    GEN_OK=1 || GEN_OK=0

  if [ "$GEN_OK" = "1" ]; then
    echo ""
    if [ "$NONINTERACTIVE" = "0" ]; then
      prompt "Looks good? Press Enter to keep, or type 'redo' to regenerate: " CONFIRM
      while [ "$CONFIRM" = "redo" ]; do
        $PYTHON scripts/config_generator.py "$COUNTRY_INPUT" "$OFFER_INPUT"
        prompt "Looks good? Press Enter to keep, or type 'redo' to regenerate: " CONFIRM
      done
    fi
  else
    echo "⚠️   Config generation failed."
    echo "     Run manually: python3 scripts/config_generator.py $COUNTRY_INPUT \"$OFFER_INPUT\""
  fi
else
  echo ""
  echo "⚠️   Skipping config generation (no valid Anthropic key)."
  echo "     After adding your key, run: python3 scripts/config_generator.py $COUNTRY_INPUT \"$OFFER_INPUT\""
fi

# ── 8. Done ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║            ✅  Setup complete!                       ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "Your config is at: $INSTALL_DIR/configs/$COUNTRY_INPUT.json"
echo "Your offer + pitch angle are saved in: configs/business_context.json"
echo ""
echo "Run a scrape (use any vertical name from the config):"
echo "  cd $INSTALL_DIR"
echo "  python3 scripts/ops_router.py scrape $COUNTRY_INPUT <vertical_name>"
echo ""
echo "See README.md for the full command reference."
echo ""
