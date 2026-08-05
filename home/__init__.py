"""home — Hermes plugin for the homepage (home-srv-v2).

Calls home-srv-v2's /api/v2 REST surface directly. Unlike notes and recipes,
this app IS user-scoped and it authenticates properly: `X-Home-Key` AND
`X-User-Id`, both required, checked in api/v2.ts. The key proves the caller is
a trusted tool caller; the user id says whom it acts for.

**The user id comes from the profile's env, never from the model.** That is the
whole identity rail here: HOME_USER_ID is put in the .env by the operator, the
model cannot see it and cannot set it, so an agent cannot act as somebody else
by asking. A profile with no HOME_USER_ID gets a 401 from the app and can
therefore act for nobody — the same fuse fin3's default profile has.

Env (profile .env):
  HOME_URL      base URL (default http://home2:3021)
  HOME_KEY      X-Home-Key, shared with the app's HOME_API_KEY
  HOME_USER_ID  identity id this profile acts as

Deliberately four tools. Adding, deleting, resizing, moving, grouping, widgets
and sync were tools once and were cut as noise — they fit the page better than
a bot. The REST endpoints still exist, so re-adding one is an edit here.

Two layers, and the tools split along them:
  - home_update changes a tile for EVERYONE (the global catalogue);
  - home_hide / home_unhide change the page for THIS PERSON only.

Tool descriptions port VERBATIM from srv-mcp-yaml/home.yaml.

One deliberate difference from the gate: the gate builds its body from a STRING
TEMPLATE, so an omitted argument arrives as `""` and the app has to treat `""`
as "didn't say" (api/lib/input.ts — it once wiped a tile's url, icon and
description because every unset field arrived as an empty string). This plugin
builds real JSON and simply omits keys the model did not provide, which the app
reads identically and which cannot blank a field by accident.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

PLUGIN_VERSION = "2026-08-05.4"

DEFAULT_URL = "http://home2:3021"


def _env(name: str, default: str = "") -> str:
    """Profile-scoped credential read — see the notes plugin for why a bare
    os.environ.get is wrong under the multiplexed gateway."""
    try:
        from agent.secret_scope import get_secret

        val = get_secret(name, "")
    except Exception:
        val = os.environ.get(name, "")
    return val or default


def _call(method: str, path: str, args: dict, arg_style: str) -> str:
    base = _env("HOME_URL", DEFAULT_URL).rstrip("/")
    args = dict(args or {})

    # Path parameters are consumed out of args so they never also travel in the
    # body — /items/{id}/hide takes its id from the URL, not the payload.
    if "{id}" in path:
        raw = args.pop("id", None)
        if raw in (None, ""):
            return json.dumps({"ok": False, "message": "id is required — get it from home_view"})
        path = path.replace("{id}", urllib.parse.quote(str(raw)))

    url = base + path
    data = None
    headers = {
        "X-Home-Key": _env("HOME_KEY"),
        # From the env, never from the model. See the module docstring.
        "X-User-Id": _env("HOME_USER_ID"),
    }

    if arg_style == "query":
        # Booleans must go over the wire LOWERCASE. The app does
        # `c.req.query("includeHidden") === "true"` (api/v2.ts), and Python's
        # urlencode renders True as "True", which fails that comparison
        # silently — home_view(includeHidden=true) returned the ordinary page
        # and the hidden tiles were simply absent, with no error to notice.
        clean = {
            k: ("true" if v is True else "false" if v is False else v)
            for k, v in args.items()
            if v is not None and v != ""
        }
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    elif arg_style == "body":
        # Omit what the model did not set. The app treats absent and "" alike,
        # so this is compatible with the gate and cannot blank a field.
        clean = {k: v for k, v in args.items() if v is not None and v != ""}
        headers["Content-Type"] = "application/json"
        data = json.dumps(clean).encode()

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        return json.dumps(
            {"ok": False, "message": f"home HTTP {e.code}: {e.read().decode()[:300]}"}
        )
    except Exception as e:  # noqa: BLE001 — surface it to the agent, never crash the turn
        # NAME THE URL. A port-less VITA3_URL cost a night on 2026-08-04
        # because the bridge only said "unreachable: <errno>".
        return json.dumps(
            {"ok": False, "message": f"home unreachable at {url} — check HOME_URL: {e}"}
        )


def _make_handler(method: str, path: str, arg_style: str):
    def _handler(args: dict, session_id: str = None, **kwargs) -> str:
        return _call(method, path, args, arg_style)

    return _handler


def _s(d):
    return {"type": "string", "description": d}


def _n(d):
    return {"type": "number", "description": d}


def _b(d):
    return {"type": "boolean", "description": d}


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


TOOLS = [
    (
        "home_view",
        "The person's homepage exactly as they see it — sections in order (shared first, then theirs, then other people's), each tile with its id, title, url, description, icon, size, group and up/down status. Start here; every other tool needs an id from it.",
        _schema(
            {
                "includeHidden": _b(
                    "Include tiles this person has hidden, flagged `hidden` (default false). The only way to find something to un-hide."
                ),
            }
        ),
        "GET",
        "/api/v2/view",
        "query",
    ),
    (
        "home_update",
        "Fix a tile's title, description or icon. This is the GLOBAL layer: on a shared or discovered tile the change is EVERYONE's, which is deliberate. Refused with 403 on somebody else's personal bookmark. Pass only the fields you are changing — the rest are left alone.",
        _schema(
            {
                "id": _n("Tile id from home_view"),
                "title": _s("The tile's name"),
                "description": _s(
                    "Subtitle under the title. Omitting it leaves the current one; there is no way to clear it from here."
                ),
                "icon": _s("An emoji, or a URL to an image. Pass iconKind with it."),
                "iconKind": _s("emoji or url — say which `icon` is"),
            },
            ["id"],
        ),
        "PATCH",
        "/api/v2/items/{id}",
        "body",
    ),
    (
        "home_hide",
        'Take a tile off THIS person\'s page. Everyone else still sees it. Works on any tile, including shared and discovered ones — and it is what "I don\'t want to see this" means here. Reversible with home_unhide.',
        _schema({"id": _n("Tile id from home_view")}, ["id"]),
        "POST",
        "/api/v2/items/{id}/hide",
        "none",
    ),
    (
        "home_unhide",
        "Put a hidden tile back on this person's page. Find hidden ones with home_view includeHidden=true.",
        _schema({"id": _n("Tile id from home_view")}, ["id"]),
        "POST",
        "/api/v2/items/{id}/unhide",
        "none",
    ),
]


def register(ctx) -> None:
    for name, description, schema, method, path, arg_style in TOOLS:
        ctx.register_tool(
            name=name,
            toolset="home",
            schema=schema,
            handler=_make_handler(method, path, arg_style),
            description=description,
        )
    print(
        f"[home] registered {len(TOOLS)} tools (v{PLUGIN_VERSION}) -> "
        f"{_env('HOME_URL', DEFAULT_URL)} "
        f"as user {_env('HOME_USER_ID') or '(none — acts for nobody)'}",
        flush=True,
    )
