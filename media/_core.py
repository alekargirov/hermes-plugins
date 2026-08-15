"""Shared core for the media plugin — the HTTP call, the URL template, and the
response shaping, written ONCE.

Until 2026-08-15 radarr, sonarr, lidarr, plex, nzb and tmdb were six sibling
plugin directories, and each carried its own byte-identical copy of everything
below. The copies were not laziness: hermes loads every plugin directory
independently, so there genuinely was no shared import path between them, and
each `__init__.py` said so at the top.

Folding them into ONE plugin removes that constraint. hermes' loader passes
`submodule_search_locations` and sets `__path__` (hermes_cli/plugins.py), so a
plugin directory is a package and `from ._core import ...` resolves. Six copies
collapse to one.

`_render` and `_shape` still port from _template/url_template.py, which remains
the readable spec with the tests — the OTHER nine plugins in this repo still
carry their own copies, so a rule change still starts there.

WHAT THIS FILE DOES NOT DECIDE
Each service keeps its own toolset. A single flat `media` toolset would put 42
tools in one bucket and re-create the failure this repo already paid for: when
fin3 shared the `todo` toolset the model read a neighbour's schema and refused
a change the tool supported. See tests/test_direct_plugins.py.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, NamedTuple, Optional

_NOW = re.compile(r"\{now([^}]*)\}")
_TOKEN = re.compile(r"\{(env|arg)([^}]*)\}")
_NOW_SHIFT = re.compile(r"^([+-])(\d+)d$")


class Tool(NamedTuple):
    """One HTTP call the model can make.

    `requires_env` names variables this ONE tool needs beyond the service's
    url_env/key_env — plex's collection writes need PLEX_MACHINE_ID, the four
    read tools do not. Unset, the template renders it empty and the call still
    goes out: `uri=server:///com.plexapp...` is a well-formed request that
    quietly creates an EMPTY collection, and nothing in the response says why.
    Refuse by name before the request instead.
    """

    name: str
    description: str
    schema: dict
    method: str
    url: str
    body: Optional[str] = None
    select: Optional[list] = None
    limit: Optional[int] = None
    requires_env: tuple = ()


class Service(NamedTuple):
    """One backend behind the media plugin.

    These six fields are the ENTIRE disagreement between the old six `_call`
    functions; everything else about them was character-identical.

    url_env      the variable holding the base URL, or None when the service
                 has no configurable host. tmdb is the only one: it talks to
                 api.themoviedb.org and its only config IS the key.
    key_env      the credential variable, or None when the credential is not a
                 separate value. nzb is the only one: its user and password are
                 rendered into the URL path by the tool template.
    auth_header  the header carrying key_env, or None when the credential does
                 not travel as a header (nzb: in the path; tmdb: in the query).
    redact       scrubs the URL before it appears in any message the model
                 sees. Only needed where the URL itself carries a secret.
    log_note     what the registration line names when there is no url_env.
    """

    name: str
    url_env: Optional[str]
    key_env: Optional[str]
    auth_header: Optional[str]
    accept_json: bool
    redact: Optional[Callable[[str], str]]
    log_note: Optional[str]
    version: str
    tools: list


def _env(name: str, default: str = "") -> str:
    """Profile-scoped credential read. The multiplexed gateway keeps each
    profile's .env in an isolated per-turn secret scope and never mutates
    os.environ — a bare os.environ.get returns another profile's value or
    nothing. On a single-profile gateway get_secret falls through to
    os.environ, so both modes work."""
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
        # Lists join with commas — see _template/url_template.py for why.
        if isinstance(val, (list, tuple)):
            val = ",".join(str(v) for v in val)
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


def _call(svc: Service, tool: Tool, args: dict) -> str:
    # Order matters and matches what the six copies did: URL first, then key.
    # Without the key guard the request goes out with an empty auth header and
    # the service answers a bare 401, which the agent reports as a broken
    # backend rather than one missing line in the profile .env. Name the
    # variable, never the value.
    if svc.url_env and not _env(svc.url_env):
        return json.dumps(
            {"ok": False, "message": f"{svc.url_env} is not set for this profile"}
        )
    if svc.key_env and not _env(svc.key_env):
        return json.dumps(
            {"ok": False, "message": f"{svc.key_env} is not set for this profile"}
        )
    for name in tool.requires_env:
        if not _env(name):
            return json.dumps(
                {
                    "ok": False,
                    "message": f"{name} is not set for this profile, "
                    f"and {tool.name} cannot work without it",
                }
            )

    url = _render(tool.url, args, quote=True)

    headers = {}
    if svc.accept_json:
        headers["Accept"] = "application/json"
    if svc.auth_header:
        headers[svc.auth_header] = _env(svc.key_env)

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
            text = resp.read().decode()
            if not text.strip():
                # Plex answers a successful DELETE with 200 and NO BODY. Handed
                # back as "" that is indistinguishable from a tool that did
                # nothing, and the model has to guess whether the collection is
                # gone. Say so instead.
                return json.dumps(
                    {
                        "ok": True,
                        "message": f"{tool.name} succeeded (HTTP {resp.status}, "
                        f"empty response)",
                    }
                )
            return _shape(text, tool.select, tool.limit)
    except urllib.error.HTTPError as e:
        return json.dumps(
            {
                "ok": False,
                "message": f"{svc.name} HTTP {e.code}: {e.read().decode()[:300]}",
            }
        )
    except Exception as e:  # noqa: BLE001 — surface it, never crash the turn
        safe = svc.redact(url) if svc.redact else url
        # Naming the URL turns a wrong host into a visible typo instead of a
        # plugin that looks broken. Naming the URL *variable* only makes sense
        # when there is one — tmdb has no host to misconfigure, and telling the
        # operator to "check TMDB_API_KEY" over a read timeout sends them after
        # a key that was working. A bad key arrives as an HTTP 401 above, where
        # it is unmistakable.
        hint = f" — check {svc.url_env}" if svc.url_env else ""
        return json.dumps(
            {"ok": False, "message": f"{svc.name} unreachable at {safe}{hint}: {e}"}
        )


def _make_handler(svc: Service, tool: Tool):
    def _handler(args: dict, session_id: str = None, **kwargs) -> str:
        return _call(svc, tool, args)

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


def _fn_schema(name: str, description: str, params: dict) -> dict:
    """hermes registers `schema` VERBATIM as the OpenAI `function` object, so
    name and description must live INSIDE it and the argument schema must sit
    under `parameters`. Registering a bare {"type":"object","properties":...}
    leaves `function.parameters` absent; the schema sanitizer then substitutes
    an empty {"type":"object","properties":{}} and the model sees a tool with
    no arguments and no description. See _template/tool_schema.py."""
    return {"name": name, "description": description, "parameters": params}


def register_service(ctx, svc: Service) -> None:
    """Register one service under ITS OWN toolset, then log where it points.

    The log line must never print a credential. tmdb's only config IS its key,
    and the first version of that plugin printed it straight into the container
    log, where docker keeps it.
    """
    for tool in svc.tools:
        ctx.register_tool(
            name=tool.name,
            toolset=svc.name,
            schema=_fn_schema(tool.name, tool.description, tool.schema),
            handler=_make_handler(svc, tool),
            description=tool.description,
        )

    if svc.url_env:
        target = _env(svc.url_env) or f"({svc.url_env} unset)"
    else:
        set_ = "(key set)" if _env(svc.key_env) else f"({svc.key_env} UNSET)"
        target = f"{svc.log_note} {set_}"
    print(
        f"[{svc.name}] registered {len(svc.tools)} tools (v{svc.version}) -> {target}",
        flush=True,
    )
