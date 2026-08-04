"""notes — Hermes plugin for the notes vault (notes-srv).

Calls notes-srv's /api/v2 REST surface directly. notes-srv has NO users and NO
authentication beyond one rule: the X-API-Key string IS the top-level folder
this caller may write under (key `claude` -> may write `claude` and
`claude/...`, nothing else), enforced in the app's api/lib/vault.ts. There is
therefore no user id to carry and no reason for an /api/agent/tools endpoint —
a second agent surface would give that scoping rule a second place to go wrong.

Env (profile .env):
  NOTES_URL      base URL (dev default http://notes:3000)
  NOTES_API_KEY  the caller's key AND its writable folder — load-bearing

Tool descriptions port VERBATIM from srv-mcp-yaml/notes.yaml. They are the
agent's only guidance; do not paraphrase them.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

# The tool surface this file was built for. hermes loads plugins at PROCESS
# START, so copying this file to an agent host changes nothing until that agent
# is restarted — a stale copy offers tools the app has changed, or misses tools
# entirely. The register() log line prints this so a stale copy is visible.
PLUGIN_VERSION = "2026-08-04.9"

DEFAULT_URL = "http://notes:3000"


def _env(name: str, default: str = "") -> str:
    """Profile-scoped credential read. The multiplexed gateway (hermes 0.18+)
    keeps each profile's .env in an isolated per-turn secret scope and never
    mutates os.environ — a bare os.environ.get returns another profile's value
    or nothing. get_secret honours the scope; on a single-profile gateway
    (prod: one container per user) it falls through to os.environ, so both
    modes work.
    """
    try:
        from agent.secret_scope import get_secret

        val = get_secret(name, "")
    except Exception:
        val = os.environ.get(name, "")
    return val or default


def _call(method: str, path: str, args: dict, arg_style: str) -> str:
    base = _env("NOTES_URL", DEFAULT_URL).rstrip("/")
    args = args or {}
    url = base + path
    data = None
    headers = {"X-API-Key": _env("NOTES_API_KEY")}

    if arg_style == "query":
        # Drop empties: `?path=` is a different request to notes-srv than no
        # query at all (bare = vault root).
        clean = {k: v for k, v in args.items() if v is not None and v != ""}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    else:
        headers["Content-Type"] = "application/json"
        data = json.dumps(args).encode()

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        return json.dumps({"ok": False, "message": f"notes HTTP {e.code}: {body}"})
    except Exception as e:  # noqa: BLE001 — surface it to the agent, never crash the turn
        return json.dumps({"ok": False, "message": f"notes unreachable: {e}"})


def _make_handler(method: str, path: str, arg_style: str):
    def _handler(args: dict, session_id: str = None, **kwargs) -> str:
        return _call(method, path, args, arg_style)

    return _handler


def _s(d):
    return {"type": "string", "description": d}


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


TOOLS = [
    (
        "notes_tree",
        "Full folder/file tree of the notes vault. Returns the whole tree; use notes_list to scope to one folder level.",
        _schema({}),
        "GET",
        "/api/v2/tree",
        "query",
    ),
    (
        "notes_list",
        "List direct subfolders and notes at one folder level. Omit path for vault root.",
        _schema({"path": _s('Folder path (e.g. "claude/conventions"). Empty = vault root.')}),
        "GET",
        "/api/v2/folders/list",
        "query",
    ),
    (
        "notes_read",
        'Read a note by path. Path is "folder/Title" — no .md extension (e.g. '
        '"claude/conventions/INDEX"). Returns the markdown AND every comment thread '
        "on it (see commentsText for a readable rendering). Comments are anchored by "
        '"^a1b2c3" markers in the content: KEEP those markers when you rewrite a '
        "note, they are what holds each comment to its paragraph.",
        _schema({"path": _s("Note path (folder/Title, no .md)")}, ["path"]),
        "GET",
        "/api/v2/notes/read",
        "query",
    ),
    (
        "notes_search",
        "Full-text search (case-insensitive substring over title+content) across the notes vault. Returns matching notes with full content.",
        _schema({"q": _s("Search query")}, ["q"]),
        "GET",
        "/api/v2/notes/search",
        "query",
    ),
    (
        "notes_comments",
        "List the comment threads on a note (anchors, comments, replies) without its content. notes_read already includes these — use this only when you want the threads alone.",
        _schema({"path": _s('Note path, "folder/Title" — no .md')}, ["path"]),
        "GET",
        "/api/v2/notes/comments",
        "query",
    ),
    (
        "notes_write",
        "Create or update a note. Path must be under YOUR top-level folder (your "
        "username is the write key; e.g. claude/...). Content is a markdown string. "
        'Path is "folder/Title" — no .md. Preserve any "^a1b2c3" block markers the '
        "note came with: they anchor existing comments, and dropping them makes the "
        "server re-attach by matching text, or orphan the thread when it can't.",
        _schema(
            {
                "path": _s('Note path under your folder (e.g. "claude/apps/notes-srv/overview")'),
                "content": _s("Full note contents (markdown)"),
            },
            ["path", "content"],
        ),
        "POST",
        "/api/v2/notes/write",
        "body",
    ),
    (
        "notes_comment_reply",
        "Reply to a comment thread on a note. Pass the anchor exactly as notes_read "
        'shows it in brackets — "[^a1b2c3]" means anchor "a1b2c3". Your reply is '
        "attributed to you by name. You can only answer threads a human opened; "
        "replying on an anchor with no thread is rejected, and there is no way to "
        "start one.",
        _schema(
            {
                "path": _s('Note path, "folder/Title" — no .md'),
                "anchor": _s('Block anchor of the thread, without the caret (e.g. "a1b2c3")'),
                "body": _s("The reply text"),
            },
            ["path", "anchor", "body"],
        ),
        "POST",
        "/api/v2/notes/comments/reply",
        "body",
    ),
    (
        "notes_move",
        'Move or rename a note. Both paths must be under your own top-level folder. Paths are "folder/Title" — no .md.',
        _schema(
            {"from": _s("Current path"), "to": _s("New path")},
            ["from", "to"],
        ),
        "POST",
        "/api/v2/notes/move",
        "body",
    ),
    (
        "notes_delete",
        'Delete a note by path. Must be under your own top-level folder. Path is "folder/Title" — no .md.',
        _schema({"path": _s("Path of the note to delete")}, ["path"]),
        "POST",
        "/api/v2/notes/delete",
        "body",
    ),
]


def register(ctx) -> None:
    for name, description, schema, method, path, arg_style in TOOLS:
        ctx.register_tool(
            name=name,
            toolset="notes",
            schema=schema,
            handler=_make_handler(method, path, arg_style),
            description=description,
        )
    print(
        f"[notes] registered {len(TOOLS)} tools (v{PLUGIN_VERSION}) -> "
        f"{_env('NOTES_URL', DEFAULT_URL)} "
        f"as key {_env('NOTES_API_KEY') or '(none — reads only)'}",
        flush=True,
    )
