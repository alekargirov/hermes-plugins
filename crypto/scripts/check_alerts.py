#!/usr/bin/env python3
"""Evaluate crypto price alerts — the scheduled half of the `crypto` plugin.

Designed to be run by ``hermes cron --script``: its stdout is injected as
context before the agent's prompt. When nothing fired it prints a single
NO_ALERTS_TRIGGERED line, so the cron prompt can tell the agent to answer
[SILENT] and stay quiet instead of messaging the user every interval.

Standalone by design — imports only the plugin's own stdlib modules, so it
runs fine from cron, a shell, or another container without Hermes loaded.

``hermes cron --script`` only accepts real files inside ``$HERMES_HOME/scripts``
(symlinks are resolved and rejected), so this file is written to work from
either home: run it in place, or copy it to ``~/.hermes/scripts/`` and it will
still find the plugin.

    python3 ~/.hermes/plugins/crypto/scripts/check_alerts.py [--json] [--quiet]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _find_plugin_dir() -> Path:
    """Locate the plugin package, whether we run in place or from scripts/."""
    override = (os.environ.get("CRYPTO_PRICES_DIR") or "").strip()
    candidates = []
    if override:
        candidates.append(Path(override).expanduser())
    candidates.append(Path(__file__).resolve().parent.parent)
    hermes_home = (os.environ.get("HERMES_HOME") or "").strip()
    base = Path(hermes_home).expanduser() if hermes_home else (Path.home() / ".hermes")
    # Both layouts: a plain install, and the fleet's mount where the repo
    # directory itself is the plugin category.
    candidates.append(base / "plugins" / "crypto")
    candidates.append(base / "plugins" / "hermes-plugins" / "crypto")
    candidates.append(base / "plugins" / "crypto-prices")
    for candidate in candidates:
        if (candidate / "alerts.py").is_file() and (candidate / "providers.py").is_file():
            return candidate
    raise SystemExit(
        "crypto plugin not found. Set CRYPTO_PRICES_DIR to its directory. "
        f"Looked in: {', '.join(str(c) for c in candidates)}"
    )


PLUGIN_DIR = _find_plugin_dir()
sys.path.insert(0, str(PLUGIN_DIR))

import alerts as alert_store  # noqa: E402
import providers  # noqa: E402


def _fetch_quotes(pairs):
    """Fetch one quote per watched (symbol, currency) pair."""
    quotes = {}
    for currency in sorted({currency for _sym, currency in pairs}):
        symbols = [sym for sym, cur in pairs if cur == currency]
        for quote in providers.get_quotes(symbols, currency):
            quotes[f"{quote.get('symbol')}/{currency}"] = quote
    return quotes


def main() -> int:
    parser = argparse.ArgumentParser(description="Check crypto price alerts.")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="print nothing unless an alert fired (for `hermes cron --no-agent`)",
    )
    args = parser.parse_args()

    pairs = alert_store.symbols_to_watch()
    if not pairs:
        if args.json:
            print(json.dumps({"triggered": []}))
        elif not args.quiet:
            print("NO_ALERTS_TRIGGERED (no alerts configured)")
        return 0

    try:
        quotes = _fetch_quotes(pairs)
    except Exception as exc:  # never let a dead API spam the user with tracebacks
        message = f"ALERT_CHECK_FAILED: {type(exc).__name__}: {exc}"
        if args.json:
            print(json.dumps({"ok": False, "message": message}))
        elif not args.quiet:
            # In quiet mode a transient API outage must stay silent — the user
            # asked to hear about price moves, not about network weather.
            print(message)
        return 0

    triggered, checked = alert_store.evaluate(quotes)

    if args.json:
        print(json.dumps({
            "triggered": triggered,
            "checked": len(checked),
            "prices": {key: q.get("price") for key, q in quotes.items()},
        }, default=str))
        return 0

    if not triggered:
        if not args.quiet:
            print(f"NO_ALERTS_TRIGGERED ({len(checked)} alert(s) checked, nothing hit)")
        return 0

    print(f"CRYPTO ALERTS TRIGGERED: {len(triggered)}")
    print()
    for item in triggered:
        print(f"- {item['description']}")
        print(f"  {item['reason']} (source: {item.get('source', '?')})")
        if item.get("note"):
            print(f"  note: {item['note']}")
        if item.get("disabled_after_trigger"):
            print("  this was a one-shot alert and is now disabled")
        print()

    print("Current prices:")
    for key, quote in sorted(quotes.items()):
        if not quote.get("ok", True):
            print(f"- {key}: unavailable")
        else:
            print(f"- {key}: {quote.get('price')} (via {quote.get('source')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
