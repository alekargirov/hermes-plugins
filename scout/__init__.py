"""scout — Hermes plugin for the Scout research store (scout-srv).

Calls scout-srv's /api/v1 REST surface directly. The X-Api-Key is a shared
secret, not an identity: scout is single-user.

Env (profile .env):
  SCOUT_URL      base URL (dev default http://scout:3026)
  SCOUT_API_KEY  the shared key

Tool descriptions are byte-identical to src/lib/server/mcp.ts. Two languages,
two copies: editing one means editing the other. Two tools carry the same
arg-reshaping mcp.ts does in-process — scout_nearby folds lat/lon into a
single `near` query param, and scout_mission_list's rootId never reaches the
REST call at all, it only filters the tree client-side after the fact. Get
those wrong and this plugin silently disagrees with what the app itself does
for its own MCP callers.
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

# hermes loads plugins at PROCESS START — copying this file to an agent host
# changes nothing until that agent restarts. The register() log line prints
# this so a stale copy is visible; see notes/__init__.py for the incident that
# made this convention non-optional.
PLUGIN_VERSION = "2026-08-08.1"
DEFAULT_URL = "http://scout:3026"


def _env(name: str, default: str = "") -> str:
    """Profile-scoped credential read. The multiplexed gateway keeps each
    profile's .env in an isolated per-turn secret scope and never mutates
    os.environ — a bare os.environ.get returns another profile's value or
    nothing. get_secret honours the scope; on a single-profile gateway it
    falls through to os.environ, so both modes work."""
    try:
        from agent.secret_scope import get_secret

        val = get_secret(name, "")
    except Exception:
        val = os.environ.get(name, "")
    return val or default


def _call(method: str, path: str, args: dict) -> str:
    base = _env("SCOUT_URL", DEFAULT_URL).rstrip("/")
    key = _env("SCOUT_API_KEY")
    # Refuse by NAME before the request goes out: an empty auth header produces
    # a bare 401 that an agent reports as "the backend is down".
    if not key:
        return "SCOUT_API_KEY is not set in this agent's .env — cannot call scout."
    url = f"{base}/api/v1{path}"
    data = None
    headers = {"X-Api-Key": key, "Content-Type": "application/json"}
    if method == "GET":
        clean = {k: v for k, v in (args or {}).items() if v not in (None, "")}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    else:
        data = json.dumps(args or {}).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode()
    except urllib.error.HTTPError as e:
        return f"scout {e.code} at {url}: {e.read().decode()[:400]}"
    except Exception as e:
        # Name the URL and the variable — the difference between a mystery and
        # a one-line fix.
        return f"scout unreachable at {url} (SCOUT_URL): {e}"


_PATH_PARAM = re.compile(r":(\w+)")


def _fill_path(path: str, args: dict):
    """Substitute :param placeholders in a REST path from args, matching
    mcp.ts's callTool. Returns the filled path and the set of arg names it
    consumed, so callers exclude them from the query/body that follows."""
    used = set()

    def _sub(m):
        k = m.group(1)
        used.add(k)
        return urllib.parse.quote(str(args.get(k, "")), safe="")

    return _PATH_PARAM.sub(_sub, path), used


def _nearby_to_rest_args(args: dict) -> dict:
    """scout_nearby is a point-radius convenience wrapper over /search: mcp.ts
    folds lat/lon into a single `near` query param before dispatch, exactly as
    below."""
    rest = dict(args or {})
    lat = rest.pop("lat", None)
    lon = rest.pop("lon", None)
    rest["near"] = f"{lat},{lon}"
    return rest


def _find_subtree(nodes, root_id):
    for n in nodes or []:
        if n.get("id") == root_id:
            return n
        found = _find_subtree(n.get("children"), root_id)
        if found is not None:
            return found
    return None


def _mission_list_post_process(data, raw_args):
    """rootId is client-only — never sent to REST — and scopes the already-
    returned tree down to one subtree, mirroring mcp.ts's findSubtree."""
    root_id = (raw_args or {}).get("rootId")
    if root_id in (None, ""):
        return data
    match = _find_subtree((data or {}).get("missions"), int(root_id))
    return {"missions": [match] if match is not None else []}


CRITERION_SCHEMA = {
    "type": "object",
    "properties": {
        "field": {"type": "string", "description": "the fact key this criterion judges, e.g. price_usd"},
        "op": {
            "type": "string",
            "enum": ["<", "<=", ">", ">=", "=", "within", "contains", "exists"],
            "description": "'within' is '<=' by another name and reads better on a distance",
        },
        "value": {"type": "string", "description": 'comparison value, always a string (e.g. "60000")'},
        "unit": {"type": "string"},
        "kind": {
            "type": "string",
            "enum": ["scope", "hard", "soft"],
            "description": (
                "scope decides whether a candidate belongs in the mission at all (refused at "
                "write time if it fails); hard must pass to score; soft is weighted into the score"
            ),
        },
        "weight": {"type": "number", "description": "soft-criterion weight (ignored for scope/hard)"},
    },
    "required": ["field", "op", "value", "kind"],
}


TOOLS = [
    {
        "name": "scout_subject_upsert",
        "description": (
            "Create or update a place, area or product in Scout. Give a slug, name and kind, and "
            "optionally lat/lon. Coordinates you supply are stored UNVERIFIED and shown in red until "
            "alek confirms them by hand — say so explicitly when you report back to the user. If you "
            "do not know exactly where something is, OMIT lat/lon rather than estimating or guessing a "
            "nearby point. Passing verified:true REQUIRES lat and lon and is refused with a 400 if you "
            "claim it without coordinates — verification is a human action, not something you can "
            "assert. If missionId is given, the subject is scope-checked against that mission's scope "
            "criteria (and its ancestors'); a subject outside scope is refused with a 422 and logged to "
            "the rejection log instead of being written."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "stable kebab-case id"},
                "name": {"type": "string"},
                "kind": {"type": "string", "enum": ["place", "area", "product"]},
                "lat": {"type": "number", "description": "omit if unknown — do not estimate"},
                "lon": {"type": "number", "description": "omit if unknown — do not estimate"},
                "geomKind": {
                    "type": "string",
                    "enum": ["captured", "corrected", "geocoded", "inferred"],
                    "description": "where the coordinate came from",
                },
                "geomSource": {"type": "string", "description": "free-text provenance, e.g. a URL or note"},
                "verified": {
                    "type": "boolean",
                    "description": "REQUIRES lat/lon; refused with 400 without them — a human-only claim",
                },
                "missionId": {"type": "number", "description": "link to a mission; enforces its scope on write"},
                "tags": {
                    "type": "object",
                    "description": "free-form key/value tags, matched by \"=\" scope criteria",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["slug", "name", "kind"],
        },
        "method": "POST",
        "path": "/subjects",
    },
    {
        "name": "scout_fact_add",
        "description": (
            "Attach a fact to a subject. kind must be one of captured, computed, declared, researched, "
            "inferred. A researched fact REQUIRES sourceUrl and is refused with a 400 if you omit it — "
            "never claim researched without a real citation. Use inferred, not researched, when you are "
            "reasoning or estimating rather than citing a source. valueText and/or valueNum hold the "
            "fact's value; ttlDays marks how long the fact stays fresh before scout_stale will flag it."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "subjectId": {"type": "number"},
                "key": {"type": "string"},
                "valueText": {"type": "string"},
                "valueNum": {"type": "number"},
                "unit": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": ["captured", "computed", "declared", "researched", "inferred"],
                },
                "sourceUrl": {"type": "string", "description": "REQUIRED when kind=researched"},
                "sourceName": {"type": "string"},
                "ttlDays": {"type": "number", "description": "days until scout_stale flags this fact"},
                "retrievedAt": {"type": "string", "description": "ISO timestamp; defaults to now"},
            },
            "required": ["subjectId", "key", "kind"],
        },
        "method": "POST",
        "path": "/subjects/:subjectId/facts",
    },
    {
        "name": "scout_mission_create",
        "description": (
            "Create a mission (or a sub-mission, via parentId) with an optional brief and an optional "
            "inline list of criteria. Each criterion has field, op (one of <, <=, >, >=, =, within, "
            "contains, exists), value, optional unit, kind (scope, hard, or soft) and optional weight. "
            "scope criteria define what belongs in the mission at all — a candidate outside scope is "
            "refused at write time, not merely scored low. hard criteria must pass; soft criteria are "
            "weighted toward a score. A sub-mission inherits its parent's criteria unless it overrides "
            "the same (field, kind) pair."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "brief": {"type": "string"},
                "parentId": {"type": "number", "description": "makes this a sub-mission"},
                "position": {"type": "number"},
                "criteria": {"type": "array", "items": CRITERION_SCHEMA},
            },
            "required": ["name"],
        },
        "method": "POST",
        "path": "/missions",
    },
    {
        "name": "scout_mission_list",
        "description": (
            "List every mission as a tree (each node carries its own, unmerged criteria — not the "
            "merged ancestor chain used for scope/scoring). Pass rootId to get back only the subtree "
            "rooted at that mission id and its descendants, instead of the whole forest."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "rootId": {"type": "number", "description": "optional: scope the result to this mission's subtree"},
            },
        },
        "method": "GET",
        "path": "/missions",
        "client_only_args": ("rootId",),
        "post_process": _mission_list_post_process,
    },
    {
        "name": "scout_search",
        "description": (
            "Search subjects (places, areas, products) by mission, kind, free-text name (q), "
            "verification status, or location. For a spatial search pass near as \"lat,lon\" together "
            "with radiusM (both required together); withinSlug restricts to subjects inside a named "
            "area's polygon. Each result reports geomVerified — when false, the pin is unconfirmed and "
            "any spatial match (near/radiusM, withinSlug) against it is only as good as that unverified "
            "guess; report that caveat to the user rather than presenting proximity as certain."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "missionId": {"type": "number"},
                "kind": {"type": "string", "enum": ["place", "area", "product"]},
                "q": {"type": "string", "description": "substring match on name"},
                "verified": {"type": "boolean"},
                "near": {"type": "string", "description": '"lat,lon" — must be given together with radiusM'},
                "radiusM": {"type": "number", "description": "metres; must be given together with near"},
                "withinSlug": {"type": "string", "description": "slug of an area-kind subject"},
                "limit": {"type": "number"},
                "offset": {"type": "number"},
            },
        },
        "method": "GET",
        "path": "/search",
    },
    {
        "name": "scout_nearby",
        "description": (
            "Find subjects within radiusM metres of a lat/lon point — a convenience wrapper around "
            "scout_search's spatial filter for point-radius lookups. Each result reports geomVerified; "
            "when false the match is against an UNVERIFIED pin and the proximity itself is unconfirmed "
            "— always surface that caveat, do not report it as a clean hit."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lon": {"type": "number"},
                "radiusM": {"type": "number", "description": "search radius in metres"},
                "kind": {"type": "string", "enum": ["place", "area", "product"]},
                "missionId": {"type": "number"},
                "verified": {"type": "boolean"},
                "limit": {"type": "number"},
            },
            "required": ["lat", "lon", "radiusM"],
        },
        "method": "GET",
        "path": "/search",
        "to_rest_args": _nearby_to_rest_args,
    },
    {
        "name": "scout_score",
        "description": (
            "Score a mission's linked subjects against its full merged criteria chain (root down to "
            "this mission). Returns hardPass, a weighted soft score, and a per-criterion explanation for "
            "each subject. Any spatial criterion (distance/near/within fields) that passes ONLY because "
            "of an unverified pin carries caveat: \"pin unverified\" in its result — always report that "
            "caveat rather than presenting the pass as a clean, confirmed result."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "missionId": {"type": "number"},
            },
            "required": ["missionId"],
        },
        "method": "GET",
        "path": "/missions/:missionId/score",
    },
    {
        "name": "scout_stale",
        "description": (
            "List current facts whose retrievedAt + ttlDays has passed (oldest first) — the things "
            "Scout believes it knows but which are due for a re-check. Pass limit to cap how many are "
            "returned (default 100, max 500)."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "number", "description": "default 100, max 500"},
            },
        },
        "method": "GET",
        "path": "/stale",
    },
    {
        "name": "scout_rejected",
        "description": (
            "List the scope-rejection log: candidates that were refused at write time for being outside "
            "a mission's scope (or its ancestors'), rather than merely scoring low. Optionally filter by "
            "missionId. Useful for auditing whether a mission's scope is too narrow (rejecting things "
            "that should belong) or working as intended."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "missionId": {"type": "number"},
                "limit": {"type": "number", "description": "default 100, max 500"},
            },
        },
        "method": "GET",
        "path": "/rejected",
    },
]

assert len(TOOLS) == 9, "scout-srv's mcp.ts declares exactly 9 tools — update this comment if that changes"


def _make_handler(tool: dict):
    def _handler(args: dict, session_id: str = None, **kwargs) -> str:
        raw_args = dict(args or {})
        to_rest = tool.get("to_rest_args")
        rest_args = to_rest(raw_args) if to_rest else dict(raw_args)
        for k in tool.get("client_only_args", ()):
            rest_args.pop(k, None)

        filled_path, used = _fill_path(tool["path"], rest_args)
        remaining = {k: v for k, v in rest_args.items() if k not in used}

        text = _call(tool["method"], filled_path, remaining)

        post = tool.get("post_process")
        if post:
            try:
                data = json.loads(text)
            except Exception:
                return text  # an error string from _call, not JSON — hand it through
            try:
                return json.dumps(post(data, raw_args))
            except Exception:
                return text  # malformed upstream body — hand it through unmodified rather than crash

        return text

    return _handler


def _fn_schema(name: str, description: str, params: dict) -> dict:
    """hermes registers `schema` VERBATIM as the OpenAI `function` object, so
    name and description must live INSIDE it and the argument schema must sit
    under `parameters`. Registering a bare {"type":"object","properties":...}
    leaves `function.parameters` absent; the schema sanitizer then substitutes
    an empty {"type":"object","properties":{}} and the model sees a tool with
    no arguments and no description. See _template/tool_schema.py."""
    return {"name": name, "description": description, "parameters": params}


def register(ctx) -> None:
    for tool in TOOLS:
        ctx.register_tool(
            name=tool["name"],
            toolset="scout",
            schema=_fn_schema(tool["name"], tool["description"], tool["schema"]),
            handler=_make_handler(tool),
            description=tool["description"],
        )
    print(
        f"[scout] registered {len(TOOLS)} tools (v{PLUGIN_VERSION}) -> "
        f"{_env('SCOUT_URL', DEFAULT_URL)} "
        f"as key {'(set)' if _env('SCOUT_API_KEY') else '(none — every call will refuse)'}",
        flush=True,
    )
