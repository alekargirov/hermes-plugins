"""radarr — Radarr movie library, search, add, delete, queue, profiles.

Eight tools against the Radarr /api/v3 endpoints. Mirrors lidarr's shape:
library/profile reads use `select:` to keep responses complete under the
token budget.

Env (profile .env): RADARR_URL (e.g. http://10.0.1.10:7878), RADARR_API_KEY.
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


_HDR = {"X-Api-Key": "{env.RADARR_API_KEY}"}


TOOLS = [
    (
        "radarr_library",
        "List all movies in the Radarr library (id, title, year, tmdbId, hasFile, monitored). Trimmed to essential fields so large libraries return complete and untruncated. Use the id field with radarr_delete to remove movies.",
        _schema({}),
        _make_handler({
            "method": "GET",
            "url": "{env.RADARR_URL}/api/v3/movie",
            "headers": _HDR,
            "select": ["id", "title", "year", "tmdbId", "hasFile", "monitored"],
        }),
    ),
    (
        "radarr_search",
        "Search for a movie in Radarr (lookup, not library search). Matched against title.",
        _schema({"query": _s("Movie title to search for")}, ["query"]),
        _make_handler({
            "method": "GET",
            "url": "{env.RADARR_URL}/api/v3/movie/lookup?term={arg.query}",
            "headers": _HDR,
        }),
    ),
    (
        "radarr_add",
        "Add a movie to Radarr. Use radarr_search first to get tmdbId and titleSlug.",
        _schema(
            {
                "tmdbId": _n("TMDB id from radarr_search"),
                "title": _s("Movie title from radarr_search"),
                "titleSlug": _s("title slug from radarr_search"),
                "qualityProfileId": _n("Quality profile id from radarr_qualityprofile"),
                "rootFolderPath": _s("Root folder path from radarr_rootfolder"),
                "monitored": _b("Add as monitored (default true)"),
            },
            ["tmdbId", "title", "titleSlug", "qualityProfileId", "rootFolderPath"],
        ),
        _make_handler({
            "method": "POST",
            "url": "{env.RADARR_URL}/api/v3/movie",
            "headers": _HDR,
        }),
    ),
    (
        "radarr_delete",
        "Delete a movie from Radarr by its id. Set deleteFiles=true to also remove files on disk. Get the id from radarr_library.",
        _schema(
            {
                "id": _n("Radarr movie id (from radarr_library)"),
                "deleteFiles": _b("Also remove files on disk (default false)"),
            },
            ["id"],
        ),
        _make_handler({
            "method": "DELETE",
            "url": "{env.RADARR_URL}/api/v3/movie/{arg.id}?deleteFiles={arg.deleteFiles|false}",
            "headers": _HDR,
        }),
    ),
    (
        "radarr_queue",
        "Get the Radarr download queue.",
        _schema({}),
        _make_handler({
            "method": "GET",
            "url": "{env.RADARR_URL}/api/v3/queue?includeMovie=true",
            "headers": _HDR,
        }),
    ),
    (
        "radarr_wanted",
        "Get missing/wanted movies from Radarr.",
        _schema({}),
        _make_handler({
            "method": "GET",
            "url": "{env.RADARR_URL}/api/v3/wanted/missing?pageSize=50",
            "headers": _HDR,
        }),
    ),
    (
        "radarr_rootfolder",
        "List Radarr root folders (id, path, accessible, freeSpace). Call before radarr_add to get a valid rootFolderPath (use the path value).",
        _schema({}),
        _make_handler({
            "method": "GET",
            "url": "{env.RADARR_URL}/api/v3/rootfolder",
            "headers": _HDR,
            "select": ["id", "path", "accessible", "freeSpace"],
        }),
    ),
    (
        "radarr_qualityprofile",
        "List Radarr quality profiles (id, name). Call before radarr_add to get a valid qualityProfileId (use the id).",
        _schema({}),
        _make_handler({
            "method": "GET",
            "url": "{env.RADARR_URL}/api/v3/qualityprofile",
            "headers": _HDR,
            "select": ["id", "name"],
        }),
    ),
]


def register(ctx) -> None:
    for name, description, schema, handler in TOOLS:
        ctx.register_tool(
            name=name,
            toolset="radarr",
            schema=schema,
            handler=handler,
            description=description,
        )
    print(
        f"[radarr] registered {len(TOOLS)} tools -> {_env('RADARR_URL') or '(RADARR_URL unset)'}",
        flush=True,
    )