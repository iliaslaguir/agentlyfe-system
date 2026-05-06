#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Agentlyfe — Quick key setup for individual scripts
# Usage: curl -sSL https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/setup_keys.sh | bash
# ─────────────────────────────────────────────────────────────────────────────
set -e

# Re-attach stdin to terminal when piped through `curl ... | bash`.
# Swallow the redirect error if there's no controlling terminal.
if [ ! -t 0 ]; then
  exec < /dev/tty 2>/dev/null || true
fi

# Bail out cleanly if there's still no real terminal — running without
# a TTY would silently produce a config full of placeholders.
if [ ! -t 0 ]; then
  echo "❌  setup_keys.sh needs an interactive terminal."
  echo "    If you ran this via 'curl | bash' inside a non-TTY shell,"
  echo "    download it first then run it directly:"
  echo ""
  echo "    curl -O https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/setup_keys.sh"
  echo "    bash setup_keys.sh"
  exit 1
fi

SECRETS_DIR="./configs/secrets"
mkdir -p "$SECRETS_DIR"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║         Agentlyfe — Quick API Key Setup              ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "Quick walkthrough — links + instructions are below each prompt."
echo "Press Enter to skip OPTIONAL fields."
echo ""

# Anthropic
echo "──────────────────────────────────────────────────────"
echo " 🤖  ANTHROPIC API KEY  (required — powers all the AI)"
echo "──────────────────────────────────────────────────────"
echo "  Get one (~2 min):"
echo "    1. https://console.anthropic.com/settings/keys"
echo "    2. Sign up, click 'Create Key', copy it (sk-ant-...)"
echo "    3. Add \$5 credit at console.anthropic.com/settings/billing"
echo ""
read -p "  Paste your Anthropic key: " ANTHROPIC_KEY
ANTHROPIC_KEY=$(echo "$ANTHROPIC_KEY" | tr -d '[:space:]')
echo "${ANTHROPIC_KEY:-YOUR_ANTHROPIC_API_KEY_HERE}" > "$SECRETS_DIR/anthropic_key.txt"
echo "  ✅  Saved."
echo ""

# Google Places
echo "──────────────────────────────────────────────────────"
echo " 🗺️   GOOGLE PLACES API KEY  (required to find leads)"
echo "──────────────────────────────────────────────────────"
echo "  Get one (~5 min, fiddly first time — \$200/mo free credit):"
echo "    1. https://console.cloud.google.com/  → create a new project"
echo "    2. Enable 'Places API (New)':"
echo "       https://console.cloud.google.com/apis/library/places.googleapis.com"
echo "    3. Create key:"
echo "       https://console.cloud.google.com/apis/credentials"
echo "       → Create Credentials → API key → copy (AIza...)"
echo ""
read -p "  Paste your Google Places key: " GOOGLE_KEY
GOOGLE_KEY=$(echo "$GOOGLE_KEY" | tr -d '[:space:]')
echo ""

# Notion
echo "──────────────────────────────────────────────────────"
echo " 📋  NOTION CRM  (OPTIONAL)"
echo "──────────────────────────────────────────────────────"
echo "  Skip unless you want leads synced to a Notion database."
echo "  Setup (~3 min):"
echo "    1. Duplicate the template (link in README)"
echo "    2. https://www.notion.so/my-integrations → New integration"
echo "       → copy 'Internal Integration Secret' (secret_...)"
echo "    3. On the database in Notion: ⋯ → Add connections → pick yours"
echo "    4. DB ID = the 32-char chunk in the URL before '?v='"
echo ""
read -p "  Notion token (or Enter to skip): " NOTION_TOKEN
read -p "  Notion Leads DB ID: " NOTION_DB
echo ""

# Telegram
echo "──────────────────────────────────────────────────────"
echo " 📱  TELEGRAM BOT  (OPTIONAL — control from your phone)"
echo "──────────────────────────────────────────────────────"
echo "  Setup (~2 min):"
echo "    1. Telegram → message @BotFather → /newbot → copy bot token"
echo "    2. Message your new bot anything"
echo "    3. Visit: https://api.telegram.org/botBOT_TOKEN/getUpdates"
echo "       Find \"chat\":{\"id\": NUMBER ...} — that's your chat ID"
echo ""
read -p "  Telegram bot token (or Enter to skip): " TG_TOKEN
read -p "  Telegram chat ID: " TG_CHAT
echo ""

cat > "$SECRETS_DIR/notion.env" <<EOF
NOTION_TOKEN=${NOTION_TOKEN:-YOUR_NOTION_TOKEN_HERE}
NOTION_LEADS_DB_ID=${NOTION_DB:-YOUR_LEADS_DB_ID_HERE}
NOTION_DEALS_DB_ID=YOUR_DEALS_DB_ID_HERE
TELEGRAM_TOKEN=${TG_TOKEN:-YOUR_TELEGRAM_BOT_TOKEN_HERE}
TELEGRAM_CHAT_ID=${TG_CHAT:-YOUR_TELEGRAM_CHAT_ID_HERE}
GOOGLE_PLACES_API_KEY=${GOOGLE_KEY:-YOUR_GOOGLE_PLACES_API_KEY_HERE}
EOF
echo "✅  Saved to $SECRETS_DIR/notion.env"
echo ""
echo "Done. Run your script now."
echo ""
