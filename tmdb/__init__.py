"""tmdb — Hermes plugin for The Movie Database.

A DIRECT plugin against a public API. The base URL is literal
(https://api.themoviedb.org/3) — there is no TMDB_URL, only a key, and TMDB
takes it as a QUERY PARAMETER rather than a header.

That has a consequence this file has to handle: the key ends up inside every
URL, so it must never be echoed back in an error message. `_redact` strips it.

Single-tenant: a public catalogue, nothing user-scoped.

Env (profile .env):
  TMDB_API_KEY  a TMDB v3 API key

Tool descriptions and URL templates port VERBATIM from srv-mcp-yaml/tmdb.yaml.
"""


from __future__ import annotations

import datetime as _dt
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import NamedTuple, Optional

PLUGIN_VERSION = "2026-08-05.5"

_NOW = re.compile(r"\{now([^}]*)\}")
_TOKEN = re.compile(r"\{(env|arg)([^}]*)\}")
_NOW_SHIFT = re.compile(r"^([+-])(\d+)d$")


class Tool(NamedTuple):
    name: str
    description: str
    schema: dict
    method: str
    url: str
    body: Optional[str] = None
    select: Optional[list] = None
    limit: Optional[int] = None


def _env(name: str, default: str = "") -> str:
    try:
        from agent.secret_scope import get_secret

        val = get_secret(name, "")
    except Exception:
        val = os.environ.get(name, "")
    return val or default


def _now(expr: str) -> str:
    today = _dt.date.today()
    m = _NOW_SHIFT.match(expr)
    if m:
        d = int(m.group(2))
        today = today + _dt.timedelta(days=d if m.group(1) == "+" else -d)
    return today.isoformat()


def _render(template: str, args: dict, *, quote: bool) -> str:
    """See _template/url_template.py. Date macros resolve first, over the whole
    template, because they appear inside defaults."""
    args = args or {}
    template = _NOW.sub(lambda m: _now(m.group(1)), template)

    def sub(m: re.Match) -> str:
        kind, rest = m.group(1), m.group(2)
        if kind == "env":
            return _env(rest.lstrip("."))
        name, _, default = rest.lstrip(".").partition("|")
        val = args.get(name)
        if val is None or val == "":
            val = default
        if isinstance(val, bool):
            val = "true" if val else "false"
        val = str(val)
        return urllib.parse.quote(val, safe="") if quote else val

    return _TOKEN.sub(sub, template)


def _shape(text: str, select, limit) -> str:
    if not select and limit is None:
        return text
    try:
        data = json.loads(text)
    except Exception:
        return text
    if not isinstance(data, list):
        return text
    items = data[:limit] if limit is not None else data
    if select:
        items = [
            {f: i.get(f) for f in select} if isinstance(i, dict) else i for i in items
        ]
    return json.dumps(items)


def _redact(u: str) -> str:
    """The API key rides in the query string, so it is in every URL. Never let
    it back out in an error message."""
    return re.sub(r"api_key=[^&]*", "api_key=***", u)


def _call(tool: Tool, args: dict) -> str:
    if not _env("TMDB_API_KEY"):
        return json.dumps(
            {"ok": False, "message": "TMDB_API_KEY is not set for this profile"}
        )
    url = _render(tool.url, args, quote=True)
    headers = {"Accept": "application/json"}

    data = None
    if tool.body is not None:
        headers["Content-Type"] = "application/json"
        data = _render(tool.body, args, quote=False).encode()
    elif tool.method in ("POST", "PUT"):
        headers["Content-Type"] = "application/json"
        data = json.dumps(args or {}).encode()

    req = urllib.request.Request(url, data=data, headers=headers, method=tool.method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return _shape(resp.read().decode(), tool.select, tool.limit)
    except urllib.error.HTTPError as e:
        return json.dumps(
            {"ok": False, "message": f"tmdb HTTP {e.code}: {e.read().decode()[:300]}"}
        )
    except Exception as e:  # noqa: BLE001 — surface it, never crash the turn
        return json.dumps(
            {"ok": False, "message": f"tmdb unreachable at {_redact(url)} — check TMDB_API_KEY: {e}"}
        )


def _make_handler(tool: Tool):
    def _handler(args: dict, session_id: str = None, **kwargs) -> str:
        return _call(tool, args)

    return _handler


def _s(d):
    return {"type": "string", "description": d}


def _n(d):
    return {"type": "number", "description": d}


def _b(d):
    return {"type": "boolean", "description": d}


def _bs():
    return {"type": "string"}


def _bn():
    return {"type": "number"}


def _bb():
    return {"type": "boolean"}


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


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


def register(ctx) -> None:
    for tool in TOOLS:
        ctx.register_tool(
            name=tool.name,
            toolset="tmdb",
            schema=tool.schema,
            handler=_make_handler(tool),
            description=tool.description,
        )
    print(
        f"[tmdb] registered {len(TOOLS)} tools (v{PLUGIN_VERSION}) -> "
        f"{_env('TMDB_API_KEY') or '(TMDB_API_KEY unset)'}",
        flush=True,
    )
