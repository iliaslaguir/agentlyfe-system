#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Agentlyfe — Quick key setup for individual scripts
# Usage: curl -sSL https://raw.githubusercontent.com/iliaslaguir/agentlyfe-system/main/setup_keys.sh | bash
# ─────────────────────────────────────────────────────────────────────────────
set -e

# Re-attach stdin to terminal when piped through `curl ... | bash`
if [ ! -t 0 ] && [ -e /dev/tty ]; then
  exec < /dev/tty
fi

SECRETS_DIR="./configs/secrets"
mkdir -p "$SECRETS_DIR"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║         Agentlyfe — Quick API Key Setup              ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

read -p "🔑  Anthropic API key (sk-ant-...): " ANTHROPIC_KEY
ANTHROPIC_KEY=$(echo "$ANTHROPIC_KEY" | tr -d '[:space:]')
echo "${ANTHROPIC_KEY:-YOUR_ANTHROPIC_API_KEY_HERE}" > "$SECRETS_DIR/anthropic_key.txt"
echo "✅  Saved to $SECRETS_DIR/anthropic_key.txt"

echo ""
read -p "🔑  Google Places API key (for scraping): " GOOGLE_KEY
GOOGLE_KEY=$(echo "$GOOGLE_KEY" | tr -d '[:space:]')

echo ""
echo "Notion + Telegram (press Enter to skip):"
read -p "   Notion token: " NOTION_TOKEN
read -p "   Notion Leads DB ID: " NOTION_DB
read -p "   Telegram bot token: " TG_TOKEN
read -p "   Telegram chat ID: " TG_CHAT

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
