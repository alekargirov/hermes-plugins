"""radarr — Hermes plugin for Radarr.

A DIRECT plugin: Radarr is third-party software on the LAN, so there is no
endpoint of ours to forward to and this file owns the HTTP call.

Auth is Radarr's own `X-Api-Key`. Single-tenant — there is no user id and
nothing to scope, because everyone shares one movie library.

Env (profile .env):
  RADARR_URL      e.g. http://radarr:7878
  RADARR_API_KEY  Radarr's API key (Settings -> General)

Tool descriptions and URL templates port VERBATIM from
srv-mcp-yaml/radarr.yaml.

`render` and `shape` are copied from _template/url_template.py, which is the
readable spec with the tests. hermes loads every plugin directory
independently, so there is no shared import path — the duplication is the cost
of that, and _template/ is where a rule change starts.

radarr_library declares `select`: a full Radarr movie object is enormous and
there are thousands of them, so the tool projects each row down to six fields.
Without that the model gets a truncated wall of JSON instead of a usable list.
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

PLUGIN_VERSION = "2026-08-05.8"

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
            # env tokens carry defaults too: {env.CAL_URL|http://cal:3020}.
            # Splitting only on the arg branch left the whole
            # "CAL_URL|http://cal:3020" being looked up as a variable name,
            # which resolved to empty and produced a relative URL.
            name, _, default = rest.lstrip(".").partition("|")
            return _env(name) or default
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


def _call(tool: Tool, args: dict) -> str:
    if not _env("RADARR_URL"):
        return json.dumps(
            {"ok": False, "message": "RADARR_URL is not set for this profile"}
        )
    key = _env("RADARR_API_KEY")
    if not key:
        # Without this the request goes out with an empty X-Api-Key and the
        # service answers a bare 401, which the agent reports as a broken
        # backend rather than one missing line in the profile .env. Name the
        # variable, never the value.
        return json.dumps(
            {"ok": False, "message": "RADARR_API_KEY is not set for this profile"}
        )
    url = _render(tool.url, args, quote=True)
    headers = {"X-Api-Key": key, "Accept": "application/json"}

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
            {"ok": False, "message": f"radarr HTTP {e.code}: {e.read().decode()[:300]}"}
        )
    except Exception as e:  # noqa: BLE001 — surface it, never crash the turn
        return json.dumps(
            {"ok": False, "message": f"radarr unreachable at {url} — check RADARR_URL: {e}"}
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
        "radarr_library",
        "List all movies in the Radarr library (id, title, year, tmdbId, hasFile, monitored). Trimmed to essential fields so large libraries return complete and untruncated. Use the id field with radarr_delete to remove movies.",
        _schema({}),
        "GET",
        "{env.RADARR_URL}/api/v3/movie",
        body=None,
        select=["id", "title", "year", "tmdbId", "hasFile", "monitored"],
        limit=None,
    ),
    Tool(
        "radarr_search",
        "Search for a movie in Radarr (lookup, not library search). Matched against title.",
        _schema(
            {
                "query": _s("Movie title to search for"),
            },
            ["query"],
        ),
        "GET",
        "{env.RADARR_URL}/api/v3/movie/lookup?term={arg.query}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "radarr_add",
        "Add a movie to Radarr. Use radarr_search first to get tmdbId and titleSlug.",
        _schema(
            {
                "tmdbId": _n("TMDB id from radarr_search"),
                "title": _bs(),
                "titleSlug": _bs(),
                "qualityProfileId": _bn(),
                "rootFolderPath": _bs(),
                "monitored": _bb(),
            },
            ["tmdbId", "title", "titleSlug", "qualityProfileId", "rootFolderPath"],
        ),
        "POST",
        "{env.RADARR_URL}/api/v3/movie",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "radarr_delete",
        "Delete a movie from Radarr by its id. Set deleteFiles=true to also remove files on disk. Get the id from radarr_library.",
        _schema(
            {
                "id": _n("Radarr movie id (from radarr_library)"),
                "deleteFiles": _b("Also remove files on disk (default false)"),
            },
            ["id"],
        ),
        "DELETE",
        "{env.RADARR_URL}/api/v3/movie/{arg.id}?deleteFiles={arg.deleteFiles|false}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "radarr_queue",
        "Get the Radarr download queue.",
        _schema({}),
        "GET",
        "{env.RADARR_URL}/api/v3/queue?includeMovie=true",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "radarr_wanted",
        "Get missing/wanted movies from Radarr.",
        _schema({}),
        "GET",
        "{env.RADARR_URL}/api/v3/wanted/missing?pageSize=50",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "radarr_rootfolder",
        "List Radarr root folders (id, path, accessible, freeSpace). Call before radarr_add to get a valid rootFolderPath (use the path value).",
        _schema({}),
        "GET",
        "{env.RADARR_URL}/api/v3/rootfolder",
        body=None,
        select=["id", "path", "accessible", "freeSpace"],
        limit=None,
    ),
    Tool(
        "radarr_qualityprofile",
        "List Radarr quality profiles (id, name). Call before radarr_add to get a valid qualityProfileId (use the id).",
        _schema({}),
        "GET",
        "{env.RADARR_URL}/api/v3/qualityprofile",
        body=None,
        select=["id", "name"],
        limit=None,
    ),
]


def _fn_schema(name: str, description: str, params: dict) -> dict:
    """hermes registers `schema` VERBATIM as the OpenAI `function` object, so
    name and description must live INSIDE it and the argument schema must sit
    under `parameters`. Registering a bare {"type":"object","properties":...}
    leaves `function.parameters` absent; the schema sanitizer then substitutes
    an empty {"type":"object","properties":{}} and the model sees a tool with
    no arguments and no description. See _template/tool_schema.py."""
    return {"name": name, "description": description, "parameters": params}


def register(ctx) -> None:
    for tool in TOOLS:
        ctx.register_tool(
            name=tool.name,
            toolset="radarr",
            schema=_fn_schema(tool.name, tool.description, tool.schema),
            handler=_make_handler(tool),
            description=tool.description,
        )
    print(
        f"[radarr] registered {len(TOOLS)} tools (v{PLUGIN_VERSION}) -> "
        f"{_env('RADARR_URL') or '(RADARR_URL unset)'}",
        flush=True,
    )
