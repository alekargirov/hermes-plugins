"""nzb — Hermes plugin for NZBGet.

A DIRECT plugin speaking NZBGet's JSON-RPC. Two things make it unlike the rest:

  1. Auth is in the URL PATH, not a header:
     {NZB_URL}{NZB_USER}:{NZB_PASSWORD}/jsonrpc. NZB_URL needs its trailing
     slash — without it the path collapses and every call 404s.
  2. Because the PASSWORD IS IN THE URL, no error message may contain the URL.
     `_redact` replaces the credential segment before anything is returned to
     the model. This is the one plugin where naming the URL in an error would
     leak a secret into the transcript, so it names the env var instead.

Every call is POST with a JSON-RPC body; the method name is baked into each
tool rather than exposed, so the agent cannot invoke arbitrary RPCs.

Single-tenant.

Env (profile .env):
  NZB_URL       base URL WITH a trailing slash, e.g. http://nzb:6789/
  NZB_USER      NZBGet control username
  NZB_PASSWORD  NZBGet control password

Tool descriptions and bodies port VERBATIM from srv-mcp-yaml/nzb.yaml.
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

PLUGIN_VERSION = "2026-08-05.7"

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
    """The PASSWORD is in the URL path ({NZB_URL}{user}:{pass}/jsonrpc), so the
    URL can never appear in anything returned to the model."""
    return re.sub(r"(https?://[^/]+/)[^/]*:[^/]*/", r"\1***:***/", u)


def _call(tool: Tool, args: dict) -> str:
    if not _env("NZB_URL"):
        return json.dumps(
            {"ok": False, "message": "NZB_URL is not set for this profile"}
        )
    url = _render(tool.url, args, quote=True)
    headers = {"Content-Type": "application/json"}

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
            {"ok": False, "message": f"nzb HTTP {e.code}: {e.read().decode()[:300]}"}
        )
    except Exception as e:  # noqa: BLE001 — surface it, never crash the turn
        return json.dumps(
            {"ok": False, "message": f"nzb unreachable at {_redact(url)} — check NZB_URL: {e}"}
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
        "nzb_status",
        "NZBGet server status — download rate, remaining size, paused state, free disk space.",
        _schema({}),
        "POST",
        "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        body="{\"method\":\"status\"}",
        select=None,
        limit=None,
    ),
    Tool(
        "nzb_queue",
        "List the current NZBGet download queue (active and queued items with NZBID, name, size, progress). Use NZBID with nzb_delete.",
        _schema({}),
        "POST",
        "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        body="{\"method\":\"listgroups\"}",
        select=None,
        limit=None,
    ),
    Tool(
        "nzb_history",
        "NZBGet download history (completed/failed items). Returns the full history — can be long.",
        _schema({}),
        "POST",
        "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        body="{\"method\":\"history\",\"params\":[false]}",
        select=None,
        limit=None,
    ),
    Tool(
        "nzb_add",
        "Add a download to NZBGet by NZB file URL. NZBGet fetches the URL itself. Optionally set a category (e.g. movies, tv, music) and a name.",
        _schema(
            {
                "url": _s("Direct URL to the .nzb file"),
                "category": _s("NZBGet category (optional, e.g. movies, tv, music)"),
                "name": _s("Filename to store as (optional — derived from the URL if empty)"),
            },
            ["url"],
        ),
        "POST",
        "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        body="{\"method\":\"append\",\"params\":[\"{arg.name|}\",\"{arg.url}\",\"{arg.category|}\",0,false,false,\"\",0,\"SCORE\"]}",
        select=None,
        limit=None,
    ),
    Tool(
        "nzb_delete",
        "Delete a queue item from NZBGet by NZBID (from nzb_queue). Removes the download, keeps nothing.",
        _schema(
            {
                "id": _n("NZBID from nzb_queue"),
            },
            ["id"],
        ),
        "POST",
        "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        body="{\"method\":\"editqueue\",\"params\":[\"GroupDelete\",0,\"\",[{arg.id}]]}",
        select=None,
        limit=None,
    ),
    Tool(
        "nzb_pause",
        "Pause all NZBGet downloads.",
        _schema({}),
        "POST",
        "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        body="{\"method\":\"pausedownload\"}",
        select=None,
        limit=None,
    ),
    Tool(
        "nzb_resume",
        "Resume all NZBGet downloads.",
        _schema({}),
        "POST",
        "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        body="{\"method\":\"resumedownload\"}",
        select=None,
        limit=None,
    ),
]


def register(ctx) -> None:
    for tool in TOOLS:
        ctx.register_tool(
            name=tool.name,
            toolset="nzb",
            schema=tool.schema,
            handler=_make_handler(tool),
            description=tool.description,
        )
    print(
        f"[nzb] registered {len(TOOLS)} tools (v{PLUGIN_VERSION}) -> "
        f"{_env('NZB_URL') or '(NZB_URL unset)'}",
        flush=True,
    )
