"""btc — bridge to btc-srv, the BTC/ETH position portal.

The plugin holds NO logic beyond forwarding. Every judgement — decay weights,
invalidation, cost basis, superseding a thesis — is btc-srv's, because a
deterministic rail beats prompt discipline (build-discipline §5).

FLEET-WIDE by alek's decision: this lives in hermes-plugins rather than inside
the app repo, so any profile can enable it with `plugins.enabled`. Single user,
so unlike fin3-bridge there is no BTC_USER_ID — there is nobody to act *as*.

Env (profile .env):
  BTC_URL       e.g. http://btc:3024 on tfk-net, or https://btc.dev.pica.win
  BTC_TOOL_KEY  shared with btc-srv's TOOL_ENDPOINT_KEY

Three lessons carried from hermes-plugins/crypto, each paid for once already:
  * tool names are GLOBAL and the registry refuses duplicates, so everything is
    namespaced btc_*;
  * every connection error names BTC_URL — a bare errno gets softened by the
    model into "I couldn't retrieve that", and the address IS the diagnosis;
  * a missing key refuses BY NAME before the request goes out, rather than
    letting btc-srv's bare 401 surface as "the backend is down".
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# hermes loads plugins at PROCESS START. Copying this file to the agent host
# changes nothing until the agent restarts; btc-srv compares this stamp against
# its own PLUGIN_VERSION and says so in the tool's own answer. Bump BOTH
# whenever a tool is added or removed.
PLUGIN_VERSION = "2026-08-20.1"

TIMEOUT = 60


def _env(name: str) -> str:
    """Profile-scoped credential read.

    The multiplexed gateway keeps each profile's .env in a per-turn secret scope
    and never mutates os.environ, so a bare os.environ.get returns another
    profile's value or nothing at all.
    """
    try:
        from agent.secret_scope import get_secret

        val = get_secret(name, "")
    except Exception:
        val = os.environ.get(name, "")
    return val or ""


def _forward(tool: str, args: dict) -> str:
    base = _env("BTC_URL").rstrip("/")
    key = _env("BTC_TOOL_KEY")

    # Refuse by NAME, before the request. Never the value.
    if not base:
        return json.dumps({"ok": False, "message": "BTC_URL is not set in this profile's .env"})
    if not key:
        return json.dumps({"ok": False, "message": "BTC_TOOL_KEY is not set in this profile's .env"})

    url = base + "/api/agent/tools"
    payload = {"tool": tool, "args": args or {}, "plugin_version": PLUGIN_VERSION}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-btc-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        return json.dumps(
            {"ok": False, "message": f"btc-srv at {url} returned HTTP {e.code}: {e.read().decode()[:300]}"}
        )
    except Exception as e:  # noqa: BLE001 — surface it, never crash the turn
        return json.dumps({"ok": False, "message": f"btc-srv unreachable at BTC_URL={url}: {e}"})


def _make_handler(tool: str):
    # hermes passes its own keywords (session_id, task_id, user_task) alongside
    # the model's args; without **kwargs this dies with TypeError on task_id.
    def _handler(args: dict, session_id: str = None, **kwargs) -> str:
        return _forward(tool, args or {})

    return _handler


def _s(d):
    return {"type": "string", "description": d}


def _n(d):
    return {"type": "number", "description": d}


def _tool(name, description, properties, required=(), emoji="\U0001FA99"):
    """One tool, in the shape hermes actually consumes.

    NOT a bare JSON Schema. hermes wants {name, description, parameters} and the
    sanitizer substitutes an EMPTY parameters block for anything missing one —
    which the model then sees as a tool that takes no arguments, with nothing
    logged anywhere. Shape copied from hermes-plugins/crypto/schemas.py, which
    is the known-working example (build-discipline #13).
    """
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": list(required),
        },
        "_emoji": emoji,
    }


_TOOLS = [
    _tool(
        "btc_snapshot",
        "Every live BTC/ETH market metric with its decayed WEIGHT and age in hours. "
        "Your training data is stale and spot moves by the minute — call this before "
        "saying what anything is worth. A weight near 1 is current; a low weight means "
        "the datum is old and must be quoted AS old. Covers price, the native ETH/BTC "
        "ratio, funding rate, open interest, MVRV, mempool fees, Fear & Greed, and "
        "macro (dollar index, M2, fed funds, 10y yield, inflation breakeven, Fed "
        "balance sheet).",
        {},
    ),
    _tool(
        "btc_notes",
        "List pasted market analysis, or save a new piece. Notes are OPINIONS, not "
        "data. When saving, always try to capture an invalidation level: "
        "invalidatePrice plus invalidateDirection, where the direction is the way "
        "price must move to PROVE THE NOTE WRONG. 'BTC stays under 68k' is a ceiling "
        "-> direction 'above'. 'BTC holds 68k' is a floor -> direction 'below'. "
        "Without a level the note can only expire, can never be proven wrong, and its "
        "author never accumulates a track record.",
        {
            "action": _s("'list' (default) or 'create'"),
            "title": _s("Short title, for create"),
            "body": _s("The analysis itself, for create"),
            "author": _s("Who said it — this is how track records accumulate"),
            "sourceUrl": _s("Where it came from"),
            "subject": _s("BTC, ETH or ROTATION (default BTC)"),
            "confidence": _n("How much the USER believes it, 1-10"),
            "invalidateAsset": _s("Asset the level applies to (default = subject)"),
            "invalidatePrice": _n("Price at which this note is proven wrong"),
            "invalidateDirection": _s("'above' busts a ceiling claim; 'below' busts a floor claim"),
            "limit": _n("Max notes to list (default 50)"),
        },
    ),
    _tool(
        "btc_position",
        "alek's actual holdings: amount, weighted-average cost, realised and "
        "unrealised P&L against live spot. Use action 'record' to log a buy or sell "
        "he tells you about. Cost basis is WEIGHTED-AVERAGE, not FIFO — never present "
        "these figures as tax numbers. A sell larger than the holding is refused, "
        "never clamped.",
        {
            "action": _s("'show' (default) or 'record'"),
            "asset": _s("BTC or ETH"),
            "side": _s("'buy' or 'sell'"),
            "amount": _n("Units of the asset, must be positive"),
            "priceUsd": _n("Price per unit in USD"),
            "feeUsd": _n("Fee in USD (default 0)"),
            "executedAt": _s("ISO date/time (default now)"),
            "note": _s("Why he did it"),
        },
    ),
    _tool(
        "btc_thesis",
        "The current thesis for BTC, ETH and ROTATION: stance, confidence, horizon, "
        "sell/buy levels, and every input with its live weight. Also reports whether a "
        "resynthesis is due and WHY. Read this before offering a view — the point is "
        "to build on the standing thesis and its evidence rather than improvise a "
        "fresh opinion each time.",
        {},
    ),
    _tool(
        "btc_thesis_write",
        "Replace the thesis for one subject. The previous one is superseded and KEPT — "
        "the archive of what was believed and when is the whole point, so never try to "
        "delete one. Levels and inputs MUST be passed as structured arguments: "
        "describing a sell level in the narrative does not create one, and the "
        "dashboard will show that you set none. Cite evidence in `inputs`, including "
        "what UNDERMINES the thesis — one with nothing against it is displayed as a "
        "red flag.",
        {
            "subject": _s("BTC, ETH or ROTATION"),
            "stance": _s("Short verdict, e.g. 'mildly bullish' or 'trim into strength'"),
            "confidence": _n("1-10, whole number"),
            "narrative": _s("The reasoning, in plain language. Commentary only — never parsed for numbers."),
            "horizonStart": _s("YYYY-MM-DD (default today)"),
            "horizonEnd": _s("YYYY-MM-DD — when this thesis should be judged"),
            "levels": {
                "type": "array",
                "description": "Price levels that make this actionable. Each: kind (sell|buy|invalidate|rotate), price, fraction (0-1, portion of the stack), rationale.",
                "items": {"type": "object"},
            },
            "inputs": {
                "type": "array",
                "description": "Evidence. Each cites exactly one observationId OR one noteId, with direction 'supports' or 'undermines' and a rationale.",
                "items": {"type": "object"},
            },
        },
        required=("subject", "stance", "confidence", "narrative", "horizonEnd"),
    ),
]


def register(ctx) -> None:
    """Register every btc_* tool under its OWN `btc` toolset.

    Names are GLOBAL in hermes and the registry refuses duplicates, with the
    loser decided by import order and nothing logged where you would look —
    hence the btc_ prefix on every one.
    """
    for schema in _TOOLS:
        ctx.register_tool(
            name=schema["name"],
            toolset="btc",
            schema=schema,
            handler=_make_handler(schema["name"]),
            description=schema["description"],
            emoji=schema["_emoji"],
        )

    print(
        f"[btc] registered {len(_TOOLS)} tools (v{PLUGIN_VERSION}) -> "
        f"BTC_URL={_env('BTC_URL') or '(unset)'} "
        f"(BTC_TOOL_KEY {'set' if _env('BTC_TOOL_KEY') else 'MISSING'})",
        flush=True,
    )
