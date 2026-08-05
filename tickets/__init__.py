"""tickets — Hermes plugin for tickets-srv.

Auth is `X-Api-Key`, and the key IS the identity: it is looked up in the shared
identity table and decides who the caller is. Username and apiKey are the same
value by convention, so the key is simply the profile owner's username.

**This plugin could not exist until 2026-08-05.** tickets-srv previously trusted
a bare `X-User-Id` header, believed exactly as sent — safe only because the MCP
gate was the sole caller and set it from a key it had already validated. Since
tickets sits on tfk-net with every agent container, a plugin talking to it
directly would have handed "act as anyone, admin included" to every agent.
tickets-srv 96df76c added key authentication; this plugin uses it and never
sends a user id at all.

The key comes from the profile's env. The model cannot see it and cannot set
it, so an agent cannot act as someone else by asking.

Env (profile .env):
  TICKETS_URL      e.g. http://tickets:4200
  TICKETS_API_KEY  this profile owner's identity key (= their username)

Tool descriptions port VERBATIM from srv-mcp-yaml/tickets.yaml.
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
    if not _env("TICKETS_URL"):
        return json.dumps(
            {"ok": False, "message": "TICKETS_URL is not set for this profile"}
        )
    url = _render(tool.url, args, quote=True)
    headers = {"X-Api-Key": _env("TICKETS_API_KEY"), "Accept": "application/json"}

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
            {"ok": False, "message": f"tickets HTTP {e.code}: {e.read().decode()[:300]}"}
        )
    except Exception as e:  # noqa: BLE001 — surface it, never crash the turn
        return json.dumps(
            {"ok": False, "message": f"tickets unreachable at {url} — check TICKETS_URL: {e}"}
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
        "tickets_create",
        "File a ticket for the admin's attention. The admin gets a Telegram alert and reviews via the pica UI. Use this when you hit a bug, need a tool capability you don't have, or want a human decision before proceeding.",
        _schema(
            {
                "subject": _s("Short, specific subject line"),
                "body": _s("Detailed description (markdown OK; include what you tried, what failed, what you'd like)"),
                "category": _s("One of: tool, bug, other (default 'other')"),
            },
            ["subject"],
        ),
        "POST",
        "{env.TICKETS_URL}/api/tickets/create",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "tickets_mine",
        "List tickets currently assigned to you (the calling agent). Use this to pick up work the admin has routed your way. Returns only open tickets where the latest assign event names your user id.",
        _schema({}),
        "GET",
        "{env.TICKETS_URL}/api/tickets/mine",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "tickets_get",
        "Read a ticket by id, including its event timeline (comments, assignments, close/reopen). Accessible to admin, the reporter, or the current assignee.",
        _schema(
            {
                "id": _bn(),
            },
            ["id"],
        ),
        "GET",
        "{env.TICKETS_URL}/api/tickets/get?id={arg.id}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "tickets_update",
        "Edit an existing ticket's subject, body, or category. Admin, the reporter, and the current assignee may update. Use this when a ticket needs new findings added or its subject sharpened — preserves the event timeline instead of closing and re-filing.",
        _schema(
            {
                "id": _bn(),
                "subject": _s("New subject line"),
                "body": _s("New body (markdown OK)"),
                "category": _s("One of: tool, bug, other"),
            },
            ["id"],
        ),
        "POST",
        "{env.TICKETS_URL}/api/tickets/update",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "tickets_comment",
        "Add a comment to a ticket. The admin, the reporter, and the current assignee may comment. Use this to provide updates, ask questions, or record resolution notes.",
        _schema(
            {
                "id": _bn(),
                "body": _s("Comment body"),
            },
            ["id", "body"],
        ),
        "POST",
        "{env.TICKETS_URL}/api/tickets/comment",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "tickets_list",
        "List all tickets (admin only). Filter by status. Returns each ticket's latest assignee + reporter username for context.",
        _schema(
            {
                "status": _s("One of: open (default), closed, all"),
            },
        ),
        "GET",
        "{env.TICKETS_URL}/api/tickets/list?status={arg.status}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "tickets_assign",
        "Assign a ticket to an agent (admin only). Pass either `agent` (username) or `assigneeId` (numeric user id). The agent will see this ticket in tickets_mine. Optional `note` is recorded in the timeline.",
        _schema(
            {
                "id": _bn(),
                "agent": _s("Agent username (preferred)"),
                "assigneeId": _n("Numeric user id (alternative)"),
                "note": _bs(),
            },
            ["id"],
        ),
        "POST",
        "{env.TICKETS_URL}/api/tickets/assign",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "tickets_close",
        "Close an open ticket (admin only). Records optional note in the timeline.",
        _schema(
            {
                "id": _bn(),
                "note": _bs(),
            },
            ["id"],
        ),
        "POST",
        "{env.TICKETS_URL}/api/tickets/close",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "tickets_reopen",
        "Reopen a closed ticket (admin only).",
        _schema(
            {
                "id": _bn(),
                "note": _bs(),
            },
            ["id"],
        ),
        "POST",
        "{env.TICKETS_URL}/api/tickets/reopen",
        body=None,
        select=None,
        limit=None,
    ),
]


def register(ctx) -> None:
    for tool in TOOLS:
        ctx.register_tool(
            name=tool.name,
            toolset="tickets",
            schema=tool.schema,
            handler=_make_handler(tool),
            description=tool.description,
        )
    print(
        f"[tickets] registered {len(TOOLS)} tools (v{PLUGIN_VERSION}) -> "
        f"{_env('TICKETS_URL') or '(TICKETS_URL unset)'}",
        flush=True,
    )
