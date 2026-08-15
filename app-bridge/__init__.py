"""app-bridge — vita3 and fin3, our own apps, in one plugin.

WHAT THIS IS
Two bridges to OUR apps. Neither holds logic: each POSTs the tool name and the
model's arguments to its app's /api/agent/tools and returns the answer. Scope,
vocabulary, ownership and identity are all enforced server-side. They were two
plugin directories until 2026-08-15, and their forward functions differed only
in which five names they used — that now lives once, in _core.py.

Not to be confused with `media`, the other merged plugin here. media talks
DIRECTLY to third-party services and owns URL templates, response shaping and
per-service auth. app-bridge does none of that: one fixed endpoint, one fixed
payload, no shaping. Two different jobs, two different cores, deliberately not
forced together.

ONE PLUGIN, TWO TOOLSETS — READ THIS BEFORE "SIMPLIFYING" IT
vita3 tools register under `vita3` and fin3 tools under `fin3`. Never a shared
toolset: fin3 used to register under `todo` and hermes' own todo schema bled
into ours, so the model told alek fin3_update_category "only supports target
and content" and refused a change the tool plainly supports.

TWO VERSIONS, NOT ONE
Each app compares the stamp the bridge sends against its own PLUGIN_VERSION and
reports a mismatch to the model. The versions are independent and must stay in
their own service files — one shared number would break both handshakes.

hermes loads plugins at PROCESS START. Editing anything here changes nothing
until the agent restarts, and for a bind-mounted plugin `docker compose
restart` is required — plain `up -d` does not reload it.
"""

from __future__ import annotations

from . import fin3, vita3
from ._core import register_bridge

BRIDGES = [vita3.BRIDGE, fin3.BRIDGE]


def register(ctx) -> None:
    for bridge in BRIDGES:
        register_bridge(ctx, bridge)
