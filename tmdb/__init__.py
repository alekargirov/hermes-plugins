"""tmdb — The Movie DB search, details, credits, popular, top-rated.

Five GETs against api.themoviedb.org/3. API key passed as the `api_key` query
param (TMDB's auth pattern, not a header).

Env (profile .env): TMDB_API_KEY.
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


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


TOOLS = [
    (
        "tmdb_search",
        "Search movies or TV shows using TMDB. type: 'movie' or 'tv'.",
        _schema(
            {
                "type": _s("'movie' or 'tv'"),
                "query": _s("Search query"),
            },
            ["type", "query"],
        ),
        _make_handler({
            "method": "GET",
            "url": "https://api.themoviedb.org/3/search/{arg.type}?api_key={env.TMDB_API_KEY}&query={arg.query}",
        }),
    ),
    (
        "tmdb_get_details",
        "Get movie or TV show details by TMDB ID. type: 'movie' or 'tv'.",
        _schema(
            {
                "type": _s("'movie' or 'tv'"),
                "id": _n("TMDB ID"),
            },
            ["type", "id"],
        ),
        _make_handler({
            "method": "GET",
            "url": "https://api.themoviedb.org/3/{arg.type}/{arg.id}?api_key={env.TMDB_API_KEY}",
        }),
    ),
    (
        "tmdb_get_credits",
        "Get cast and crew credits for a movie or TV show by TMDB ID. type: 'movie' or 'tv'.",
        _schema(
            {
                "type": _s("'movie' or 'tv'"),
                "id": _n("TMDB ID"),
            },
            ["type", "id"],
        ),
        _make_handler({
            "method": "GET",
            "url": "https://api.themoviedb.org/3/{arg.type}/{arg.id}/credits?api_key={env.TMDB_API_KEY}",
        }),
    ),
    (
        "tmdb_get_popular",
        "Get popular movies or TV shows from TMDB. type: 'movie' or 'tv'.",
        _schema(
            {
                "type": _s("'movie' or 'tv'"),
                "page": _n("Page number"),
            },
            ["type", "page"],
        ),
        _make_handler({
            "method": "GET",
            "url": "https://api.themoviedb.org/3/{arg.type}/popular?api_key={env.TMDB_API_KEY}&page={arg.page}",
        }),
    ),
    (
        "tmdb_get_top_rated",
        "Get top-rated movies from TMDB.",
        _schema({"page": _n("Page number")}, ["page"]),
        _make_handler({
            "method": "GET",
            "url": "https://api.themoviedb.org/3/movie/top_rated?api_key={env.TMDB_API_KEY}&page={arg.page}",
        }),
    ),
]


def register(ctx) -> None:
    for name, description, schema, handler in TOOLS:
        ctx.register_tool(
            name=name,
            toolset="tmdb",
            schema=schema,
            handler=handler,
            description=description,
        )
    key = _env("TMDB_API_KEY")
    print(
        f"[tmdb] registered {len(TOOLS)} tools (key {'set' if key else 'UNSET'})",
        flush=True,
    )