"""Tool handlers — what runs when the LLM calls each plex tool.

Every handler delegates to ``_http.execute`` with its spec. Generated from the
legacy MCP YAML; do not edit by hand.
"""
from __future__ import annotations

from ._http import execute


_SPECS = {
    "plex_now_playing": {
        "method": "GET",
        "url": "{env.PLEX_URL}/status/sessions",
        "headers": {
            "X-Plex-Token": "{env.PLEX_TOKEN}",
            "Accept": "application/json"
        }
    },
    "plex_on_deck": {
        "method": "GET",
        "url": "{env.PLEX_URL}/library/onDeck",
        "headers": {
            "X-Plex-Token": "{env.PLEX_TOKEN}",
            "Accept": "application/json"
        }
    },
    "plex_recently_added": {
        "method": "GET",
        "url": "{env.PLEX_URL}/library/recentlyAdded",
        "headers": {
            "X-Plex-Token": "{env.PLEX_TOKEN}",
            "Accept": "application/json"
        }
    },
    "plex_search": {
        "method": "GET",
        "url": "{env.PLEX_URL}/search?query={arg.query}",
        "headers": {
            "X-Plex-Token": "{env.PLEX_TOKEN}",
            "Accept": "application/json"
        }
    }
}


def plex_now_playing(args: dict, **kwargs) -> str:
    return execute(_SPECS["plex_now_playing"], args)


def plex_on_deck(args: dict, **kwargs) -> str:
    return execute(_SPECS["plex_on_deck"], args)


def plex_recently_added(args: dict, **kwargs) -> str:
    return execute(_SPECS["plex_recently_added"], args)


def plex_search(args: dict, **kwargs) -> str:
    return execute(_SPECS["plex_search"], args)



