"""notes — Notes vault (notes-srv v2).

Nine tools. Reads are open; writes are scoped by the profile's USER_ID /
USER_NAME — those ride in X-User-Id / X-API-Key headers, never through the
model, and the server checks them against its own auth. notes_read returns
the note AND every comment thread on it. Comments are anchored by
"^a1b2c3" markers in the content — KEEP those markers when rewriting a note,
they are what holds each thread to its paragraph. The agent may REPLY to a
thread but never open one — the app rejects a reply on an anchor with no
thread.

Env (profile .env): NOTES_URL (default http://notes:3000), USER_ID, USER_NAME.
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


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


_BASE = "{env.NOTES_URL|http://notes:3000}"
_WRITE_HDR = {"X-API-Key": "{env.USER_NAME}", "X-User-Id": "{env.USER_ID}"}


TOOLS = [
    (
        "notes_tree",
        "Full folder/file tree of the notes vault. Returns the whole tree; use notes_list to scope to one folder level.",
        _schema({}),
        _make_handler({
            "method": "GET",
            "url": f"{_BASE}/api/v2/tree",
        }),
    ),
    (
        "notes_list",
        "List direct subfolders and notes at one folder level. Omit path for vault root.",
        _schema(
            {
                "path": _s(
                    'Folder path (e.g. "claude/conventions"). Empty = vault root.'
                ),
            }
        ),
        _make_handler({
            "method": "GET",
            "url": f"{_BASE}/api/v2/folders/list?path={{arg.path|}}",
        }),
    ),
    (
        "notes_read",
        "Read a note by path. Path is 'folder/Title' — no .md extension (e.g. 'claude/conventions/INDEX'). Returns the markdown AND every comment thread on it (see commentsText for a readable rendering). Comments are anchored by '^a1b2c3' markers in the content: KEEP those markers when you rewrite a note, they are what holds each comment to its paragraph.",
        _schema(
            {"path": _s("Note path (folder/Title, no .md)")},
            ["path"],
        ),
        _make_handler({
            "method": "GET",
            "url": f"{_BASE}/api/v2/notes/read?path={{arg.path}}",
        }),
    ),
    (
        "notes_search",
        "Full-text search (case-insensitive substring over title+content) across the notes vault. Returns matching notes with full content.",
        _schema({"q": _s("Search query")}, ["q"]),
        _make_handler({
            "method": "GET",
            "url": f"{_BASE}/api/v2/notes/search?q={{arg.q}}",
        }),
    ),
    (
        "notes_write",
        "Create or update a note. Path must be under YOUR top-level folder (your username is the write key; e.g. claude/...). Content is a markdown string. Path is 'folder/Title' — no .md. Preserve any '^a1b2c3' block markers the note came with: they anchor existing comments, and dropping them makes the server re-attach by matching text, or orphan the thread when it can't.",
        _schema(
            {
                "path": _s(
                    "Note path under your folder (e.g. 'claude/apps/notes-srv/overview')"
                ),
                "content": _s("Full note contents (markdown)"),
            },
            ["path", "content"],
        ),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/notes/write",
            "headers": _WRITE_HDR,
        }),
    ),
    (
        "notes_comments",
        "List the comment threads on a note (anchors, comments, replies) without its content. notes_read already includes these — use this only when you want the threads alone.",
        _schema({"path": _s('Note path, "folder/Title" — no .md')}, ["path"]),
        _make_handler({
            "method": "GET",
            "url": f"{_BASE}/api/v2/notes/comments?path={{arg.path}}",
        }),
    ),
    (
        "notes_comment_reply",
        "Reply to a comment thread on a note. Pass the anchor exactly as notes_read shows it in brackets — '[^a1b2c3]' means anchor 'a1b2c3'. Your reply is attributed to you by name. You can only answer threads a human opened; replying on an anchor with no thread is rejected, and there is no way to start one.",
        _schema(
            {
                "path": _s('Note path, "folder/Title" — no .md'),
                "anchor": _s(
                    "Block anchor of the thread, without the caret (e.g. 'a1b2c3')"
                ),
                "body": _s("The reply text"),
            },
            ["path", "anchor", "body"],
        ),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/notes/comments/reply",
            "headers": _WRITE_HDR,
        }),
    ),
    (
        "notes_delete",
        "Delete a note by path. Must be under your own top-level folder. Path is 'folder/Title' — no .md.",
        _schema({"path": _s("Path of the note to delete")}, ["path"]),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/notes/delete",
            "headers": _WRITE_HDR,
        }),
    ),
    (
        "notes_move",
        "Move or rename a note. Both paths must be under your own top-level folder. Paths are 'folder/Title' — no .md.",
        _schema(
            {
                "from": _s("Current path"),
                "to": _s("New path"),
            },
            ["from", "to"],
        ),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/notes/move",
            "headers": _WRITE_HDR,
        }),
    ),
]


def register(ctx) -> None:
    for name, description, schema, handler in TOOLS:
        ctx.register_tool(
            name=name,
            toolset="notes",
            schema=schema,
            handler=handler,
            description=description,
        )
    print(
        f"[notes] registered {len(TOOLS)} tools -> {_env('NOTES_URL') or '(NOTES_URL unset)'} as {_env('USER_NAME') or '(USER_NAME unset)'}",
        flush=True,
    )