#!/usr/bin/env bash
# Install the btc plugin into a Hermes home.
#
#   ./install.sh                          -> $HERMES_HOME, or ~/.hermes
#   HERMES_HOME=/path/to/profile ./install.sh
#
# For the fleet this directory ships in hermes-plugins and is mounted with the
# rest, so this is only for a plain Hermes home.
set -euo pipefail

HOME_DIR="${HERMES_HOME:-$HOME/.hermes}"
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME_DIR/plugins/btc"

mkdir -p "$DEST"
cp "$SRC"/__init__.py "$SRC"/plugin.yaml "$SRC"/README.md "$DEST/"
echo "[btc] installed to $DEST"

ENV_FILE="$HOME_DIR/.env"
if ! grep -qs '^BTC_URL=' "$ENV_FILE" 2>/dev/null; then
  cat >&2 <<'MSG'

[btc] NOT YET CONFIGURED. Add to this profile's .env:

  BTC_URL=http://btc:3024        # container-to-container on tfk-net.
                                 # Use the PUBLIC url only from a host that is
                                 # NOT on tfk-net — from inside, traefik
                                 # hairpins a public url and you get a 404.
  BTC_TOOL_KEY=<btc-srv TOOL_ENDPOINT_KEY>

Then:  hermes plugins enable btc   &&   restart the agent.
Plugins load at PROCESS START — an enabled plugin does nothing until then.
MSG
else
  echo "[btc] BTC_URL already set in $ENV_FILE"
fi
