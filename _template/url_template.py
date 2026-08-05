"""Reference implementation of the URL/body template the MCP YAML specs use.

NOT a plugin — the leading underscore keeps it out of hermes' plugin scan,
which only walks directories containing a plugin.yaml. This file exists so the
template rules live in ONE readable place with tests against them; each direct
plugin carries its own copy of `render` and `shape`, because hermes loads every
plugin directory independently and there is no shared import path between them.

If you change the rules here, change them in the plugins too. The test suite
(tests/test_url_template.py) is the spec.

Substitutions, matching mcp-srv's executor:
  {env.NAME}          -> os.environ / secret scope
  {arg.name}          -> the model's argument, URL-quoted in a path or query
  {arg.name|default}  -> that argument, or the literal default when unset
  {now}               -> today, ISO date
  {now+14d} {now-3d}  -> today shifted by whole days

`shape` ports mcp-srv's shapeResponse: when a tool declares select/limit AND
the body parses to a JSON ARRAY, trim and project it. A full Radarr movie
object is enormous and there are thousands of them; without this the model gets
a truncated wall of JSON instead of a usable list.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import urllib.parse

_NOW = re.compile(r"\{now([^}]*)\}")
_TOKEN = re.compile(r"\{(env|arg)([^}]*)\}")
_NOW_SHIFT = re.compile(r"^([+-])(\d+)d$")


def _now(expr: str) -> str:
    """`{now}`, `{now+14d}`, `{now-3d}` -> an ISO date."""
    today = _dt.date.today()
    m = _NOW_SHIFT.match(expr)
    if m:
        days = int(m.group(2))
        today = today + _dt.timedelta(days=days if m.group(1) == "+" else -days)
    return today.isoformat()


def render(template: str, args: dict, env, *, quote: bool) -> str:
    """Fill a template. `quote` URL-escapes substituted values — on for URLs,
    off for JSON bodies, where escaping would corrupt the payload."""
    args = args or {}

    # Date macros resolve FIRST, over the whole template, because they appear
    # INSIDE defaults: sonarr's calendar is
    # `start={arg.start|{now}}&end={arg.end|{now+14d}}`. A single pass whose
    # token regex stops at the first `}` swallows `{arg.start|{now}` and leaves
    # a stray brace — the URL then carried a literal `%7Bnow}` and Sonarr got a
    # garbage date range.
    template = _NOW.sub(lambda m: _now(m.group(1)), template)

    def sub(m: re.Match) -> str:
        kind, rest = m.group(1), m.group(2)
        if kind == "env":
            return env(rest.lstrip("."))
        name, _, default = rest.lstrip(".").partition("|")
        val = args.get(name)
        if val is None or val == "":
            val = default
        # Booleans must go over the wire lowercase: several of these apps
        # compare against the string "true", and Python renders True as "True".
        if isinstance(val, bool):
            val = "true" if val else "false"
        val = str(val)
        return urllib.parse.quote(val, safe="") if quote else val

    return _TOKEN.sub(sub, template)


def shape(text: str, select=None, limit=None) -> str:
    """Port of mcp-srv's shapeResponse. Only acts on a top-level JSON array;
    anything else is returned untouched."""
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
            {f: item.get(f) for f in select} if isinstance(item, dict) else item
            for item in items
        ]
    return json.dumps(items)
