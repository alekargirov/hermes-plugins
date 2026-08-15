"""tmdb — the public movie/TV database.

Ported from the standalone tmdb plugin on 2026-08-15.

The API key rides in the QUERY STRING, so it is in every URL this module
builds. `_redact` is handed to the Service so it never travels back out in an
error message.

tmdb is also the only service here with no configurable host: its only config
IS the key. That is why its Service carries no url_env, and why a connection
failure does NOT tell the operator to check TMDB_API_KEY — a read timeout is
not an auth failure, and naming the key sends them after the wrong thing. A bad
key comes back as an HTTP 401, where it is unmistakable. minimax made this
mistake too and told alek to rotate a perfectly good key.

Env (profile .env):
  TMDB_API_KEY
"""

from __future__ import annotations

import re

from ._core import Service, Tool, _schema, _n, _s

PLUGIN_VERSION = "2026-08-05.5"


def _redact(u: str) -> str:
    """The API key rides in the query string, so it is in every URL. Never let
    it back out in an error message."""
    return re.sub(r"api_key=[^&]*", "api_key=***", u)


TOOLS = [
    Tool(
        "tmdb_search",
        "Search movies or TV shows using TMDB. type: 'movie' or 'tv'.",
        _schema(
            {
                "type": _s("'movie' or 'tv'"),
                "query": _s("Search query"),
            },
            ["type", "query"],
        ),
        "GET",
        "https://api.themoviedb.org/3/search/{arg.type}?api_key={env.TMDB_API_KEY}&query={arg.query}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "tmdb_get_details",
        "Get movie or TV show details by TMDB ID. type: 'movie' or 'tv'.",
        _schema(
            {
                "type": _s("'movie' or 'tv'"),
                "id": _n("TMDB ID"),
            },
            ["type", "id"],
        ),
        "GET",
        "https://api.themoviedb.org/3/{arg.type}/{arg.id}?api_key={env.TMDB_API_KEY}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "tmdb_get_credits",
        "Get cast and crew credits for a movie or TV show by TMDB ID. type: 'movie' or 'tv'.",
        _schema(
            {
                "type": _s("'movie' or 'tv'"),
                "id": _n("TMDB ID"),
            },
            ["type", "id"],
        ),
        "GET",
        "https://api.themoviedb.org/3/{arg.type}/{arg.id}/credits?api_key={env.TMDB_API_KEY}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "tmdb_get_popular",
        "Get popular movies or TV shows from TMDB. type: 'movie' or 'tv'.",
        _schema(
            {
                "type": _s("'movie' or 'tv'"),
                "page": _n("Page number"),
            },
            ["type", "page"],
        ),
        "GET",
        "https://api.themoviedb.org/3/{arg.type}/popular?api_key={env.TMDB_API_KEY}&page={arg.page}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "tmdb_get_top_rated",
        "Get top-rated movies from TMDB.",
        _schema(
            {
                "page": _n("Page number"),
            },
            ["page"],
        ),
        "GET",
        "https://api.themoviedb.org/3/movie/top_rated?api_key={env.TMDB_API_KEY}&page={arg.page}",
        body=None,
        select=None,
        limit=None,
    ),
]


SERVICE = Service(
    name="tmdb",
    url_env=None,
    key_env="TMDB_API_KEY",
    auth_header=None,
    accept_json=True,
    redact=_redact,
    log_note="api.themoviedb.org",
    version=PLUGIN_VERSION,
    tools=TOOLS,
)
