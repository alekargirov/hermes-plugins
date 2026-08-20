# crypto

Live cryptocurrency market data for Hermes agents — spot price, true 24h/7d
change, OHLC history, and price alerts delivered to chat. No API keys, no
accounts, stdlib only.

## Tools

| Tool | What it answers |
|---|---|
| `crypto_price` | "What's BTC at?" — price, 24h/7d change, 24h high/low/volume, for one or many symbols, in any fiat |
| `crypto_history` | "How has ETH done this month?" — OHLC candles plus start/end/change/high/low |
| `crypto_alert` | "Tell me when BTC hits 80k" — create / list / delete / enable / disable / check alerts |

Plus a `/crypto` slash command:

```
/crypto                  # BTC and ETH
/crypto BTC ETH SOL      # named symbols
/crypto eur BTC          # another fiat
/crypto history BTC 30   # 30-day summary
/crypto alerts           # list alerts
/crypto check            # evaluate alerts now
```

## Data sources

Tried in order until one answers, so a single exchange being down, rate-limited
or geo-blocked does not remove the capability:

1. **Kraken** — global spot exchange. Bid/ask, 24h high/low/volume. True 24h and
   7d change come from a second OHLC call, because Kraken's ticker only exposes
   *today's* UTC open — reporting that as "24h change" would be wrong by up to
   23 hours.
2. **Hyperliquid** — one POST returns 230+ assets (cached ~15s), and adds funding
   rate and open interest. Quotes the perp *oracle* price, USD only.
3. **Binance** — true 24h change in one call; geo-blocked in some regions.
4. **Coinbase** — spot only; the most reliable last resort.
5. **CoinGecko** — aggregated (~1-2 min lag), carries market cap, and covers
   long-tail coins the exchanges above do not list.

Quotes are cached for 20 seconds, so several agents asking at once produce one
upstream request.

## Install

For the fleet, this directory ships in `hermes-plugins` and is mounted with the
rest; enable it per profile with `plugins.enabled`. For a plain Hermes home:

```bash
./install.sh                        # into $HERMES_HOME, or ~/.hermes
HERMES_HOME=/path/to/profile ./install.sh   # into a specific profile
hermes plugins enable crypto
```

Verify:

```bash
hermes plugins list | grep crypto
hermes tools | grep crypto
```

## Alerts

Alerts live in `$HERMES_HOME/crypto/alerts.json`. Kinds:

- `above` / `below` — absolute price thresholds.
- `pct_move` — absolute change over a rolling `24h` or `7d` window exceeds N%.
- `pct_from` — moved N% from the price captured when the alert was created.

`repeat: once` (default) disables the alert after it fires; `repeat: always`
re-arms after `cooldown_minutes` (default 60; set 0 to fire on every check).

Creating an alert whose condition is *already* true returns an `already_true`
warning rather than silently arming something that fires on the next tick.

### Scheduling the checks

`hermes cron --script` only accepts real files inside `$HERMES_HOME/scripts`
(symlinks are resolved and rejected), so copy the checker there:

```bash
./install.sh          # does this, plus copying the plugin itself
```

**Cheap mode (recommended)** — no LLM in the loop, silent unless something fires:

```bash
hermes cron create "*/10 * * * *" \
  --script crypto_alerts_quiet.py --no-agent \
  --name "Crypto alerts" --deliver telegram
```

The cron runner invokes scripts as `python3 <path>` with no arguments, which is
why the quiet mode ships as its own entry point rather than a `--quiet` flag on
the job. With `--no-agent`, empty stdout means no message is delivered.

**Agent mode** — the agent sees the check output and can add context:

```bash
hermes cron create "*/10 * * * *" \
  "The crypto alert checker ran; its output is above. If it says \
NO_ALERTS_TRIGGERED, reply with exactly [SILENT] and nothing else. \
Otherwise tell me plainly what fired and what the price is now." \
  --script crypto_alerts.py \
  --name "Crypto alerts" --deliver telegram
```

The checker can also be run by hand:

```bash
python3 scripts/check_alerts.py            # human-readable
python3 scripts/check_alerts.py --json     # machine-readable
python3 scripts/check_alerts.py --quiet    # prints only when an alert fires
```

## Layout

```
crypto/
├── plugin.yaml              manifest
├── __init__.py              register() — tools + /crypto command
├── schemas.py               tool schemas (what the model reads)
├── tools.py                 handlers
├── providers.py             the provider fallback chain
├── alerts.py                alert store (flock + atomic writes) and evaluation
├── install.sh               copy into a Hermes home + wire up the cron scripts
└── scripts/
    ├── check_alerts.py       standalone checker (verbose / --json / --quiet)
    └── check_alerts_quiet.py silent entry point for `hermes cron --no-agent`
```

## Tests

```bash
cd hermes-plugins && python3 -m pytest tests/test_crypto.py -q
```

The suite never touches the network: `urlopen` is monkeypatched with recorded
response bodies, and the alert tests point `HERMES_HOME` at a tmp_path.
