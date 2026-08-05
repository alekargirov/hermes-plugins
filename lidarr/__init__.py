"""lidarr — Hermes plugin for Lidarr.

A DIRECT plugin: Lidarr is third-party software on the LAN, so there is no
endpoint of ours to forward to and this file owns the HTTP call. Auth is
Lidarr's own X-Api-Key. Single-tenant — one shared library, so there is no
user id and nothing to scope.

Env (profile .env):
  LIDARR_URL      e.g. http://lidarr:8686
  LIDARR_API_KEY  Lidarr's API key (Settings -> General)

Tool descriptions and URL templates port VERBATIM from srv-mcp-yaml/lidarr.yaml.
`_render` and `_shape` are copied from _template/url_template.py, which is the
readable spec with the tests — a rule change starts there.
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

PLUGIN_VERSION = "2026-08-05.9"

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
    if not _env("LIDARR_URL"):
        return json.dumps(
            {"ok": False, "message": "LIDARR_URL is not set for this profile"}
        )
    key = _env("LIDARR_API_KEY")
    if not key:
        # Without this the request goes out with an empty X-Api-Key and the
        # service answers a bare 401, which the agent reports as a broken
        # backend rather than one missing line in the profile .env. Name the
        # variable, never the value.
        return json.dumps(
            {"ok": False, "message": "LIDARR_API_KEY is not set for this profile"}
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
            {"ok": False, "message": f"lidarr HTTP {e.code}: {e.read().decode()[:300]}"}
        )
    except Exception as e:  # noqa: BLE001 — surface it, never crash the turn
        return json.dumps(
            {"ok": False, "message": f"lidarr unreachable at {url} — check LIDARR_URL: {e}"}
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
        "lidarr_library",
        "List all artists in the Lidarr library (id, artistName, foreignArtistId, monitored). Use the id with lidarr_delete to remove artists.",
        _schema({}),
        "GET",
        "{env.LIDARR_URL}/api/v1/artist",
        body=None,
        select=["id", "artistName", "foreignArtistId", "monitored"],
        limit=None,
    ),
    Tool(
        "lidarr_search",
        "Search for an artist in Lidarr (lookup, not library search). Returns candidates with foreignArtistId (MusicBrainz id) needed by lidarr_add.",
        _schema(
            {
                "query": _s("Artist name to search for"),
            },
            ["query"],
        ),
        "GET",
        "{env.LIDARR_URL}/api/v1/artist/lookup?term={arg.query}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "lidarr_add",
        "Add an artist to Lidarr. Use lidarr_search first to get foreignArtistId and artistName.",
        _schema(
            {
                "foreignArtistId": _s("MusicBrainz artist id from lidarr_search"),
                "artistName": _bs(),
                "qualityProfileId": _bn(),
                "metadataProfileId": _bn(),
                "rootFolderPath": _bs(),
                "monitored": _bb(),
            },
            ["foreignArtistId", "artistName", "qualityProfileId", "metadataProfileId", "rootFolderPath"],
        ),
        "POST",
        "{env.LIDARR_URL}/api/v1/artist",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "lidarr_delete",
        "Delete an artist from Lidarr by id. Set deleteFiles=true to also remove files on disk. Get the id from lidarr_library.",
        _schema(
            {
                "id": _n("Lidarr artist id (from lidarr_library)"),
                "deleteFiles": _b("Also remove files on disk (default false)"),
            },
            ["id"],
        ),
        "DELETE",
        "{env.LIDARR_URL}/api/v1/artist/{arg.id}?deleteFiles={arg.deleteFiles|false}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "lidarr_queue",
        "Get the Lidarr download queue.",
        _schema({}),
        "GET",
        "{env.LIDARR_URL}/api/v1/queue",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "lidarr_wanted",
        "Get missing/wanted albums from Lidarr.",
        _schema({}),
        "GET",
        "{env.LIDARR_URL}/api/v1/wanted/missing?pageSize=50",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "lidarr_rootfolder",
        "List Lidarr root folders (id, path, accessible, freeSpace). Call before lidarr_add to get a valid rootFolderPath (use the path value).",
        _schema({}),
        "GET",
        "{env.LIDARR_URL}/api/v1/rootfolder",
        body=None,
        select=["id", "path", "accessible", "freeSpace"],
        limit=None,
    ),
    Tool(
        "lidarr_qualityprofile",
        "List Lidarr quality profiles (id, name). Call before lidarr_add to get a valid qualityProfileId (use the id).",
        _schema({}),
        "GET",
        "{env.LIDARR_URL}/api/v1/qualityprofile",
        body=None,
        select=["id", "name"],
        limit=None,
    ),
    Tool(
        "lidarr_metadataprofile",
        "List Lidarr metadata profiles (id, name). Call before lidarr_add to get a valid metadataProfileId (use the id).",
        _schema({}),
        "GET",
        "{env.LIDARR_URL}/api/v1/metadataprofile",
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
            toolset="lidarr",
            schema=_fn_schema(tool.name, tool.description, tool.schema),
            handler=_make_handler(tool),
            description=tool.description,
        )
    print(
        f"[lidarr] registered {len(TOOLS)} tools (v{PLUGIN_VERSION}) -> "
        f"{_env('LIDARR_URL') or '(LIDARR_URL unset)'}",
        flush=True,
    )
