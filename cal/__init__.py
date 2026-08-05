"""cal — Hermes plugin for cal-srv (calendar, tasks, projects).

Auth is `X-Api-Key`, looked up in the shared identity table — the key IS the
caller. Username and apiKey are the same value by convention.

**This plugin could not exist until 2026-08-05.** cal-srv trusted a bare
`X-User-Id` header and said so in its own source: "No app auth beyond that
(gate-fronted, internal network)." cal sits on tfk-net with every agent
container, so a direct plugin would have let any agent read or edit anyone's
calendar. cal-srv cd38b84 added key authentication; this plugin uses it and
sends no user id.

The key comes from the profile's env — the model can neither see nor set it.
Every tool here acts on ONE person's data, which is exactly why the gate marked
this group `userScoped`; pinning the key per profile achieves the same thing
and cannot be overridden by anything the model says.

Timestamps are ISO 8601 and MUST carry a timezone (2026-07-25T09:00:00Z or
+03:00) — a naive time is rejected rather than guessed at. All-day events may
use a bare date.

Deleting a whole calendar / list / project is deliberately NOT exposed: it
cascades to every event or task inside. That stays a human action in the UI.

Env (profile .env):
  CAL_URL      e.g. http://cal:3020
  CAL_API_KEY  this profile owner's identity key (= their username)

Tool descriptions port VERBATIM from srv-mcp-yaml/cal.yaml.
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

PLUGIN_VERSION = "2026-08-05.18"

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
    if not _env("CAL_URL"):
        return json.dumps(
            {"ok": False, "message": "CAL_URL is not set for this profile"}
        )
    url = _render(tool.url, args, quote=True)
    headers = {"X-Api-Key": _env("CAL_API_KEY"), "Accept": "application/json"}

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
            {"ok": False, "message": f"cal HTTP {e.code}: {e.read().decode()[:300]}"}
        )
    except Exception as e:  # noqa: BLE001 — surface it, never crash the turn
        return json.dumps(
            {"ok": False, "message": f"cal unreachable at {url} — check CAL_URL: {e}"}
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
        "cal_agenda",
        "The user's upcoming agenda — events (recurrence expanded) + dated tasks — over the next N days, time-ordered. Start here for \"what's on\".",
        _schema(
            {
                "days": _n("How many days ahead, 1-90 (default 7). Out of range is an error, not a clamp."),
            },
        ),
        "GET",
        "{env.CAL_URL|http://cal:3020}/api/v2/agenda?days={arg.days|7}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "cal_calendars",
        "List the user's calendars (owned + shared), with id, name, colour.",
        _schema({}),
        "GET",
        "{env.CAL_URL|http://cal:3020}/api/v2/calendars",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "cal_containers",
        "List the user's task containers (owned + shared) — id, name, kind (board=Project, checklist=List).",
        _schema({}),
        "GET",
        "{env.CAL_URL|http://cal:3020}/api/v2/containers",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "cal_events",
        "Events in an explicit time window (recurrence expanded). Unlike cal_agenda this can look into the past. Optionally limited to one calendar.",
        _schema(
            {
                "from": _s("Window start, ISO 8601 with timezone"),
                "to": _s("Window end, ISO 8601 with timezone (max 366 days after from)"),
                "calendarId": _n("Limit to one calendar"),
            },
            ["from", "to"],
        ),
        "GET",
        "{env.CAL_URL|http://cal:3020}/api/v2/events?from={arg.from}&to={arg.to}&calendarId={arg.calendarId|}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "cal_tasks",
        "Every task in one list or project, including undated and completed ones — the only way to see tasks that cal_agenda omits.",
        _schema(
            {
                "containerId": _n("Container id (from cal_containers)"),
                "status": _s("Filter to one status (list: open|done; project: todo|doing|done|blocked)"),
            },
            ["containerId"],
        ),
        "GET",
        "{env.CAL_URL|http://cal:3020}/api/v2/tasks?containerId={arg.containerId}&status={arg.status|}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "cal_task_get",
        "One task in full — description, due date, priority, status, plus its whole thread of comments and the record of how it moved through the board. Read this before commenting on or updating a task.",
        _schema(
            {
                "id": _n("Task id (from cal_tasks"),
            },
            ["id"],
        ),
        "GET",
        "{env.CAL_URL|http://cal:3020}/api/v2/task?id={arg.id}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "cal_search",
        "Find events and tasks by a fragment of their title or notes, across everything the user can see. Use this to resolve a vague reference to an id.",
        _schema(
            {
                "q": _s("Search text, min 2 characters"),
                "limit": _n("Max results per type (default 25, max 100)"),
            },
            ["q"],
        ),
        "GET",
        "{env.CAL_URL|http://cal:3020}/api/v2/search?q={arg.q}&limit={arg.limit|25}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "cal_calendar_add",
        "Create a new calendar for the user (e.g. \"Work\", \"Training\"). Returns the new calendar with its id.",
        _schema(
            {
                "name": _bs(),
                "colour": _s("Hex colour like #3b82f6; omit to auto-pick from the palette"),
            },
            ["name"],
        ),
        "POST",
        "{env.CAL_URL|http://cal:3020}/api/v2/calendar/add",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "cal_container_add",
        "Create a new list (checklist, e.g. shopping) or project (kanban board). Returns the new container with its id.",
        _schema(
            {
                "name": _bs(),
                "kind": _s("checklist (a simple List) or board (a kanban Project)"),
                "colour": _s("Hex colour; omit to auto-pick"),
            },
            ["name", "kind"],
        ),
        "POST",
        "{env.CAL_URL|http://cal:3020}/api/v2/container/add",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "cal_event_add",
        "Add an event to one of the user's calendars. Times are ISO 8601 with a timezone. Optional repeat (every N unit).",
        _schema(
            {
                "calendarId": _n("Target calendar id (from cal_calendars)"),
                "title": _s("Event title — cannot be empty"),
                "start": _s("Start, ISO 8601 with timezone (e.g. 2026-07-25T09:00:00Z). A bare date is allowed when allDay is true."),
                "end": _s("End, ISO 8601. Must not be before start. Omit for a point event."),
                "allDay": _b("All-day event (default false)"),
                "location": _bs(),
                "notes": _bs(),
                "repeatEvery": _n("Repeat interval N (needs repeatUnit); omit for none"),
                "repeatUnit": _s("day | week | month | year"),
            },
            ["calendarId", "title", "start"],
        ),
        "POST",
        "{env.CAL_URL|http://cal:3020}/api/v2/event/add",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "cal_event_update",
        "Update an event. Only the fields you pass change. Pass end as null to clear it.",
        _schema(
            {
                "id": _bn(),
                "title": _bs(),
                "start": _s("ISO 8601 with timezone"),
                "end": _s("ISO 8601 with timezone"),
                "allDay": _bb(),
                "location": _bs(),
                "notes": _bs(),
                "repeatEvery": _n("Repeat interval N; 0 with repeatUnit none stops the repeat"),
                "repeatUnit": _s("none | day | week | month | year"),
            },
            ["id"],
        ),
        "POST",
        "{env.CAL_URL|http://cal:3020}/api/v2/event/update",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "cal_event_delete",
        "Delete one event (id) or many at once (ids). Prefer ids for cleanups — one batched call instead of a burst of requests. Unknown single id returns 404.",
        _schema(
            {
                "id": _n("A single event id"),
                "ids": _s("Several event ids (max 200). Reports which were deleted and which were already gone."),
            },
        ),
        "POST",
        "{env.CAL_URL|http://cal:3020}/api/v2/event/delete",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "cal_task_add",
        "Add a task to a list or project. Status defaults to open (list) or todo (project). A dated task also shows on the calendar.",
        _schema(
            {
                "containerId": _n("Target container id (from cal_containers)"),
                "title": _s("Cannot be empty"),
                "dueAt": _s("Due date/time, ISO 8601 with timezone"),
                "status": _s("Override the default (list: open|done; project: todo|doing|done|blocked)"),
                "notes": _bs(),
                "priority": _n("0 none, 1 low, 2 medium, 3 high"),
            },
            ["containerId", "title"],
        ),
        "POST",
        "{env.CAL_URL|http://cal:3020}/api/v2/task/add",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "cal_task_update",
        "Update a task's title, notes, due date, priority or status. Only the fields you pass change. Pass dueAt as null to un-date it.",
        _schema(
            {
                "id": _bn(),
                "title": _bs(),
                "status": _s("list: open|done; project: todo|doing|done|blocked"),
                "dueAt": _s("ISO 8601 with timezone, or null to clear"),
                "notes": _bs(),
                "priority": _n("0 none, 1 low, 2 medium, 3 high"),
            },
            ["id"],
        ),
        "POST",
        "{env.CAL_URL|http://cal:3020}/api/v2/task/update",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "cal_task_comment",
        "Add a comment to a task. Lands in the same thread the user reads in the app, attributed to them. Use it to leave progress notes, findings or questions on a card as work moves along.",
        _schema(
            {
                "taskId": _bn(),
                "body": _s("The comment text — cannot be empty"),
            },
            ["taskId", "body"],
        ),
        "POST",
        "{env.CAL_URL|http://cal:3020}/api/v2/task/comment",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "cal_task_complete",
        "Mark a task done.",
        _schema(
            {
                "id": _bn(),
            },
            ["id"],
        ),
        "POST",
        "{env.CAL_URL|http://cal:3020}/api/v2/task/complete",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "cal_task_move",
        "Move a task to a different status column. Rejects a status the container doesn't have.",
        _schema(
            {
                "id": _bn(),
                "status": _s("project: todo | doing | done | blocked; list: open | done"),
            },
            ["id", "status"],
        ),
        "POST",
        "{env.CAL_URL|http://cal:3020}/api/v2/task/move",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "cal_task_delete",
        "Delete one task (id) or many at once (ids) — permanent, unlike completing. Prefer ids for cleanups. Unknown single id returns 404.",
        _schema(
            {
                "id": _n("A single task id"),
                "ids": _s("Several task ids (max 200). Reports which were deleted and which were already gone."),
            },
        ),
        "POST",
        "{env.CAL_URL|http://cal:3020}/api/v2/task/delete",
        body=None,
        select=None,
        limit=None,
    ),
]


def register(ctx) -> None:
    for tool in TOOLS:
        ctx.register_tool(
            name=tool.name,
            toolset="cal",
            schema=tool.schema,
            handler=_make_handler(tool),
            description=tool.description,
        )
    print(
        f"[cal] registered {len(TOOLS)} tools (v{PLUGIN_VERSION}) -> "
        f"{_env('CAL_URL') or '(CAL_URL unset)'}",
        flush=True,
    )
