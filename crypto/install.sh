#!/usr/bin/env bash
# Install the crypto plugin into a Hermes home (defaults to ~/.hermes).
#
#   ./install.sh                       # install into $HERMES_HOME or ~/.hermes
#   HERMES_HOME=/path ./install.sh     # install into a specific profile
#
# Copies the plugin, drops the alert checkers into <home>/scripts (hermes cron
# refuses scripts outside that directory), and prints the remaining steps.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOME_DIR="${HERMES_HOME:-$HOME/.hermes}"

mkdir -p "$HOME_DIR/plugins" "$HOME_DIR/scripts"
DEST="$HOME_DIR/plugins/crypto"

if [ "$SRC" = "$(cd "$DEST" 2>/dev/null && pwd || echo '')" ]; then
    # Already living at the destination — copying would mean rm -rf'ing our
    # own source. Just refresh the cron scripts below.
    echo "Plugin already installed at $DEST — refreshing scripts only."
else
    rm -rf "$DEST"
    cp -r "$SRC" "$DEST"
fi
rm -rf "$DEST/__pycache__"

cp "$SRC/scripts/check_alerts.py"       "$HOME_DIR/scripts/crypto_alerts.py"
cp "$SRC/scripts/check_alerts_quiet.py" "$HOME_DIR/scripts/crypto_alerts_quiet.py"
# The quiet wrapper imports its sibling by module name, so keep the names paired.
sed -i 's/^import check_alerts.*/import crypto_alerts as check_alerts  # noqa: E402/' \
    "$HOME_DIR/scripts/crypto_alerts_quiet.py"

echo "Installed into $HOME_DIR"
echo
echo "Next:"
echo "  hermes plugins enable crypto"
echo "  hermes tools | grep crypto"
echo
echo "Alert delivery (silent unless something fires, no LLM cost):"
echo "  hermes cron create '*/10 * * * *' --script crypto_alerts_quiet.py --no-agent \\"
echo "    --name 'Crypto alerts' --deliver telegram"
