"""Alert store and evaluation for the `crypto` plugin.

Alerts live in ``$HERMES_HOME/crypto/alerts.json``. Both the agent
(via the ``crypto_alert`` tool) and the cron script write to that file, so
every mutation takes an flock and lands through an atomic rename — a crashed
process can never leave a half-written alert list behind.

Four alert kinds:

* ``above`` / ``below``  — absolute price thresholds.
* ``pct_move``           — |change| over a rolling window (24h or 7d) exceeds N%.
* ``pct_from``           — price moved N% away from where it was when the
                           alert was created (baseline captured at creation).
"""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

VALID_KINDS = ("above", "below", "pct_move", "pct_from")
VALID_WINDOWS = ("24h", "7d")
VALID_REPEAT = ("once", "always")
DEFAULT_COOLDOWN_MINUTES = 60


class AlertError(Exception):
    """Bad alert definition — surfaced to the agent as a tool error."""


def hermes_home() -> Path:
    value = (os.environ.get("HERMES_HOME") or "").strip()
    return Path(value).expanduser().resolve() if value else (Path.home() / ".hermes").resolve()


def state_dir() -> Path:
    path = hermes_home() / "crypto"
    path.mkdir(parents=True, exist_ok=True)
    return path


def alerts_file() -> Path:
    return state_dir() / "alerts.json"


def _lock_file() -> Path:
    return state_dir() / "alerts.lock"


class _FileLock:
    """Advisory lock guarding read-modify-write cycles on alerts.json."""

    def __init__(self) -> None:
        self._handle = None

    def __enter__(self) -> "_FileLock":
        self._handle = open(_lock_file(), "a+")
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *_exc: Any) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None


def load_alerts() -> List[Dict[str, Any]]:
    path = alerts_file()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    return data.get("alerts", []) if isinstance(data, dict) else []


def save_alerts(alerts: List[Dict[str, Any]]) -> None:
    path = alerts_file()
    tmp = path.with_suffix(".json.tmp")
    payload = {"version": 1, "updated_at": int(time.time()), "alerts": alerts}
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _new_id(existing: List[Dict[str, Any]]) -> str:
    taken = {a.get("id") for a in existing}
    while True:
        candidate = secrets.token_hex(3)
        if candidate not in taken:
            return candidate


def create_alert(
    symbol: str,
    kind: str,
    threshold: float,
    *,
    currency: str = "USD",
    window: str = "24h",
    repeat: str = "once",
    cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
    note: str = "",
    baseline_price: Optional[float] = None,
) -> Dict[str, Any]:
    kind = (kind or "").strip().lower()
    if kind not in VALID_KINDS:
        raise AlertError(f"kind must be one of {', '.join(VALID_KINDS)} (got '{kind}')")

    window = (window or "24h").strip().lower()
    if window not in VALID_WINDOWS:
        raise AlertError(f"window must be one of {', '.join(VALID_WINDOWS)}")

    repeat = (repeat or "once").strip().lower()
    if repeat not in VALID_REPEAT:
        raise AlertError(f"repeat must be one of {', '.join(VALID_REPEAT)}")

    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        raise AlertError("threshold must be a number")
    if threshold <= 0:
        raise AlertError("threshold must be greater than zero")

    if kind == "pct_from" and not baseline_price:
        raise AlertError("pct_from alerts need a baseline_price (current price at creation)")

    alert = {
        "symbol": symbol.strip().upper(),
        "currency": currency.strip().upper(),
        "kind": kind,
        "threshold": threshold,
        "window": window,
        "repeat": repeat,
        "cooldown_minutes": max(0, int(cooldown_minutes)),
        "note": (note or "").strip(),
        "enabled": True,
        "created_at": int(time.time()),
        "last_triggered_at": None,
        "trigger_count": 0,
    }
    if baseline_price:
        alert["baseline_price"] = float(baseline_price)

    with _FileLock():
        alerts = load_alerts()
        alert["id"] = _new_id(alerts)
        alerts.append(alert)
        save_alerts(alerts)
    return alert


def delete_alert(alert_id: str) -> bool:
    alert_id = (alert_id or "").strip().lower()
    with _FileLock():
        alerts = load_alerts()
        remaining = [a for a in alerts if a.get("id") != alert_id]
        if len(remaining) == len(alerts):
            return False
        save_alerts(remaining)
    return True


def set_enabled(alert_id: str, enabled: bool) -> bool:
    alert_id = (alert_id or "").strip().lower()
    with _FileLock():
        alerts = load_alerts()
        found = False
        for alert in alerts:
            if alert.get("id") == alert_id:
                alert["enabled"] = bool(enabled)
                found = True
        if found:
            save_alerts(alerts)
    return found


def describe(alert: Dict[str, Any]) -> str:
    """One-line human description — used in tool output and Telegram alerts."""
    symbol = alert.get("symbol", "?")
    currency = alert.get("currency", "USD")
    kind = alert.get("kind")
    threshold = alert.get("threshold")
    if kind == "above":
        text = f"{symbol} above {threshold:,.8g} {currency}"
    elif kind == "below":
        text = f"{symbol} below {threshold:,.8g} {currency}"
    elif kind == "pct_move":
        text = f"{symbol} moves more than {threshold:g}% in {alert.get('window', '24h')}"
    elif kind == "pct_from":
        baseline = alert.get("baseline_price")
        text = f"{symbol} moves {threshold:g}% from {baseline:,.8g} {currency}"
    else:
        text = f"{symbol} {kind} {threshold}"
    if alert.get("note"):
        text += f" ({alert['note']})"
    return text


def _cooldown_active(alert: Dict[str, Any], now: float) -> bool:
    last = alert.get("last_triggered_at")
    if not last:
        return False
    return (now - float(last)) < alert.get("cooldown_minutes", DEFAULT_COOLDOWN_MINUTES) * 60


def _evaluate_one(alert: Dict[str, Any], quote: Dict[str, Any]) -> Optional[str]:
    """Return a reason string when the alert fires, else None."""
    price = quote.get("price")
    if price is None:
        return None
    kind = alert.get("kind")
    threshold = float(alert.get("threshold", 0))
    currency = alert.get("currency", "USD")

    if kind == "above":
        if price >= threshold:
            return f"price {price:,.8g} {currency} is at or above {threshold:,.8g}"
        return None

    if kind == "below":
        if price <= threshold:
            return f"price {price:,.8g} {currency} is at or below {threshold:,.8g}"
        return None

    if kind == "pct_move":
        key = "change_7d_pct" if alert.get("window") == "7d" else "change_24h_pct"
        change = quote.get(key)
        if change is None:
            # No change figure from this provider — stay silent rather than
            # guess; a missing datum must never look like a triggered alert.
            return None
        if abs(float(change)) >= threshold:
            direction = "up" if float(change) > 0 else "down"
            return (
                f"{direction} {abs(float(change)):.2f}% over {alert.get('window', '24h')} "
                f"(now {price:,.8g} {currency})"
            )
        return None

    if kind == "pct_from":
        baseline = alert.get("baseline_price")
        if not baseline:
            return None
        change = (price - float(baseline)) / float(baseline) * 100.0
        if abs(change) >= threshold:
            direction = "up" if change > 0 else "down"
            return (
                f"{direction} {abs(change):.2f}% from {float(baseline):,.8g} "
                f"(now {price:,.8g} {currency})"
            )
        return None

    return None


def evaluate(quotes_by_key: Dict[str, Dict[str, Any]], *, now: Optional[float] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Check every enabled alert against fresh quotes.

    ``quotes_by_key`` maps "SYMBOL/CURRENCY" to a quote dict from providers.

    Returns ``(triggered, checked)``. Firing an alert bumps its counter and,
    for ``repeat: once``, disables it — persisted under the same lock so two
    concurrent checks cannot double-fire the same alert.
    """
    now = time.time() if now is None else now
    triggered: List[Dict[str, Any]] = []
    checked: List[Dict[str, Any]] = []

    with _FileLock():
        alerts = load_alerts()
        dirty = False
        for alert in alerts:
            if not alert.get("enabled", True):
                continue
            key = f"{alert.get('symbol')}/{alert.get('currency', 'USD')}"
            quote = quotes_by_key.get(key)
            if not quote or not quote.get("ok", True):
                continue
            checked.append(alert)
            if _cooldown_active(alert, now):
                continue
            reason = _evaluate_one(alert, quote)
            if not reason:
                continue

            alert["last_triggered_at"] = int(now)
            alert["trigger_count"] = int(alert.get("trigger_count", 0)) + 1
            if alert.get("repeat", "once") == "once":
                alert["enabled"] = False
            dirty = True
            triggered.append({
                "id": alert.get("id"),
                "symbol": alert.get("symbol"),
                "currency": alert.get("currency", "USD"),
                "description": describe(alert),
                "reason": reason,
                "price": quote.get("price"),
                "source": quote.get("source"),
                "note": alert.get("note", ""),
                "repeat": alert.get("repeat", "once"),
                "disabled_after_trigger": alert.get("repeat", "once") == "once",
            })

        if dirty:
            save_alerts(alerts)

    return triggered, checked


def symbols_to_watch() -> List[Tuple[str, str]]:
    """Distinct (symbol, currency) pairs across all enabled alerts."""
    pairs = {
        (a.get("symbol", ""), a.get("currency", "USD"))
        for a in load_alerts()
        if a.get("enabled", True) and a.get("symbol")
    }
    return sorted(pairs)
