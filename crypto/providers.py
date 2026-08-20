"""Market-data providers for the `crypto` plugin.

Four public, key-free sources tried in order until one answers:

1. Kraken     — global spot exchange, no geo-blocks; bid/ask/24h high/low/volume.
                 True 24h and 7d change come from a second OHLC call.
2. Hyperliquid— one POST covers 230+ assets (cached snapshot), and adds funding
                 rate and open interest. Quotes the perp oracle price, USD only.
3. Binance    — one call gives a true 24h change; geo-blocked in some regions.
4. Coinbase   — spot price only; the most reliable last resort for "what is it
                 worth right now".
5. CoinGecko  — aggregated (~1-2 min lag) but carries market cap and works for
                 long-tail coins the exchanges above do not list.

Every fetch returns the same quote dict so callers never care who answered.
Only the stdlib is used — these plugins run inside minimal containers.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

USER_AGENT = "hermes-crypto-prices/1.0"
DEFAULT_TIMEOUT = 8.0

# Quotes are cached briefly so three agents asking "what's BTC" in the same
# minute produce one upstream request, not three.
_CACHE_TTL = 20.0
_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_cache_lock = threading.Lock()

# Symbols that exchanges spell differently from everyone else.
_SYMBOL_ALIASES = {"XBT": "BTC"}

# CoinGecko needs slugs, not tickers. Majors are hardcoded to avoid a lookup
# round-trip; anything else falls back to their /search endpoint.
_COINGECKO_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "ripple",
    "ADA": "cardano", "DOGE": "dogecoin", "AVAX": "avalanche-2",
    "DOT": "polkadot", "MATIC": "matic-network", "LINK": "chainlink",
    "LTC": "litecoin", "BCH": "bitcoin-cash", "ATOM": "cosmos",
    "UNI": "uniswap", "XLM": "stellar", "TRX": "tron", "ETC": "ethereum-classic",
    "FIL": "filecoin", "APT": "aptos", "ARB": "arbitrum", "OP": "optimism",
    "NEAR": "near", "ALGO": "algorand", "XMR": "monero", "TON": "the-open-network",
    "SUI": "sui", "SHIB": "shiba-inu", "PEPE": "pepe", "USDT": "tether",
    "USDC": "usd-coin", "BNB": "binancecoin",
}

_coingecko_id_cache: Dict[str, str] = {}


class ProviderError(Exception):
    """A single provider failed; the caller should try the next one."""


def normalize_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper().lstrip("$")
    return _SYMBOL_ALIASES.get(s, s)


def normalize_currency(currency: str) -> str:
    return (currency or "USD").strip().upper()


def http_json(url: str, timeout: float = DEFAULT_TIMEOUT) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"HTTP {exc.code} from {urllib.parse.urlsplit(url).netloc}") from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"network error reaching {urllib.parse.urlsplit(url).netloc}: {exc.reason}") from exc
    except (ValueError, TimeoutError) as exc:
        raise ProviderError(f"bad response from {urllib.parse.urlsplit(url).netloc}: {exc}") from exc


def http_post_json(url: str, payload: Dict[str, Any], timeout: float = DEFAULT_TIMEOUT) -> Any:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"HTTP {exc.code} from {urllib.parse.urlsplit(url).netloc}") from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"network error reaching {urllib.parse.urlsplit(url).netloc}: {exc.reason}") from exc
    except (ValueError, TimeoutError) as exc:
        raise ProviderError(f"bad response from {urllib.parse.urlsplit(url).netloc}: {exc}") from exc


def _pct(new: float, old: float) -> Optional[float]:
    if not old:
        return None
    return round((new - old) / old * 100.0, 2)


# ---------------------------------------------------------------------------
# Kraken
# ---------------------------------------------------------------------------

def _kraken_ticker(symbol: str, currency: str) -> Dict[str, Any]:
    pair = f"{symbol}{currency}"
    data = http_json(f"https://api.kraken.com/0/public/Ticker?pair={urllib.parse.quote(pair)}")
    errors = data.get("error") or []
    if errors:
        raise ProviderError(f"kraken: {errors[0]}")
    result = data.get("result") or {}
    if not result:
        raise ProviderError("kraken: empty result")
    entry = next(iter(result.values()))
    # Kraken's h/l/v/p fields are [today, rolling 24h] — index 1 is the one
    # that matches what everyone else calls "24h".
    return {
        "price": float(entry["c"][0]),
        "bid": float(entry["b"][0]),
        "ask": float(entry["a"][0]),
        "high_24h": float(entry["h"][1]),
        "low_24h": float(entry["l"][1]),
        "volume_24h": float(entry["v"][1]),
        "vwap_24h": float(entry["p"][1]),
    }


def kraken_ohlc(symbol: str, currency: str, interval_minutes: int = 60) -> List[List[Any]]:
    """Return OHLC candles as [ts, open, high, low, close, vwap, volume, trades]."""
    pair = f"{symbol}{currency}"
    url = (
        "https://api.kraken.com/0/public/OHLC"
        f"?pair={urllib.parse.quote(pair)}&interval={int(interval_minutes)}"
    )
    data = http_json(url)
    errors = data.get("error") or []
    if errors:
        raise ProviderError(f"kraken: {errors[0]}")
    result = data.get("result") or {}
    candles = None
    for key, value in result.items():
        if key != "last" and isinstance(value, list):
            candles = value
            break
    if not candles:
        raise ProviderError("kraken: no OHLC data")
    return candles


def _kraken_changes(symbol: str, currency: str) -> Dict[str, Any]:
    """True 24h and 7d change, computed from hourly candles.

    Kraken's ticker only exposes today's UTC open, which is NOT a 24h change —
    reporting it as one would be wrong by up to 23 hours. One OHLC call gives
    us the real thing, plus 7d for free.
    """
    candles = kraken_ohlc(symbol, currency, 60)
    out: Dict[str, Any] = {}
    last_close = float(candles[-1][4])
    for label, bars_back in (("change_24h_pct", 24), ("change_7d_pct", 168)):
        if len(candles) > bars_back:
            out[label] = _pct(last_close, float(candles[-1 - bars_back][1]))
    return out


def fetch_kraken(symbol: str, currency: str) -> Dict[str, Any]:
    ticker = _kraken_ticker(symbol, currency)
    quote: Dict[str, Any] = {"source": "kraken", **ticker}
    try:
        quote.update(_kraken_changes(symbol, currency))
    except ProviderError:
        # Price is the important half; a missing change figure is not fatal.
        pass
    return quote


# ---------------------------------------------------------------------------
# Hyperliquid
# ---------------------------------------------------------------------------

# One POST returns context for every listed asset (230+), so the snapshot is
# cached and shared across symbols instead of re-fetched per coin.
_HL_SNAPSHOT_TTL = 15.0
_hl_snapshot: Dict[str, Any] = {}
_hl_lock = threading.Lock()


def _hyperliquid_snapshot() -> Dict[str, Dict[str, Any]]:
    """Map SYMBOL -> asset context from Hyperliquid's /info endpoint."""
    with _hl_lock:
        cached = _hl_snapshot.get("data")
        stamp = _hl_snapshot.get("ts", 0.0)
        if cached and (time.time() - stamp) < _HL_SNAPSHOT_TTL:
            return cached

    data = http_post_json("https://api.hyperliquid.xyz/info", {"type": "metaAndAssetCtxs"})
    if not isinstance(data, list) or len(data) < 2:
        raise ProviderError("hyperliquid: unexpected response shape")
    universe = ((data[0] or {}).get("universe")) or []
    contexts = data[1] or []
    snapshot = {
        str(asset.get("name", "")).upper(): ctx
        for asset, ctx in zip(universe, contexts)
        if asset.get("name")
    }
    if not snapshot:
        raise ProviderError("hyperliquid: empty universe")

    with _hl_lock:
        _hl_snapshot["data"] = snapshot
        _hl_snapshot["ts"] = time.time()
    return snapshot


def fetch_hyperliquid(symbol: str, currency: str) -> Dict[str, Any]:
    # Hyperliquid perps are USD-margined only — there is no EUR book to quote.
    if currency != "USD":
        raise ProviderError(f"hyperliquid: only quotes USD, not {currency}")

    ctx = _hyperliquid_snapshot().get(symbol)
    if not ctx:
        raise ProviderError(f"hyperliquid: {symbol} not listed")

    # oraclePx is Hyperliquid's index of spot venues — closer to a real spot
    # price than markPx, which carries the perp premium.
    price = ctx.get("oraclePx") or ctx.get("markPx") or ctx.get("midPx")
    if price is None:
        raise ProviderError(f"hyperliquid: no price for {symbol}")
    price = float(price)

    quote: Dict[str, Any] = {
        "source": "hyperliquid",
        "price": price,
        "mark_price": float(ctx["markPx"]) if ctx.get("markPx") else None,
        "volume_24h_usd": float(ctx["dayNtlVlm"]) if ctx.get("dayNtlVlm") else None,
        "open_interest": float(ctx["openInterest"]) if ctx.get("openInterest") else None,
        "funding_rate_hourly": float(ctx["funding"]) if ctx.get("funding") else None,
        "note": "perp oracle price (index of spot venues)",
    }
    prev_day = ctx.get("prevDayPx")
    if prev_day:
        quote["change_24h_pct"] = _pct(price, float(prev_day))
    return quote


# ---------------------------------------------------------------------------
# Binance
# ---------------------------------------------------------------------------

def _binance_pair(symbol: str, currency: str) -> str:
    # Binance quotes against USDT, not USD.
    quote_asset = "USDT" if currency == "USD" else currency
    return f"{symbol}{quote_asset}"


def fetch_binance(symbol: str, currency: str) -> Dict[str, Any]:
    pair = _binance_pair(symbol, currency)
    data = http_json(f"https://api.binance.com/api/v3/ticker/24hr?symbol={urllib.parse.quote(pair)}")
    if "lastPrice" not in data:
        raise ProviderError(f"binance: no data for {pair}")
    return {
        "source": "binance",
        "price": float(data["lastPrice"]),
        "bid": float(data.get("bidPrice") or 0) or None,
        "ask": float(data.get("askPrice") or 0) or None,
        "change_24h_pct": round(float(data["priceChangePercent"]), 2),
        "high_24h": float(data["highPrice"]),
        "low_24h": float(data["lowPrice"]),
        "volume_24h": float(data["volume"]),
    }


# ---------------------------------------------------------------------------
# Coinbase
# ---------------------------------------------------------------------------

def fetch_coinbase(symbol: str, currency: str) -> Dict[str, Any]:
    url = f"https://api.coinbase.com/v2/prices/{urllib.parse.quote(symbol)}-{urllib.parse.quote(currency)}/spot"
    data = http_json(url)
    amount = ((data or {}).get("data") or {}).get("amount")
    if amount is None:
        raise ProviderError(f"coinbase: no spot price for {symbol}-{currency}")
    return {"source": "coinbase", "price": float(amount)}


# ---------------------------------------------------------------------------
# CoinGecko
# ---------------------------------------------------------------------------

def _coingecko_id(symbol: str) -> str:
    if symbol in _COINGECKO_IDS:
        return _COINGECKO_IDS[symbol]
    cached = _coingecko_id_cache.get(symbol)
    if cached:
        return cached
    data = http_json(
        f"https://api.coingecko.com/api/v3/search?query={urllib.parse.quote(symbol)}"
    )
    for coin in (data or {}).get("coins") or []:
        if (coin.get("symbol") or "").upper() == symbol:
            coin_id = coin.get("id")
            if coin_id:
                _coingecko_id_cache[symbol] = coin_id
                return coin_id
    raise ProviderError(f"coingecko: unknown symbol {symbol}")


def fetch_coingecko(symbol: str, currency: str) -> Dict[str, Any]:
    coin_id = _coingecko_id(symbol)
    vs = currency.lower()
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        f"?ids={urllib.parse.quote(coin_id)}&vs_currencies={urllib.parse.quote(vs)}"
        "&include_market_cap=true&include_24hr_vol=true&include_24hr_change=true"
    )
    data = http_json(url)
    entry = (data or {}).get(coin_id)
    if not entry or entry.get(vs) is None:
        raise ProviderError(f"coingecko: no price for {coin_id} in {currency}")
    change = entry.get(f"{vs}_24h_change")
    return {
        "source": "coingecko",
        "price": float(entry[vs]),
        "change_24h_pct": round(float(change), 2) if change is not None else None,
        "market_cap": entry.get(f"{vs}_market_cap"),
        "volume_24h": entry.get(f"{vs}_24h_vol"),
        # CoinGecko aggregates across exchanges on a ~1-2 minute cadence.
        "note": "aggregated price (~1-2 min lag)",
    }


_PROVIDERS = (
    ("kraken", fetch_kraken),
    ("hyperliquid", fetch_hyperliquid),
    ("binance", fetch_binance),
    ("coinbase", fetch_coinbase),
    ("coingecko", fetch_coingecko),
)


def get_quote(
    symbol: str,
    currency: str = "USD",
    *,
    use_cache: bool = True,
    preferred: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch one quote, walking the provider chain until one answers.

    Raises ProviderError only when every provider failed, with each failure
    listed so the agent can tell "bad symbol" from "network is down".
    """
    symbol = normalize_symbol(symbol)
    currency = normalize_currency(currency)
    if not symbol:
        raise ProviderError("no symbol given")

    cache_key = f"{symbol}/{currency}/{preferred or ''}"
    if use_cache:
        with _cache_lock:
            hit = _cache.get(cache_key)
            if hit and (time.time() - hit[0]) < _CACHE_TTL:
                return dict(hit[1], cached=True)

    chain = list(_PROVIDERS)
    if preferred:
        preferred = preferred.strip().lower()
        chain.sort(key=lambda item: 0 if item[0] == preferred else 1)

    failures: List[str] = []
    for name, fetch in chain:
        try:
            quote = fetch(symbol, currency)
        except ProviderError as exc:
            failures.append(str(exc))
            continue
        except Exception as exc:  # a provider must never take the tool down
            failures.append(f"{name}: unexpected {type(exc).__name__}: {exc}")
            continue

        quote.update({
            "ok": True,
            "symbol": symbol,
            "currency": currency,
            "timestamp": int(time.time()),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        if failures:
            quote["fallback_from"] = failures
        with _cache_lock:
            _cache[cache_key] = (time.time(), quote)
        return dict(quote, cached=False)

    raise ProviderError(
        f"all providers failed for {symbol}/{currency}: " + "; ".join(failures)
    )


def get_quotes(
    symbols: List[str],
    currency: str = "USD",
    *,
    preferred: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch several quotes concurrently, preserving the requested order."""
    results: Dict[int, Dict[str, Any]] = {}

    def worker(index: int, sym: str) -> None:
        try:
            results[index] = get_quote(sym, currency, preferred=preferred)
        except ProviderError as exc:
            results[index] = {
                "ok": False,
                "symbol": normalize_symbol(sym),
                "currency": normalize_currency(currency),
                "message": str(exc),
            }

    threads = [
        threading.Thread(target=worker, args=(i, sym), daemon=True)
        for i, sym in enumerate(symbols)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=DEFAULT_TIMEOUT * 2 + 2)

    return [
        results.get(
            i,
            {"ok": False, "symbol": normalize_symbol(sym), "message": "timed out"},
        )
        for i, sym in enumerate(symbols)
    ]
