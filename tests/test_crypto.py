"""The `crypto` plugin — registration, the provider fallback chain, and alerts.

Never touches the network: `urlopen` is monkeypatched with recorded response
bodies, so a Kraken outage can never turn this suite red. The point of the
plugin is that one dead provider is survivable, and that is exactly what the
fallback tests assert — by killing providers one at a time.

Alert tests point HERMES_HOME at a tmp_path, so they exercise the real store on
a real filesystem without touching the developer's own alerts.
"""
import json
import urllib.error

import pytest

import crypto
from crypto import alerts as alert_store
from crypto import providers, tools

# --- recorded upstream bodies ------------------------------------------------

KRAKEN_TICKER = json.dumps({
    "error": [],
    "result": {"XXBTZUSD": {
        "a": ["71649.8", "1", "1.0"], "b": ["71649.7", "2", "2.0"],
        "c": ["71649.7", "0.001"], "v": ["1238.5", "6951.2"],
        "p": ["70287.1", "68402.4"], "t": [32258, 118527],
        "l": ["68850.9", "64300.7"], "h": ["71752.0", "71900.0"],
        "o": "69285.0",
    }},
}).encode()

# 200 hourly candles, close climbing 100/hour: the 24h and 7d windows are then
# arithmetic we can assert exactly rather than eyeball.
KRAKEN_OHLC = json.dumps({
    "error": [],
    "result": {
        "XXBTZUSD": [
            [1787000000 + i * 3600, f"{50000 + i * 100}", f"{50050 + i * 100}",
             f"{49950 + i * 100}", f"{50000 + i * 100}", "0", "1.0", 10]
            for i in range(200)
        ],
        "last": 1787000000,
    },
}).encode()

KRAKEN_UNKNOWN_PAIR = json.dumps({"error": ["EQuery:Unknown asset pair"]}).encode()

HYPERLIQUID = json.dumps([
    {"universe": [{"name": "BTC"}, {"name": "HYPE"}]},
    [
        {"oraclePx": "71892.0", "markPx": "71870.0", "prevDayPx": "64359.0",
         "dayNtlVlm": "6854682146.0", "openInterest": "35863.8", "funding": "0.0000125"},
        {"oraclePx": "44.5", "markPx": "44.4", "prevDayPx": "40.0",
         "dayNtlVlm": "1000.0", "openInterest": "10.0", "funding": "0.0"},
    ],
]).encode()

BINANCE = json.dumps({
    "symbol": "BTCUSDT", "lastPrice": "71638.67", "priceChangePercent": "11.163",
    "highPrice": "71752.0", "lowPrice": "64300.0", "volume": "1000.0",
    "bidPrice": "71638.66", "askPrice": "71638.67",
}).encode()

COINBASE = json.dumps({"data": {"amount": "71558.81", "base": "BTC", "currency": "USD"}}).encode()

COINGECKO = json.dumps({
    "bitcoin": {"usd": 71556, "usd_market_cap": 1436222297168.8,
                "usd_24h_vol": 1.0, "usd_24h_change": 11.117},
}).encode()


class _Resp:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeCtx:
    def __init__(self):
        self.registered = []
        self.commands = []

    def register_tool(self, name, toolset, schema, handler, description, **kw):
        self.registered.append({"name": name, "toolset": toolset, "schema": schema,
                                "handler": handler, "description": description})

    def register_command(self, name, handler, description=""):
        self.commands.append(name)


@pytest.fixture(autouse=True)
def _no_cache():
    """The 20s quote cache is a feature in production and a liar in tests."""
    providers._cache.clear()
    providers._hl_snapshot.clear()
    yield
    providers._cache.clear()
    providers._hl_snapshot.clear()


@pytest.fixture(autouse=True)
def _isolated_alerts(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))


def _route(monkeypatch, dead=(), bodies=None, http_errors=None):
    """Serve recorded bodies by host.

    *dead* hosts refuse the connection; *http_errors* maps a URL fragment to a
    status code, because "this exchange does not list that coin" arrives as a
    400 or a 404, not as a dead socket, and the two must both be survivable.
    """
    seen = []

    def fake_urlopen(req, timeout=None):
        url = req.full_url
        seen.append(url)
        for host in dead:
            if host in url:
                raise urllib.error.URLError("connection refused")
        for fragment, code in (http_errors or {}).items():
            if fragment in url:
                raise urllib.error.HTTPError(url, code, "nope", {}, None)
        table = {
            "api.kraken.com/0/public/OHLC": KRAKEN_OHLC,
            "api.kraken.com/0/public/Ticker": KRAKEN_TICKER,
            "api.hyperliquid.xyz": HYPERLIQUID,
            "api.binance.com": BINANCE,
            "api.coinbase.com": COINBASE,
            "api.coingecko.com": COINGECKO,
        }
        for fragment, body in table.items():
            if fragment in url:
                return _Resp((bodies or {}).get(fragment, body))
        raise AssertionError(f"unrouted request: {url}")

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    return seen


# --- registration ------------------------------------------------------------

def test_three_tools_register_under_the_crypto_toolset():
    ctx = FakeCtx()
    crypto.register(ctx)
    assert [t["name"] for t in ctx.registered] == [
        "crypto_price", "crypto_history", "crypto_alert"]
    assert {t["toolset"] for t in ctx.registered} == {"crypto"}
    assert ctx.commands == ["crypto"]


def test_register_survives_a_ctx_without_slash_commands():
    """The shared shape suite registers tools and nothing else. Losing the
    tools because a test double has no register_command would be absurd."""
    class ToolsOnly:
        def __init__(self):
            self.registered = []

        def register_tool(self, **kw):
            self.registered.append(kw["name"])

    ctx = ToolsOnly()
    crypto.register(ctx)
    assert len(ctx.registered) == 3


# --- the provider chain ------------------------------------------------------

def test_kraken_is_preferred_and_carries_the_full_ticker(monkeypatch):
    _route(monkeypatch)
    quote = providers.get_quote("BTC")
    assert quote["source"] == "kraken"
    assert quote["price"] == 71649.7
    # h/l/v are [today, rolling 24h] — index 1, or the numbers are wrong.
    assert quote["high_24h"] == 71900.0
    assert quote["low_24h"] == 64300.7
    assert quote["volume_24h"] == 6951.2


def test_change_comes_from_candles_not_from_todays_open(monkeypatch):
    """Kraken's ticker only exposes today's UTC open. Reporting that as a 24h
    change would be wrong by up to 23 hours, so the plugin computes it from
    hourly candles: close 69900 against the open 24 bars back, 67500."""
    _route(monkeypatch)
    quote = providers.get_quote("BTC")
    assert quote["change_24h_pct"] == pytest.approx(3.56, abs=0.01)
    assert quote["change_7d_pct"] == pytest.approx(31.64, abs=0.01)
    # today's open is 69285 — if that leaked in, the number would be ~3.4%
    assert quote["change_24h_pct"] != pytest.approx(3.41, abs=0.01)


def test_falls_through_to_hyperliquid_when_kraken_is_down(monkeypatch):
    _route(monkeypatch, dead=["api.kraken.com"])
    quote = providers.get_quote("BTC")
    assert quote["source"] == "hyperliquid"
    assert quote["price"] == 71892.0          # oraclePx, not markPx
    assert quote["mark_price"] == 71870.0
    assert quote["change_24h_pct"] == pytest.approx(11.7, abs=0.1)
    assert quote["funding_rate_hourly"] == 0.0000125
    assert quote["fallback_from"], "a fallback must say what it fell back from"


def test_chain_walks_all_the_way_to_coingecko(monkeypatch):
    _route(monkeypatch, dead=["kraken", "hyperliquid", "binance", "coinbase"])
    quote = providers.get_quote("BTC")
    assert quote["source"] == "coingecko"
    assert quote["price"] == 71556
    assert quote["market_cap"] == pytest.approx(1436222297168.8)
    assert len(quote["fallback_from"]) == 4


def test_every_provider_down_is_a_message_not_an_exception(monkeypatch):
    _route(monkeypatch, dead=["kraken", "hyperliquid", "binance", "coinbase", "coingecko"])
    out = json.loads(tools.crypto_price({"symbols": ["BTC"]}))
    assert out["quotes"][0]["ok"] is False
    assert "kraken" in out["quotes"][0]["message"]


def test_hyperliquid_declines_non_usd_rather_than_quoting_nonsense(monkeypatch):
    """Perps are USD-margined. Returning a USD number for a EUR request would
    be a silent 8% error."""
    _route(monkeypatch)
    with pytest.raises(providers.ProviderError):
        providers.fetch_hyperliquid("BTC", "EUR")


def test_unknown_symbol_is_reported_not_guessed(monkeypatch):
    _route(
        monkeypatch,
        bodies={
            "api.kraken.com/0/public/Ticker": KRAKEN_UNKNOWN_PAIR,
            "api.kraken.com/0/public/OHLC": KRAKEN_UNKNOWN_PAIR,
            "api.coingecko.com": json.dumps({"coins": []}).encode(),
        },
        # Hyperliquid simply does not list it; the two CEXes answer with a
        # status code, exactly as they do in production.
        http_errors={"api.binance.com": 400, "api.coinbase.com": 404},
    )
    out = json.loads(tools.crypto_price({"symbols": ["NOTACOIN"]}))
    assert out["quotes"][0]["ok"] is False
    assert "NOTACOIN" in out["summary"][0]


def test_xbt_is_btc(monkeypatch):
    _route(monkeypatch)
    assert providers.get_quote("xbt")["symbol"] == "BTC"


def test_quotes_are_cached_for_the_ttl(monkeypatch):
    seen = _route(monkeypatch)
    providers.get_quote("BTC")
    first = len(seen)
    again = providers.get_quote("BTC")
    assert again["cached"] is True
    assert len(seen) == first, "a cache hit must not reach the network"


# --- tools -------------------------------------------------------------------

def test_price_accepts_a_bare_string_as_well_as_a_list(monkeypatch):
    """Models pass "BTC,ETH" often enough that refusing it is just rude."""
    _route(monkeypatch)
    out = json.loads(tools.crypto_price({"symbols": "BTC, ETH"}))
    assert [q["symbol"] for q in out["quotes"]] == ["BTC", "ETH"]


def test_price_with_no_symbols_refuses_in_the_house_shape():
    out = json.loads(tools.crypto_price({"symbols": []}))
    assert out["ok"] is False
    assert "symbols" in out["message"]


def test_history_summarises_and_downsamples(monkeypatch):
    _route(monkeypatch)
    out = json.loads(tools.crypto_history({"symbol": "BTC", "days": 7, "max_points": 10}))
    assert out["ok"] is True
    assert out["points"] <= 10
    assert out["summary"]["high"] >= out["summary"]["low"]
    assert out["candles"][-1]["close"] == 69900.0, "the newest candle must survive downsampling"


def test_history_days_are_clamped(monkeypatch):
    _route(monkeypatch)
    assert json.loads(tools.crypto_history({"symbol": "BTC", "days": 9999}))["days"] == 365
    assert json.loads(tools.crypto_history({"symbol": "BTC", "days": 0}))["days"] == 1


# --- alerts ------------------------------------------------------------------

def _create(monkeypatch, **kw):
    args = {"action": "create", "symbol": "BTC", "kind": "above", "threshold": 80000}
    args.update(kw)
    return json.loads(tools.crypto_alert(args))


def test_alert_round_trip(monkeypatch):
    _route(monkeypatch)
    created = _create(monkeypatch)
    alert_id = created["created"]["id"]
    assert created["ok"] is True

    listed = json.loads(tools.crypto_alert({"action": "list"}))
    assert listed["count"] == 1
    assert listed["alerts"][0]["description"] == "BTC above 80,000 USD"

    assert json.loads(tools.crypto_alert({"action": "delete", "alert_id": alert_id}))["ok"]
    assert json.loads(tools.crypto_alert({"action": "list"}))["count"] == 0


def test_creating_an_already_true_alert_says_so(monkeypatch):
    """Arming an alert that fires on the next tick, silently, is a trap."""
    _route(monkeypatch)
    out = _create(monkeypatch, kind="above", threshold=1)
    assert "already met" in out["already_true"]


def test_above_fires_and_a_one_shot_disables_itself(monkeypatch):
    _route(monkeypatch)
    _create(monkeypatch, kind="above", threshold=1)
    first = json.loads(tools.crypto_alert({"action": "check"}))
    assert len(first["triggered"]) == 1
    assert first["triggered"][0]["disabled_after_trigger"] is True
    second = json.loads(tools.crypto_alert({"action": "check"}))
    assert second["triggered"] == []


def test_repeat_always_with_zero_cooldown_fires_every_check(monkeypatch):
    """`or` on this argument turned an explicit 0 into the 60-minute default
    and muted the alert the user just asked to hear from constantly."""
    _route(monkeypatch)
    _create(monkeypatch, kind="above", threshold=1, repeat="always", cooldown_minutes=0)
    for _ in range(3):
        assert len(json.loads(tools.crypto_alert({"action": "check"}))["triggered"]) == 1


def test_cooldown_suppresses_a_repeat_alert(monkeypatch):
    _route(monkeypatch)
    _create(monkeypatch, kind="above", threshold=1, repeat="always", cooldown_minutes=60)
    assert len(json.loads(tools.crypto_alert({"action": "check"}))["triggered"]) == 1
    assert json.loads(tools.crypto_alert({"action": "check"}))["triggered"] == []


def test_below_does_not_fire_above_its_threshold(monkeypatch):
    _route(monkeypatch)
    _create(monkeypatch, kind="below", threshold=1)
    assert json.loads(tools.crypto_alert({"action": "check"}))["triggered"] == []


def test_pct_move_uses_the_window_change(monkeypatch):
    _route(monkeypatch)
    _create(monkeypatch, kind="pct_move", threshold=3)      # 24h change is 3.56%
    assert len(json.loads(tools.crypto_alert({"action": "check"}))["triggered"]) == 1
    _route(monkeypatch)
    _create(monkeypatch, kind="pct_move", threshold=50)
    triggered = json.loads(tools.crypto_alert({"action": "check"}))["triggered"]
    assert len(triggered) == 0 or all(t["threshold"] != 50 for t in triggered)


def test_pct_move_stays_silent_when_the_provider_gave_no_change(monkeypatch):
    """A missing datum must never read as a triggered alert."""
    _route(monkeypatch)
    _create(monkeypatch, kind="pct_move", threshold=1)
    quote = {"ok": True, "symbol": "BTC", "currency": "USD", "price": 71649.7}
    triggered, checked = alert_store.evaluate({"BTC/USD": quote})
    assert checked and triggered == []


def test_pct_from_needs_a_baseline(monkeypatch):
    _route(monkeypatch)
    out = _create(monkeypatch, kind="pct_from", threshold=5)
    assert out["created"]["kind"] == "pct_from"
    with pytest.raises(alert_store.AlertError):
        alert_store.create_alert("BTC", "pct_from", 5, baseline_price=None)


def test_bad_alert_input_refuses_in_the_house_shape(monkeypatch):
    _route(monkeypatch)
    assert json.loads(tools.crypto_alert({"action": "create", "symbol": "BTC",
                                          "kind": "sideways", "threshold": 5}))["ok"] is False
    assert json.loads(tools.crypto_alert({"action": "create", "symbol": "BTC",
                                          "kind": "above", "threshold": -5}))["ok"] is False
    assert json.loads(tools.crypto_alert({"action": "nonsense"}))["ok"] is False
    assert json.loads(tools.crypto_alert({"action": "delete",
                                          "alert_id": "nope"}))["ok"] is False


def test_alerts_never_land_in_the_plugin_directory(monkeypatch, tmp_path):
    """The plugin mount is shared by the whole fleet — one profile's alerts
    must never be visible to another, or writable from a read-only mount."""
    _route(monkeypatch)
    _create(monkeypatch)
    assert alert_store.alerts_file() == tmp_path / "crypto" / "alerts.json"
    assert alert_store.alerts_file().exists()
