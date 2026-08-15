"""plex — the player, not a library manager.

Ported from the standalone plex plugin on 2026-08-15. Auth is X-Plex-Token,
and the Accept header matters: without it Plex answers XML and the model gets
a wall of markup it cannot parse.

Env (profile .env):
  PLEX_URL    e.g. http://plex:32400
  PLEX_TOKEN  a Plex auth token
"""

from __future__ import annotations

from ._core import Service, Tool, _schema, _s

PLUGIN_VERSION = "2026-08-05.4"


TOOLS = [
    Tool(
        "plex_now_playing",
        "Get currently active Plex playback sessions.",
        _schema({}),
        "GET",
        "{env.PLEX_URL}/status/sessions",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "plex_on_deck",
        "Get Plex on-deck (continue watching) items.",
        _schema({}),
        "GET",
        "{env.PLEX_URL}/library/onDeck",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "plex_recently_added",
        "Get recently added content in Plex.",
        _schema({}),
        "GET",
        "{env.PLEX_URL}/library/recentlyAdded",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "plex_search",
        "Search the Plex library.",
        _schema(
            {
                "query": _s("Search query"),
            },
            ["query"],
        ),
        "GET",
        "{env.PLEX_URL}/search?query={arg.query}",
        body=None,
        select=None,
        limit=None,
    ),
]


SERVICE = Service(
    name="plex",
    url_env="PLEX_URL",
    key_env="PLEX_TOKEN",
    auth_header="X-Plex-Token",
    accept_json=True,
    redact=None,
    log_note=None,
    version=PLUGIN_VERSION,
    tools=TOOLS,
)
