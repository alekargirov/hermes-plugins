"""crypto — Hermes plugin for live cryptocurrency market data.

The second KEYLESS plugin in this repo, after `weather`. Every source is a
public read-only endpoint, so there is no credential to set, leak or rotate —
do not go looking for a CRYPTO_API_KEY, there isn't one.

This is a DIRECT plugin: there is no app of ours behind it, so the plugin owns
the HTTP calls rather than forwarding to an /api/agent/tools endpoint.

Three tools:

  crypto_price     what a coin is worth right now, for one or many symbols
  crypto_history   OHLC candles over a period, plus summary stats
  crypto_alert     create / list / delete / enable / disable / check alerts

Alerts are stored per profile under `$HERMES_HOME/crypto/`, never in
this directory — the plugin mount is shared by the whole fleet and one agent
must not see another's alerts. Delivery is a `hermes cron` job running
`scripts/check_alerts_quiet.py`; see README.md.

Why a plugin and not a skill: "what's BTC at" is a question every profile asks
in passing, and a skill only helps once the model has decided to go read it.
A registered tool with a description that says *your training data is stale*
is what actually stops the model answering from memory.
"""

from __future__ import annotations

import logging

from . import providers, schemas, tools

logger = logging.getLogger(__name__)

PLUGIN_VERSION = "2026-08-20.1"

_TOOLS = (
    ("crypto_price", schemas.CRYPTO_PRICE, tools.crypto_price, "₿"),
    ("crypto_history", schemas.CRYPTO_HISTORY, tools.crypto_history, "📈"),
    ("crypto_alert", schemas.CRYPTO_ALERT, tools.crypto_alert, "🔔"),
)

_HELP = """\
/crypto — live crypto prices and alerts

  /crypto                      Prices for BTC and ETH
  /crypto BTC ETH SOL          Prices for the given symbols
  /crypto eur BTC              Quote in another fiat currency
  /crypto history BTC 30       30-day history summary
  /crypto alerts               List configured alerts
  /crypto check                Evaluate all alerts against live prices now
"""

_FIAT = {"USD", "EUR", "GBP", "CHF", "JPY", "AUD", "CAD", "BGN"}


def _slash_alerts() -> str:
    import json

    data = json.loads(tools.crypto_alert({"action": "list"}))
    if not data.get("ok", True):
        return f"[crypto] {data['message']}"
    if not data.get("count"):
        return "[crypto] No alerts configured."
    lines = [f"[crypto] {data['count']} alert(s):"]
    for alert in data["alerts"]:
        state = "on" if alert.get("enabled") else "off"
        lines.append(f"  {alert['id']}  [{state}]  {alert['description']}")
    return "\n".join(lines)


def _slash_check() -> str:
    import json

    data = json.loads(tools.crypto_alert({"action": "check"}))
    if not data.get("ok", True):
        return f"[crypto] {data['message']}"
    if data.get("message"):
        return f"[crypto] {data['message']}"
    if not data.get("triggered"):
        return f"[crypto] Checked {data.get('checked', 0)} alert(s) — nothing triggered."
    lines = ["[crypto] Triggered:"]
    for item in data["triggered"]:
        lines.append(f"  {item['description']} — {item['reason']}")
    return "\n".join(lines)


def _slash_history(argv) -> str:
    import json

    symbol = argv[1] if len(argv) > 1 else "BTC"
    days = int(argv[2]) if len(argv) > 2 and argv[2].isdigit() else 7
    data = json.loads(tools.crypto_history({"symbol": symbol, "days": days, "max_points": 10}))
    if not data.get("ok", True):
        return f"[crypto] {data['message']}"
    summary = data["summary"]
    return (
        f"[crypto] {data['symbol']}/{data['currency']} over {data['days']}d "
        f"({data['source']}): {summary['start']:,.8g} -> {summary['end']:,.8g} "
        f"({summary['change_pct']:+.2f}%), high {summary['high']:,.8g}, "
        f"low {summary['low']:,.8g}"
    )


def _handle_slash(raw_args: str) -> str:
    argv = (raw_args or "").split()
    head = argv[0].lower() if argv else ""

    if head in {"help", "-h", "--help"}:
        return _HELP
    if head == "alerts":
        return _slash_alerts()
    if head == "check":
        return _slash_check()
    if head == "history":
        return _slash_history(argv)

    currency = "USD"
    if argv and argv[0].upper() in _FIAT:
        currency = argv.pop(0).upper()
    symbols = [a for a in argv if a] or ["BTC", "ETH"]

    quotes = providers.get_quotes(symbols, currency)
    return "\n".join(["[crypto]"] + [f"  {tools.summary_line(q)}" for q in quotes])


def register(ctx) -> None:
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="crypto",
            schema=schema,
            handler=handler,
            description=schema["description"],
            emoji=emoji,
        )

    # The shared test doubles register tools and nothing else, and a future ctx
    # is free to drop slash commands entirely — neither should cost us the tools.
    if hasattr(ctx, "register_command"):
        ctx.register_command(
            "crypto",
            _handle_slash,
            description="Live crypto prices, history, and alerts.",
        )

    print(
        f"[crypto] registered {len(_TOOLS)} tools (v{PLUGIN_VERSION}) -> "
        "kraken, hyperliquid, binance, coinbase, coingecko (keyless)",
        flush=True,
    )
