"""HTTP template engine for MCP-style YAML tool specs.

Runs a single templated HTTP request. Templates use these placeholders:

  {env.NAME|default}     environment variable (default applied if unset)
  {arg.NAME|default}     LLM-supplied argument (default applied if absent/empty)
  {now}                  today's UTC date as YYYY-MM-DD
  {now+N[dhms]}          today plus/minus N days/hours/minutes/seconds

The body of an {arg.X} may be any JSON-serialisable value; dicts/lists are
encoded with json.dumps so the body stays valid JSON.

A `select:` field on the spec trims a JSON list/object response to only the
named keys — useful for keeping large list payloads under the token budget.

Used by every plugin generated from the legacy MCP YAMLs.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Mapping

import requests


_UNIT_TO_KW = {"d": "days", "h": "hours", "m": "minutes", "s": "seconds"}
_PLACEHOLDER_RE = re.compile(r"^(now(?:[+-]\d+[dhms])?|now)$")


def _stringify(value: Any) -> str:
    """JSON-encode dicts/lists so they survive being substituted into a body."""
    if value is None or value == "":
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def _resolve_now(spec: str) -> str:
    """Resolve ``now`` and ``now+N[dhms]`` into ISO date strings (UTC)."""
    if spec == "now":
        return datetime.utcnow().strftime("%Y-%m-%d")
    m = re.fullmatch(r"now([+-])(\d+)([dhms])", spec)
    if not m:
        return spec
    sign, n, unit = m.group(1), int(m.group(2)), m.group(3)
    delta = timedelta(**{_UNIT_TO_KW[unit]: n if sign == "+" else -n})
    return (datetime.utcnow() + delta).strftime("%Y-%m-%d")


def _find_matching_close(text: str, start: int) -> int:
    """Return the index of the ``}`` that closes the ``{`` at ``start``."""
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _is_placeholder(content: str) -> bool:
    """Return True if ``content`` (text between ``{`` and ``}``) is a known placeholder."""
    if _PLACEHOLDER_RE.match(content):
        return True
    head, _, _ = content.partition("|")
    kind, _, name = head.partition(".")
    return kind in ("env", "arg") and bool(name)


def _resolve(content: str, env: Mapping[str, str], args: Mapping[str, Any]) -> str:
    """Resolve the inner text of one placeholder (no surrounding braces)."""
    if _PLACEHOLDER_RE.match(content):
        return _resolve_now(content)

    head, _, default = content.partition("|")
    kind, _, name = head.partition(".")
    if kind == "env":
        value = env.get(name, "")
        if value:
            return value
    elif kind == "arg":
        if name in args and args[name] is not None and args[name] != "":
            return _stringify(args[name])

    if default:
        return _substitute(default, env, args)
    return ""


def _substitute(
    template: str,
    env: Mapping[str, str],
    args: Mapping[str, Any],
) -> str:
    """Substitute every supported placeholder into ``template``.

    Non-placeholder braces (e.g. JSON ``{...}`` in a request body) are emitted
    literally so the scanner can still find nested placeholders inside them.
    """
    out: list[str] = []
    i = 0
    n = len(template)
    while i < n:
        ch = template[i]
        if ch != "{":
            out.append(ch)
            i += 1
            continue
        close = _find_matching_close(template, i)
        if close == -1 or not _is_placeholder(template[i + 1:close]):
            out.append("{")
            i += 1
            continue
        out.append(_resolve(template[i + 1:close], env, args))
        i = close + 1
    return "".join(out)


def _select(payload: Any, fields: list[str]) -> Any:
    """Trim a JSON payload down to the named keys."""
    if isinstance(payload, list):
        return [
            {k: item[k] for k in fields if isinstance(item, dict) and k in item}
            for item in payload
        ]
    if isinstance(payload, dict):
        return {k: payload[k] for k in fields if k in payload}
    return payload


def execute(
    spec: Mapping[str, Any],
    args: Mapping[str, Any],
    env: Mapping[str, str] | None = None,
    *,
    timeout: int = 30,
) -> str:
    """Run a templated HTTP request and return the response as a JSON string.

    ``spec`` is the dict form of one tool entry from the legacy MCP YAML.
    ``args`` are the parameters the LLM passed.
    ``env`` is the environment to read; defaults to ``os.environ``.
    """
    env_map = dict(env) if env is not None else dict(os.environ)
    method = spec["method"].upper()
    url = _substitute(spec["url"], env_map, args)
    headers = {
        k: _substitute(v, env_map, args)
        for k, v in (spec.get("headers") or {}).items()
    }

    request_kwargs: dict[str, Any] = {
        "method": method,
        "url": url,
        "headers": headers,
        "timeout": timeout,
    }

    body_template = spec.get("body")
    if body_template:
        body = _substitute(body_template, env_map, args)
        if body:
            request_kwargs["data"] = body.encode("utf-8")
            if not any(k.lower() == "content-type" for k in headers):
                request_kwargs["headers"]["Content-Type"] = "application/json"
    elif method in {"POST", "PUT", "PATCH"} and args:
        # No explicit body template, but POST/PUT/PATCH with args — auto-serialize
        # the args as a JSON body. Mirrors the legacy MCP runtime's behaviour.
        request_kwargs["data"] = json.dumps(args, separators=(",", ":")).encode("utf-8")
        if not any(k.lower() == "content-type" for k in headers):
            request_kwargs["headers"]["Content-Type"] = "application/json"

    response = requests.request(**request_kwargs)

    try:
        payload: Any = response.json()
    except ValueError:
        payload = response.text

    if "select" in spec:
        payload = _select(payload, list(spec["select"]))

    if not response.ok:
        return json.dumps(
            {
                "error": f"HTTP {response.status_code} from {url}",
                "status": response.status_code,
                "body": payload,
            }
        )

    return json.dumps(payload)