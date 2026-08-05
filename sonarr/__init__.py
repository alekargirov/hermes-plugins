"""sonarr — Hermes plugin for Sonarr.

A DIRECT plugin: Sonarr is third-party software on the LAN, so there is no
endpoint of ours to forward to and this file owns the HTTP call. Auth is
Sonarr's own X-Api-Key. Single-tenant — one shared library, so there is no
user id and nothing to scope.

Env (profile .env):
  SONARR_URL      e.g. http://sonarr:8989
  SONARR_API_KEY  Sonarr's API key (Settings -> General)

Tool descriptions and URL templates port VERBATIM from srv-mcp-yaml/sonarr.yaml.
`_render` and `_shape` are copied from _template/url_template.py, which is the
readable spec with the tests — a rule change starts there.

sonarr_calendar uses the {now} / {now+14d} date macros: with no arguments it
asks for the next fortnight. That default sits INSIDE a template default, which
is exactly the case a single-pass renderer gets wrong — see the engine's tests.
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
    if not _env("SONARR_URL"):
        return json.dumps(
            {"ok": False, "message": "SONARR_URL is not set for this profile"}
        )
    key = _env("SONARR_API_KEY")
    if not key:
        # Without this the request goes out with an empty X-Api-Key and the
        # service answers a bare 401, which the agent reports as a broken
        # backend rather than one missing line in the profile .env. Name the
        # variable, never the value.
        return json.dumps(
            {"ok": False, "message": "SONARR_API_KEY is not set for this profile"}
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
            {"ok": False, "message": f"sonarr HTTP {e.code}: {e.read().decode()[:300]}"}
        )
    except Exception as e:  # noqa: BLE001 — surface it, never crash the turn
        return json.dumps(
            {"ok": False, "message": f"sonarr unreachable at {url} — check SONARR_URL: {e}"}
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
        "sonarr_library",
        "List TV shows in the Sonarr library (id, title, year, tvdbId, status, monitored). Trimmed to essential fields so large libraries return complete and untruncated.",
        _schema({}),
        "GET",
        "{env.SONARR_URL}/api/v3/series",
        body=None,
        select=["id", "title", "year", "tvdbId", "status", "monitored"],
        limit=None,
    ),
    Tool(
        "sonarr_search",
        "Search for a TV show in Sonarr.",
        _schema(
            {
                "query": _s("TV show title to search for"),
            },
            ["query"],
        ),
        "GET",
        "{env.SONARR_URL}/api/v3/series/lookup?term={arg.query}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "sonarr_add",
        "Add a TV show to Sonarr. RECIPE (v4 rejects hand-built minimal payloads with an unhelpful bare 400): take the ENTIRE series object returned by sonarr_search for your show (it includes seasons, images, titleSlug, languageProfileId — all required by model binding), then override just: qualityProfileId (from sonarr_qualityprofile), rootFolderPath (from sonarr_rootfolder), monitored:true, and addOptions:{monitor:all, searchForMissingEpisodes:true}. Do NOT construct the object from scratch — that is the cause of ticket #137's 400s. addOptions is what creates/searches episodes; if forgotten, fix after with sonarr_command (RefreshSeries then SeriesSearch).",
        _schema(
            {
                "payload": _s("Sonarr series object: tvdbId, title, titleSlug, qualityProfileId, rootFolderPath, monitored, seasonFolder, AND addOptions:{\"monitor\":\"all\",\"searchForMissingEpisodes\":true} — the addOptions block is what populates episode records and triggers the initial search."),
            },
            ["payload"],
        ),
        "POST",
        "{env.SONARR_URL}/api/v3/series",
        body="{arg.payload}",
        select=None,
        limit=None,
    ),
    Tool(
        "sonarr_command",
        "Run a Sonarr command. If a freshly added series shows no episodes in sonarr_wanted/sonarr_library, call name=RefreshSeries with its seriesId to create the episode records, then name=SeriesSearch with the seriesId to search. (Also valid: RescanSeries, MissingEpisodeSearch.) This is the programmatic equivalent of the manual unmonitor/monitor toggle.",
        _schema(
            {
                "payload": _s("Command object, e.g. {\"name\":\"RefreshSeries\",\"seriesId\":77} then {\"name\":\"SeriesSearch\",\"seriesId\":77}"),
            },
            ["payload"],
        ),
        "POST",
        "{env.SONARR_URL}/api/v3/command",
        body="{arg.payload}",
        select=None,
        limit=None,
    ),
    Tool(
        "sonarr_calendar",
        "Get upcoming episodes from Sonarr. Defaults to today through +14 days.",
        _schema(
            {
                "start": _s("Start date (ISO 8601, e.g. 2026-05-16). Omit for today."),
                "end": _s("End date (ISO 8601, e.g. 2026-05-23). Omit for today+14d."),
            },
        ),
        "GET",
        "{env.SONARR_URL}/api/v3/calendar?start={arg.start|{now}}&end={arg.end|{now+14d}}&includeSeries=true",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "sonarr_queue",
        "Get the Sonarr download queue.",
        _schema({}),
        "GET",
        "{env.SONARR_URL}/api/v3/queue?includeSeries=true&includeEpisode=true",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "sonarr_wanted",
        "Get missing monitored episodes from Sonarr. Returns 10 per page — increment page for more. totalRecords in response gives the total count.",
        _schema(
            {
                "page": _n("Page number, starting at 1 (default 1)"),
            },
        ),
        "GET",
        "{env.SONARR_URL}/api/v3/wanted/missing?pageSize=10&includeSeries=true&page={arg.page|1}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "sonarr_rootfolder",
        "List Sonarr root folders (id, path, accessible, freeSpace). Call before sonarr_add to get a valid rootFolderPath (use the path value).",
        _schema({}),
        "GET",
        "{env.SONARR_URL}/api/v3/rootfolder",
        body=None,
        select=["id", "path", "accessible", "freeSpace"],
        limit=None,
    ),
    Tool(
        "sonarr_qualityprofile",
        "List Sonarr quality profiles (id, name). Call before sonarr_add to get a valid qualityProfileId (use the id).",
        _schema({}),
        "GET",
        "{env.SONARR_URL}/api/v3/qualityprofile",
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
            toolset="sonarr",
            schema=_fn_schema(tool.name, tool.description, tool.schema),
            handler=_make_handler(tool),
            description=tool.description,
        )
    print(
        f"[sonarr] registered {len(TOOLS)} tools (v{PLUGIN_VERSION}) -> "
        f"{_env('SONARR_URL') or '(SONARR_URL unset)'}",
        flush=True,
    )
