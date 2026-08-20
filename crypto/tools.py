"""Tool handlers for the crypto plugin.

Every handler returns a JSON string and never raises — a market-data lookup
failing must read as "I could not get the price", not as a broken agent turn.
Failures use this repo's refusal shape, {"ok": false, "message": ...}, so the
model reads them the same way it reads every other plugin's.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from . import alerts as alert_store
from . import providers

# Kraken OHLC step sizes, in minutes. Picked so a request covering N days
# lands on a readable number of candles rather than 720 of them.
_INTERVAL_LADDER = (
    (1, 15),
    (3, 60),
    (14, 240),
    (60, 1440),
    (365, 10080),
)


def _err(message: str, **extra: Any) -> str:
    return json.dumps({"ok": False, "message": message, **extra})


def _clamped(raw: Any, *, default: int, low: int, high: int) -> int:
    """Absent -> default. Present but silly -> clamped, never re-defaulted."""
    if raw is None:
        return default
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def _fmt_price(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return f"{value:.8f}".rstrip("0").rstrip(".")


def summary_line(quote: Dict[str, Any]) -> str:
    """Compact one-liner — what the model should echo to the user."""
    if quote.get("message"):
        return f"{quote.get('symbol', '?')}: unavailable ({quote['message']})"
    parts = [f"{quote['symbol']} {_fmt_price(quote.get('price'))} {quote.get('currency', 'USD')}"]
    change = quote.get("change_24h_pct")
    if change is not None:
        parts.append(f"{change:+.2f}% 24h")
    change_7d = quote.get("change_7d_pct")
    if change_7d is not None:
        parts.append(f"{change_7d:+.2f}% 7d")
    if quote.get("high_24h") is not None and quote.get("low_24h") is not None:
        parts.append(
            f"24h range {_fmt_price(quote['low_24h'])}-{_fmt_price(quote['high_24h'])}"
        )
    parts.append(f"via {quote.get('source', '?')}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# crypto_price
# ---------------------------------------------------------------------------

def crypto_price(args: Dict[str, Any], **_kwargs: Any) -> str:
    raw_symbols = args.get("symbols")
    if isinstance(raw_symbols, str):
        # Tolerate "BTC" and "BTC,ETH" as well as the declared array.
        raw_symbols = [part for part in raw_symbols.replace(",", " ").split() if part]
    if not raw_symbols:
        return _err("No symbols given. Pass e.g. symbols: ['BTC'].")
    if not isinstance(raw_symbols, list):
        return _err("symbols must be a list of ticker strings.")

    symbols = [str(s) for s in raw_symbols][:15]
    currency = providers.normalize_currency(args.get("currency") or "USD")
    provider = args.get("provider")

    quotes = providers.get_quotes(symbols, currency, preferred=provider)
    return json.dumps({
        "ok": True,
        "quotes": quotes,
        "summary": [summary_line(q) for q in quotes],
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, default=str)


# ---------------------------------------------------------------------------
# crypto_history
# ---------------------------------------------------------------------------

def _pick_interval(days: int) -> int:
    for max_days, interval in _INTERVAL_LADDER:
        if days <= max_days:
            return interval
    return 21600


def _downsample(rows: List[List[Any]], max_points: int) -> List[List[Any]]:
    if max_points <= 0 or len(rows) <= max_points:
        return rows
    stride = len(rows) / float(max_points)
    picked = [rows[int(i * stride)] for i in range(max_points)]
    # Always keep the most recent candle — it is the one the user cares about.
    if picked[-1] is not rows[-1]:
        picked[-1] = rows[-1]
    return picked


def _coingecko_history(symbol: str, currency: str, days: int) -> List[Dict[str, Any]]:
    coin_id = providers._coingecko_id(symbol)
    url = (
        f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        f"?vs_currency={currency.lower()}&days={int(days)}"
    )
    data = providers.http_json(url)
    points = (data or {}).get("prices") or []
    if not points:
        raise providers.ProviderError(f"coingecko: no history for {coin_id}")
    return [
        {
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(point[0] / 1000)),
            "close": round(float(point[1]), 8),
        }
        for point in points
    ]


def crypto_history(args: Dict[str, Any], **_kwargs: Any) -> str:
    symbol = providers.normalize_symbol(str(args.get("symbol") or ""))
    if not symbol:
        return _err("No symbol given.")
    currency = providers.normalize_currency(args.get("currency") or "USD")

    # `or` here would turn an explicit 0 into the default — the same bug that
    # muted zero-cooldown alerts. Absent means default; present means clamp.
    days = _clamped(args.get("days"), default=7, low=1, high=365)
    max_points = _clamped(args.get("max_points"), default=60, low=5, high=200)

    cutoff = time.time() - days * 86400
    candles: List[Dict[str, Any]] = []
    source = ""
    failures: List[str] = []

    try:
        raw = providers.kraken_ohlc(symbol, currency, _pick_interval(days))
        rows = [row for row in raw if float(row[0]) >= cutoff] or raw
        rows = _downsample(rows, max_points)
        candles = [
            {
                "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(row[0]))),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[6]),
            }
            for row in rows
        ]
        source = "kraken"
    except providers.ProviderError as exc:
        failures.append(str(exc))
    except Exception as exc:
        failures.append(f"kraken: unexpected {type(exc).__name__}: {exc}")

    if not candles:
        try:
            points = _downsample(_coingecko_history(symbol, currency, days), max_points)
            candles = points
            source = "coingecko"
        except providers.ProviderError as exc:
            failures.append(str(exc))
        except Exception as exc:
            failures.append(f"coingecko: unexpected {type(exc).__name__}: {exc}")

    if not candles:
        return _err(
            f"No history available for {symbol}/{currency}: " + "; ".join(failures)
        )

    first = candles[0]
    last = candles[-1]
    start_price = float(first.get("open", first.get("close")))
    end_price = float(last["close"])
    highs = [float(c["high"]) for c in candles if "high" in c] or [float(c["close"]) for c in candles]
    lows = [float(c["low"]) for c in candles if "low" in c] or [float(c["close"]) for c in candles]

    return json.dumps({
        "ok": True,
        "symbol": symbol,
        "currency": currency,
        "days": days,
        "source": source,
        "points": len(candles),
        "summary": {
            "start": start_price,
            "end": end_price,
            "change_pct": round((end_price - start_price) / start_price * 100, 2) if start_price else None,
            "high": max(highs),
            "low": min(lows),
            "period_start": first["time"],
            "period_end": last["time"],
        },
        "candles": candles,
        "degraded": failures or None,
    }, default=str)


# ---------------------------------------------------------------------------
# crypto_alert
# ---------------------------------------------------------------------------

def _public_alert(alert: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": alert.get("id"),
        "description": alert_store.describe(alert),
        "symbol": alert.get("symbol"),
        "currency": alert.get("currency", "USD"),
        "kind": alert.get("kind"),
        "threshold": alert.get("threshold"),
        "window": alert.get("window"),
        "repeat": alert.get("repeat"),
        "enabled": alert.get("enabled", True),
        "trigger_count": alert.get("trigger_count", 0),
        "last_triggered_at": alert.get("last_triggered_at"),
    }


def _check_now() -> Dict[str, Any]:
    pairs = alert_store.symbols_to_watch()
    if not pairs:
        return {
            "ok": True,
            "action": "check",
            "triggered": [],
            "message": "No enabled alerts to check.",
        }

    quotes_by_key: Dict[str, Dict[str, Any]] = {}
    for currency in sorted({currency for _sym, currency in pairs}):
        symbols = [sym for sym, cur in pairs if cur == currency]
        for quote in providers.get_quotes(symbols, currency):
            quotes_by_key[f"{quote.get('symbol')}/{currency}"] = quote

    triggered, checked = alert_store.evaluate(quotes_by_key)
    return {
        "ok": True,
        "action": "check",
        "checked": len(checked),
        "triggered": triggered,
        "prices": [summary_line(q) for q in quotes_by_key.values()],
    }


def crypto_alert(args: Dict[str, Any], **_kwargs: Any) -> str:
    action = str(args.get("action") or "").strip().lower()

    try:
        if action == "list":
            all_alerts = alert_store.load_alerts()
            return json.dumps({
                "ok": True,
                "action": "list",
                "count": len(all_alerts),
                "alerts": [_public_alert(a) for a in all_alerts],
                "storage": str(alert_store.alerts_file()),
            }, default=str)

        if action == "create":
            symbol = providers.normalize_symbol(str(args.get("symbol") or ""))
            if not symbol:
                return _err("create needs a symbol.")
            kind = str(args.get("kind") or "").strip().lower()
            if args.get("threshold") is None:
                return _err("create needs a threshold.")
            currency = providers.normalize_currency(args.get("currency") or "USD")

            baseline = None
            current: Optional[Dict[str, Any]] = None
            try:
                current = providers.get_quote(symbol, currency)
            except providers.ProviderError as exc:
                # A pct_from alert is meaningless without a baseline, so that
                # case is fatal; the others can be armed blind.
                if kind == "pct_from":
                    return _err(f"Cannot create pct_from alert — no current price: {exc}")
            if current:
                baseline = current.get("price")

            alert = alert_store.create_alert(
                symbol,
                kind,
                args.get("threshold"),
                currency=currency,
                window=str(args.get("window") or "24h"),
                repeat=str(args.get("repeat") or "once"),
                # `or` would turn an explicit 0 ("alert me every time") into
                # the default 60-minute cooldown, silently muting the alert.
                cooldown_minutes=(
                    alert_store.DEFAULT_COOLDOWN_MINUTES
                    if args.get("cooldown_minutes") is None
                    else int(args["cooldown_minutes"])
                ),
                note=str(args.get("note") or ""),
                baseline_price=baseline if kind == "pct_from" else None,
            )
            payload = {
                "ok": True,
                "action": "create",
                "created": _public_alert(alert),
                "current_price": current.get("price") if current else None,
            }
            # Warn rather than silently arm an alert that is already true.
            if current:
                reason = alert_store._evaluate_one(alert, current)
                if reason:
                    payload["already_true"] = (
                        f"Heads up: this condition is already met right now ({reason})."
                    )
            return json.dumps(payload, default=str)

        if action == "delete":
            alert_id = str(args.get("alert_id") or "").strip()
            if not alert_id:
                return _err("delete needs an alert_id.")
            if not alert_store.delete_alert(alert_id):
                return _err(f"No alert with id '{alert_id}'.")
            return json.dumps({"ok": True, "action": "delete", "id": alert_id})

        if action in ("enable", "disable"):
            alert_id = str(args.get("alert_id") or "").strip()
            if not alert_id:
                return _err(f"{action} needs an alert_id.")
            if not alert_store.set_enabled(alert_id, action == "enable"):
                return _err(f"No alert with id '{alert_id}'.")
            return json.dumps({
                "ok": True,
                "action": action,
                "id": alert_id,
                "enabled": action == "enable",
            })

        if action == "check":
            return json.dumps(_check_now(), default=str)

        return _err(
            "Unknown action. Use create, list, delete, enable, disable or check."
        )

    except alert_store.AlertError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(f"crypto_alert failed: {type(exc).__name__}: {exc}")
