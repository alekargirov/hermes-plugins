"""tickets — Internal ticket system (tickets-srv).

Nine tools. Every call carries the calling agent's USER_ID in X-User-Id —
the server gates by it. tickets_create opens a ticket that the admin gets a
Telegram alert for; tickets_mine lists tickets currently assigned to the
caller; tickets_assign / tickets_close / tickets_reopen are admin-only
(the server enforces).

Env (profile .env): TICKETS_URL, USER_ID.
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta


def _env(name: str) -> str:
    try:
        from agent.secret_scope import get_secret
        val = get_secret(name, "")
    except Exception:
        val = os.environ.get(name, "")
    return val or ""


def _now(spec: str) -> str:
    if spec == "now":
        return datetime.utcnow().strftime("%Y-%m-%d")
    m = re.fullmatch(r"now([+-])(\d+)([dhms])", spec)
    if not m:
        return spec
    sign, n, unit = m.group(1), int(m.group(2)), m.group(3)
    kw = {"d": "days", "h": "hours", "m": "minutes", "s": "seconds"}[unit]
    return (datetime.utcnow() + timedelta(**{kw: n if sign == "+" else -n})).strftime("%Y-%m-%d")


def _find_close(s, start):
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _is_placeholder(content):
    if re.fullmatch(r"now(?:[+-]\d+[dhms])?", content):
        return True
    head, _, _ = content.partition("|")
    kind, _, name = head.partition(".")
    return kind in ("env", "arg") and bool(name)


def _resolve_content(content, args):
    if re.fullmatch(r"now(?:[+-]\d+[dhms])?", content):
        return _now(content)
    head, _, default = content.partition("|")
    kind, _, name = head.partition(".")
    if kind == "env":
        v = _env(name)
        if v:
            return v
    elif kind == "arg":
        if name in args and args[name] is not None and args[name] != "":
            v = args[name]
            if isinstance(v, (dict, list)):
                return json.dumps(v, separators=(",", ":"))
            return str(v)
    if default is not None:
        return _resolve(default, args)
    return ""


def _resolve(template, args):
    out = []
    i = 0
    n = len(template)
    while i < n:
        ch = template[i]
        if ch != "{":
            out.append(ch)
            i += 1
            continue
        close = _find_close(template, i)
        if close == -1 or not _is_placeholder(template[i + 1:close]):
            out.append("{")
            i += 1
            continue
        out.append(_resolve_content(template[i + 1:close], args))
        i = close + 1
    return "".join(out)


def _request(method, url, headers, body, select):
    headers = dict(headers)
    if body:
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
        if not any(k.lower() == "content-type" for k in headers):
            headers["Content-Type"] = "application/json"
    else:
        body_bytes = None
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode()[:300]
        except Exception:
            err_body = ""
        return json.dumps({"ok": False, "message": f"{method} {url} HTTP {e.code}: {err_body}"})
    except Exception as e:
        return json.dumps({"ok": False, "message": f"{method} {url} unreachable: {e}"})
    try:
        payload = json.loads(raw)
    except ValueError:
        return raw
    if select:
        if isinstance(payload, list):
            payload = [
                {k: item[k] for k in select if isinstance(item, dict) and k in item}
                for item in payload
            ]
        elif isinstance(payload, dict):
            payload = {k: payload[k] for k in select if k in payload}
    return json.dumps(payload)


def _make_handler(spec):
    method = spec["method"]
    url_t = spec["url"]
    headers_t = spec.get("headers", {})
    body_t = spec.get("body")
    select = spec.get("select")

    def handler(args, **kwargs):
        url = _resolve(url_t, args)
        headers = {k: _resolve(v, args) for k, v in headers_t.items()}
        body = _resolve(body_t, args) if body_t else None
        if not body and method in ("POST", "PUT", "PATCH") and args:
            body = json.dumps(args, separators=(",", ":"))
        return _request(method, url, headers, body, select)

    return handler


def _s(d):
    return {"type": "string", "description": d}


def _n(d):
    return {"type": "number", "description": d}


def _b(d):
    return {"type": "boolean", "description": d}


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


_HDR = {"X-User-Id": "{env.USER_ID}"}


TOOLS = [
    (
        "tickets_create",
        "File a ticket for the admin's attention. The admin gets a Telegram alert and reviews via the pica UI. Use this when you hit a bug, need a tool capability you don't have, or want a human decision before proceeding.",
        _schema(
            {
                "subject": _s("Short, specific subject line"),
                "body": _s(
                    "Detailed description (markdown OK; include what you tried, what failed, what you'd like)"
                ),
                "category": _s("One of: tool, bug, other (default 'other')"),
            },
            ["subject"],
        ),
        _make_handler({
            "method": "POST",
            "url": "{env.TICKETS_URL}/api/tickets/create",
            "headers": _HDR,
        }),
    ),
    (
        "tickets_mine",
        "List tickets currently assigned to you (the calling agent). Use this to pick up work the admin has routed your way. Returns only open tickets where the latest assign event names your user id.",
        _schema({}),
        _make_handler({
            "method": "GET",
            "url": "{env.TICKETS_URL}/api/tickets/mine",
            "headers": _HDR,
        }),
    ),
    (
        "tickets_get",
        "Read a ticket by id, including its event timeline (comments, assignments, close/reopen). Accessible to admin, the reporter, or the current assignee.",
        _schema({"id": _n("Ticket id")}, ["id"]),
        _make_handler({
            "method": "GET",
            "url": "{env.TICKETS_URL}/api/tickets/get?id={arg.id}",
            "headers": _HDR,
        }),
    ),
    (
        "tickets_update",
        "Edit an existing ticket's subject, body, or category. Admin, the reporter, and the current assignee may update. Use this when a ticket needs new findings added or its subject sharpened — preserves the event timeline instead of closing and re-filing.",
        _schema(
            {
                "id": _n("Ticket id"),
                "subject": _s("New subject line"),
                "body": _s("New body (markdown OK)"),
                "category": _s("One of: tool, bug, other"),
            },
            ["id"],
        ),
        _make_handler({
            "method": "POST",
            "url": "{env.TICKETS_URL}/api/tickets/update",
            "headers": _HDR,
        }),
    ),
    (
        "tickets_comment",
        "Add a comment to a ticket. The admin, the reporter, and the current assignee may comment. Use this to provide updates, ask questions, or record resolution notes.",
        _schema(
            {
                "id": _n("Ticket id"),
                "body": _s("Comment body"),
            },
            ["id", "body"],
        ),
        _make_handler({
            "method": "POST",
            "url": "{env.TICKETS_URL}/api/tickets/comment",
            "headers": _HDR,
        }),
    ),
    (
        "tickets_list",
        "List all tickets (admin only). Filter by status. Returns each ticket's latest assignee + reporter username for context.",
        _schema({"status": _s("One of: open (default), closed, all")}),
        _make_handler({
            "method": "GET",
            "url": "{env.TICKETS_URL}/api/tickets/list?status={arg.status}",
            "headers": _HDR,
        }),
    ),
    (
        "tickets_assign",
        "Assign a ticket to an agent (admin only). Pass either `agent` (username) or `assigneeId` (numeric user id). The agent will see this ticket in tickets_mine. Optional `note` is recorded in the timeline.",
        _schema(
            {
                "id": _n("Ticket id"),
                "agent": _s("Agent username (preferred)"),
                "assigneeId": _n("Numeric user id (alternative)"),
                "note": _s("Optional note for the timeline"),
            },
            ["id"],
        ),
        _make_handler({
            "method": "POST",
            "url": "{env.TICKETS_URL}/api/tickets/assign",
            "headers": _HDR,
        }),
    ),
    (
        "tickets_close",
        "Close an open ticket (admin only). Records optional note in the timeline.",
        _schema(
            {
                "id": _n("Ticket id"),
                "note": _s("Optional note for the timeline"),
            },
            ["id"],
        ),
        _make_handler({
            "method": "POST",
            "url": "{env.TICKETS_URL}/api/tickets/close",
            "headers": _HDR,
        }),
    ),
    (
        "tickets_reopen",
        "Reopen a closed ticket (admin only).",
        _schema(
            {
                "id": _n("Ticket id"),
                "note": _s("Optional note for the timeline"),
            },
            ["id"],
        ),
        _make_handler({
            "method": "POST",
            "url": "{env.TICKETS_URL}/api/tickets/reopen",
            "headers": _HDR,
        }),
    ),
]


def register(ctx) -> None:
    for name, description, schema, handler in TOOLS:
        ctx.register_tool(
            name=name,
            toolset="tickets",
            schema=schema,
            handler=handler,
            description=description,
        )
    print(
        f"[tickets] registered {len(TOOLS)} tools -> {_env('TICKETS_URL') or '(TICKETS_URL unset)'} as {_env('USER_ID') or '(USER_ID unset)'}",
        flush=True,
    )