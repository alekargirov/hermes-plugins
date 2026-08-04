"""sonarr — Sonarr series library, search, add, command, calendar, queue.

Nine tools against the Sonarr /api/v3 endpoints. sonarr_add is the
notable one — Sonarr v4 rejects hand-built minimal payloads with a bare 400.
The recipe is to take the ENTIRE series object returned by sonarr_search
(it carries seasons, images, titleSlug, languageProfileId — all required by
model binding) and override just qualityProfileId, rootFolderPath,
monitored, and addOptions:{monitor:"all", searchForMissingEpisodes:true}.
Constructing the object from scratch is what produces the 400.
sonarr_command (RefreshSeries + SeriesSearch) is how to populate episode
records after the fact if addOptions was forgotten.

Env (profile .env): SONARR_URL (e.g. http://10.0.1.10:8989), SONARR_API_KEY.
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


def _o(d):
    return {"type": "object", "description": d}


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


_HDR = {"X-Api-Key": "{env.SONARR_API_KEY}"}


TOOLS = [
    (
        "sonarr_library",
        "List TV shows in the Sonarr library (id, title, year, tvdbId, status, monitored). Trimmed to essential fields so large libraries return complete and untruncated.",
        _schema({}),
        _make_handler({
            "method": "GET",
            "url": "{env.SONARR_URL}/api/v3/series",
            "headers": _HDR,
            "select": ["id", "title", "year", "tvdbId", "status", "monitored"],
        }),
    ),
    (
        "sonarr_search",
        "Search for a TV show in Sonarr.",
        _schema({"query": _s("TV show title to search for")}, ["query"]),
        _make_handler({
            "method": "GET",
            "url": "{env.SONARR_URL}/api/v3/series/lookup?term={arg.query}",
            "headers": _HDR,
        }),
    ),
    (
        "sonarr_add",
        "Add a TV show to Sonarr. RECIPE (v4 rejects hand-built minimal payloads with an unhelpful bare 400): take the ENTIRE series object returned by sonarr_search for your show (it includes seasons, images, titleSlug, languageProfileId — all required by model binding), then override just: qualityProfileId (from sonarr_qualityprofile), rootFolderPath (from sonarr_rootfolder), monitored:true, and addOptions:{monitor:all, searchForMissingEpisodes:true}. Do NOT construct the object from scratch — that is the cause of ticket #137's 400s. addOptions is what creates/searches episodes; if forgotten, fix after with sonarr_command (RefreshSeries then SeriesSearch).",
        _schema(
            {
                "payload": _o(
                    "Sonarr series object: tvdbId, title, titleSlug, qualityProfileId, rootFolderPath, monitored, seasonFolder, AND addOptions:{\"monitor\":\"all\",\"searchForMissingEpisodes\":true} — the addOptions block is what populates episode records and triggers the initial search."
                ),
            },
            ["payload"],
        ),
        _make_handler({
            "method": "POST",
            "url": "{env.SONARR_URL}/api/v3/series",
            "headers": _HDR,
            "body": "{arg.payload}",
        }),
    ),
    (
        "sonarr_command",
        "Run a Sonarr command. If a freshly added series shows no episodes in sonarr_wanted/sonarr_library, call name=RefreshSeries with its seriesId to create the episode records, then name=SeriesSearch with the seriesId to search. (Also valid: RescanSeries, MissingEpisodeSearch.) This is the programmatic equivalent of the manual unmonitor/monitor toggle.",
        _schema(
            {
                "payload": _o(
                    'Command object, e.g. {"name":"RefreshSeries","seriesId":77} then {"name":"SeriesSearch","seriesId":77}'
                ),
            },
            ["payload"],
        ),
        _make_handler({
            "method": "POST",
            "url": "{env.SONARR_URL}/api/v3/command",
            "headers": _HDR,
            "body": "{arg.payload}",
        }),
    ),
    (
        "sonarr_calendar",
        "Get upcoming episodes from Sonarr. Defaults to today through +14 days.",
        _schema(
            {
                "start": _s("Start date (ISO 8601, e.g. 2026-05-16). Omit for today."),
                "end": _s("End date (ISO 8601, e.g. 2026-05-23). Omit for today+14d."),
            }
        ),
        _make_handler({
            "method": "GET",
            "url": "{env.SONARR_URL}/api/v3/calendar?start={arg.start|{now}}&end={arg.end|{now+14d}}&includeSeries=true",
            "headers": _HDR,
        }),
    ),
    (
        "sonarr_queue",
        "Get the Sonarr download queue.",
        _schema({}),
        _make_handler({
            "method": "GET",
            "url": "{env.SONARR_URL}/api/v3/queue?includeSeries=true&includeEpisode=true",
            "headers": _HDR,
        }),
    ),
    (
        "sonarr_wanted",
        "Get missing monitored episodes from Sonarr. Returns 10 per page — increment page for more. totalRecords in response gives the total count.",
        _schema({"page": _n("Page number, starting at 1 (default 1)")}),
        _make_handler({
            "method": "GET",
            "url": "{env.SONARR_URL}/api/v3/wanted/missing?pageSize=10&includeSeries=true&page={arg.page|1}",
            "headers": _HDR,
        }),
    ),
    (
        "sonarr_rootfolder",
        "List Sonarr root folders (id, path, accessible, freeSpace). Call before sonarr_add to get a valid rootFolderPath (use the path value).",
        _schema({}),
        _make_handler({
            "method": "GET",
            "url": "{env.SONARR_URL}/api/v3/rootfolder",
            "headers": _HDR,
            "select": ["id", "path", "accessible", "freeSpace"],
        }),
    ),
    (
        "sonarr_qualityprofile",
        "List Sonarr quality profiles (id, name). Call before sonarr_add to get a valid qualityProfileId (use the id).",
        _schema({}),
        _make_handler({
            "method": "GET",
            "url": "{env.SONARR_URL}/api/v3/qualityprofile",
            "headers": _HDR,
            "select": ["id", "name"],
        }),
    ),
]


def register(ctx) -> None:
    for name, description, schema, handler in TOOLS:
        ctx.register_tool(
            name=name,
            toolset="sonarr",
            schema=schema,
            handler=handler,
            description=description,
        )
    print(
        f"[sonarr] registered {len(TOOLS)} tools -> {_env('SONARR_URL') or '(SONARR_URL unset)'}",
        flush=True,
    )