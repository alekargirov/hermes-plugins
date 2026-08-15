"""Shared core for the app-bridge plugin — the forward, written ONCE.

A BRIDGE, not a direct plugin. vita3 and fin3 are OUR apps. The bridge holds no
logic beyond forwarding: it POSTs the tool name and the model's arguments to
the app's /api/agent/tools and returns whatever comes back. Scope, vocabulary,
ownership and identity are all decided server-side.

Identity rides in two places, checked against each other by the app:
  - user_id: this profile's own <APP>_USER_ID, from the profile .env, put there
    by the operator. The model never sees it and cannot set it.
  - session_id: the dispatch context (the turn id the app minted), delivered to
    the handler in code, never through the model.
The app resolves the turn and refuses any call where the two disagree.

<APP>_USER_ID IS OPTIONAL AND DELIBERATELY UNGUARDED. One container per person
sets it and gets a cross-check; one shared container leaves it unset and the
turn alone decides. fin3's default profile has none on purpose and can
therefore act for nobody. A guard here would break both arrangements.

Until 2026-08-15 this was two directories, vita3-bridge and fin3-bridge, whose
_forward functions differed only in which five names they used.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import NamedTuple


class Bridge(NamedTuple):
    """One of our apps behind the bridge.

    version is PER APP and must stay that way. Each app compares the stamp
    against its own PLUGIN_VERSION (vita-srv-v3's, and fin's
    src/lib/server/tool-hints.ts) and reports a mismatch to the model. Merging
    the two directories must not merge the two version lines — one shared
    number would break both handshakes at once.
    """

    name: str  # the toolset, and the tool-name prefix
    label: str  # what failures call this bridge
    url_env: str
    key_env: str
    key_header: str
    user_env: str
    no_user_note: str  # what the registration line says when user_env is unset
    version: str
    tools: list


def _env(name: str) -> str:
    """Profile-scoped credential read. The multiplexed gateway keeps each
    profile's .env in an isolated per-turn secret scope and never mutates
    os.environ — a bare os.environ.get returns another profile's value or
    nothing. On a single-profile gateway get_secret falls through to
    os.environ, so both modes work."""
    try:
        from agent.secret_scope import get_secret

        val = get_secret(name, "")
    except Exception:
        val = os.environ.get(name, "")
    return val or ""


def _forward(bridge: Bridge, tool: str, args: dict, session_id) -> str:
    # THE GUARDS BELOW ARE NOT DECORATION.
    # Neither bridge had them until 2026-08-15. With the URL unset, _forward
    # built the relative address "/api/agent/tools" and failed with a message
    # naming neither the URL nor the variable — so a port-less VITA3_URL read
    # as a broken plugin instead of a typo, and cost alek hours on prod. notes
    # was fixed after that incident and the bridges were not; the test that
    # records it is tests/test_notes.py. Refuse before firing, and name the
    # variable, never the value.
    if not _env(bridge.url_env):
        return json.dumps(
            {"ok": False, "message": f"{bridge.url_env} is not set for this profile"}
        )
    if not _env(bridge.key_env):
        return json.dumps(
            {"ok": False, "message": f"{bridge.key_env} is not set for this profile"}
        )

    url = _env(bridge.url_env).rstrip("/") + "/api/agent/tools"
    payload = {
        "tool": tool,
        "session_id": session_id,
        "user_id": _env(bridge.user_env),
        "args": args or {},
        "plugin_version": bridge.version,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            bridge.key_header: _env(bridge.key_env),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        return json.dumps(
            {"ok": False, "message": f"endpoint HTTP {e.code}: {e.read().decode()[:300]}"}
        )
    except Exception as e:  # noqa: BLE001 — surface it, never crash the turn
        # The URL is in the message on purpose: without it a wrong host reads
        # as a broken plugin rather than a typo. The credential is a header,
        # never part of the URL, so there is nothing here to redact.
        return json.dumps(
            {
                "ok": False,
                "message": (
                    f"{bridge.label} unreachable at {url} "
                    f"— check {bridge.url_env}: {e}"
                ),
            }
        )


def _make_handler(bridge: Bridge, tool: str):
    def _handler(args: dict, session_id: str = None, **kwargs) -> str:
        return _forward(bridge, tool, args, session_id)

    return _handler


def _s(d):
    return {"type": "string", "description": d}


def _n(d):
    return {"type": "number", "description": d}


def _b(d):
    return {"type": "boolean", "description": d}


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


def _fn_schema(name: str, description: str, params: dict) -> dict:
    """hermes registers `schema` VERBATIM as the OpenAI `function` object, so
    name and description must live INSIDE it and the argument schema must sit
    under `parameters`. Registering a bare {"type":"object","properties":...}
    leaves `function.parameters` absent; the schema sanitizer then substitutes
    an empty {"type":"object","properties":{}} and the model sees a tool with
    no arguments and no description. See _template/tool_schema.py."""
    return {"name": name, "description": description, "parameters": params}


def register_bridge(ctx, bridge: Bridge) -> None:
    """Register one app under ITS OWN toolset, then log where it points.

    Never a shared toolset. fin3 used to register under `todo`, and hermes' own
    todo schema bled into ours — the model told alek fin3_update_category "only
    supports target and content" and refused a change the tool plainly
    supports. Both apps have had their own toolset since, and the merge does
    not undo that.

    The tool count in this line is the operational check: after any change,
    the container log must say the number this file registers.
    """
    for name, description, schema in bridge.tools:
        ctx.register_tool(
            name=name,
            toolset=bridge.name,
            schema=_fn_schema(name, description, schema),
            handler=_make_handler(bridge, name),
            description=description,
        )
    # _env, not os.environ: under the multiplexed gateway the profile's value
    # lives in the secret scope, so os.environ.get printed "(unset)" for a URL
    # that was set. The old line reported a healthy bridge as misconfigured.
    #
    # The version is in the line because a stale plugin is the failure mode
    # that keeps costing time: hermes loads plugins at PROCESS START, so
    # editing a bridge changes nothing until the agent restarts. "registered
    # N tools" is still the substring to grep for.
    print(
        f"[{bridge.label}] registered {len(bridge.tools)} tools "
        f"(v{bridge.version}) -> "
        f"{_env(bridge.url_env) or f'({bridge.url_env} unset)'} "
        f"as user {_env(bridge.user_env) or bridge.no_user_note}",
        flush=True,
    )
