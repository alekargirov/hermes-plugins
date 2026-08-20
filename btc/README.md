# btc

Bridge to **btc-srv** — the BTC/ETH position portal. Forwards `btc_*` tool calls
to the app's `/api/agent/tools`; every judgement lives in the app.

| tool | answers |
|---|---|
| `btc_snapshot` | every live metric with its decayed weight and age |
| `btc_notes` | list / save pasted analysis, with an invalidation level |
| `btc_position` | holdings, weighted-average cost, realised + unrealised P&L; record a trade |
| `btc_thesis` | the current thesis per subject, its levels, its inputs and their weights |
| `btc_thesis_write` | replace a thesis — levels and inputs as structured arguments |

## Env (per profile `.env`)

```
BTC_URL=http://btc:3024          # container-to-container on tfk-net
BTC_TOOL_KEY=<btc-srv TOOL_ENDPOINT_KEY>
```

**Which URL.** From an agent container on `tfk-net`, use `http://btc:3024`. A
public `https://btc.dev.pica.win` from inside the network hairpins through
traefik and 404s — the same trap that sent every vita3 call to port 80 for
hours. Use the public address only from a host that is genuinely outside.

Get the key with:

```bash
grep '^TOOL_ENDPOINT_KEY=' /home/apps/btc-srv/.env.secrets
```

Single-user, so there is no `BTC_USER_ID`.

## Enable

```bash
hermes plugins enable btc
# then restart the agent — plugins load at PROCESS START
```

The app stamps its own `PLUGIN_VERSION` against the one this file sends and says
so in the tool's answer when they differ, because "unknown tool" from a stale
plugin looks exactly like a broken backend.

## Why the direction field reads the way it does

`invalidateDirection` names the direction price must move to **falsify** the
note, not the side of the level it sits on:

- `above` busts a **ceiling** — *"BTC stays under 68k"*.
- `below` busts a **floor** — *"BTC holds 68k"*.

Same number, opposite claims. Getting it backwards produces a bust that never
fires, and nothing errors.
