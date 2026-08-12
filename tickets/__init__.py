"""tickets — Hermes plugin for tickets-srv.

Auth is `X-Api-Key`, and **the key IS the caller's name**. There is no identity
server behind tickets-srv any more and nothing to look the key up in: send
`scout-agent` and you are scout-agent, for as long as you keep sending it.

That makes the key an identity rather than a secret, and the ownership rules it
unlocks — only the reporter may edit or delete what they filed — a convention
between well-behaved agents, not a boundary. Anything on tfk-net that knows the
string can claim the name. See tickets-srv src/auth.ts for why that trade was
made: a name that had to be registered somewhere else went stale, and two
thirds of the queue ended up displaying a bare user id instead of a reporter.

The key still comes from the profile's env, where the model cannot see it or
set it, so an agent cannot act as someone else *by asking*.

Env (profile .env):
  TICKETS_URL      e.g. http://tickets:4200
  TICKETS_API_KEY  this profile owner's name, e.g. `lili` or `scout-agent`

Tool descriptions are kept BYTE-IDENTICAL to tickets-srv src/mcp.ts. Two
languages means two copies; if you edit one, edit the other.
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

PLUGIN_VERSION = "2026-08-12.10"

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
    key = _env("TICKETS_API_KEY")
    if not key:
        # Without this the request goes out with an empty X-Api-Key, tickets-srv
        # answers a bare 401, and the agent reports "tickets is unauthorized" —
        # which reads like a broken backend rather than one missing line in the
        # profile .env. Cost alek a testing session on 2026-08-05. Name the
        # variable, never the value.
        return json.dumps(
            {
                "ok": False,
                "message": "TICKETS_API_KEY is not set for this profile — add it "
                           "to the profile .env (it is simply the profile "
                           "owner's name, e.g. `lili` or `scout-agent`)",
            }
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
        "File a ticket for the admin's attention, under your own name — your API key IS your name, so whatever you file is attributed to you. The admin gets a Telegram alert and reviews via the tickets UI. Use this when you hit a bug, need a tool capability you don't have, or want a human decision before proceeding.",
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
        "List open tickets that belong to you (the calling agent) — by default both the ones you filed and the ones assigned to you. scope='reported' returns only tickets YOU filed, which is how you follow up on your own bug reports. scope='assigned' returns only work an admin has routed your way (the latest assign event names you). scope='all' is the default and returns both. Filing a ticket does NOT assign it to you.",
        _schema(
            {
                "scope": _s("One of: all (default), reported, assigned"),
            },
        ),
        "GET",
        # The API defaults to `assigned`, which is what /mine has always meant
        # and what the gate still relies on. The PLUGIN defaults to `all`: an
        # agent asking "what are my tickets" almost always means the ones it
        # filed, and a bot that filed ten of them was told it owned none.
        "{env.TICKETS_URL}/api/tickets/mine?scope={arg.scope|all}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "tickets_get",
        "Read a ticket by id, including its event timeline (comments, assignments, close/reopen). Reads are open to any caller.",
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
        "Edit an existing ticket's subject, body, or category. The reporter and the current assignee may update. Use this when a ticket needs new findings added or its subject sharpened — preserves the event timeline instead of closing and re-filing.",
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
        "Add a comment to a ticket. The reporter and the current assignee may comment. Use this to provide updates, ask questions, or record resolution notes.",
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
        "List tickets. Filter by status. Returns each ticket's reporter and latest assignee for context. Reads are open to any caller.",
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
        'Assign a ticket to an agent (admin only — routing work is the admin\'s job). Pass `agent` as the agent\'s name, e.g. "claude" or "scout-agent". There is no registry, so any well-formed name is accepted. The agent will see this ticket in tickets_mine. Optional `note` is recorded in the timeline.',
        _schema(
            {
                "id": _bn(),
                "agent": _s('Agent name, e.g. "claude" or "scout-agent"'),
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
        "Close an open ticket. The reporter and the current assignee may close — so you can retract a ticket you filed by mistake, and you can close work that was assigned to you once it is done. Records an optional note in the timeline.",
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
        "Reopen a closed ticket. The reporter and the current assignee may reopen. Records an optional note in the timeline.",
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
    Tool(
        "tickets_delete",
        "Permanently delete a ticket you filed, along with its timeline. Only the reporter may delete, and only while nobody else has touched it: once the ticket has been assigned, or someone else has replied, it can only be closed. Use this to retract a duplicate or a test artifact — prefer tickets_close for anything real, which keeps the history.",
        _schema(
            {
                "id": _bn(),
            },
            ["id"],
        ),
        "POST",
        "{env.TICKETS_URL}/api/tickets/delete",
        body=None,
        select=None,
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
            toolset="tickets",
            schema=_fn_schema(tool.name, tool.description, tool.schema),
            handler=_make_handler(tool),
            description=tool.description,
        )
    print(
        f"[tickets] registered {len(TOOLS)} tools (v{PLUGIN_VERSION}) -> "
        f"{_env('TICKETS_URL') or '(TICKETS_URL unset)'} "
        # Presence only — the key is an identity and never goes in a log.
        f"{'(key set)' if _env('TICKETS_API_KEY') else '(TICKETS_API_KEY UNSET)'}",
        flush=True,
    )
