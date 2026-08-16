"""pica-search — Hermes plugin for reading web pages via our crawl4ai.

WHY THIS EXISTS, given crawl4ai already speaks MCP.

Wiring crawl4ai's MCP server straight into an agent works and needs no code —
that is what the fleet did first (2026-08-16). Two things went wrong with it:

1. On a real fleet config the model never reached for those tools. Granted the
   full `web` toolset, it tried `web_extract` (permanently broken here — no
   extract backend, and SearXNG is search-only), then shelled out to
   `terminal` + curl. `mcp__crawl4ai__md` was registered and available the
   whole time. On a deliberately narrow toolset it behaved perfectly, which is
   exactly how the earlier "the raw MCP surface is fine" conclusion was reached
   and why it was wrong.
2. The fix is guidance, and guidance had nowhere fleet-wide to live. Upstream
   MCP tool descriptions are not ours to edit, and neither is the built-in
   `web_search`. SOUL.md works but is one file per agent — nine copies of a
   paragraph, guaranteed to drift as bots come and go.

The plugins repo is the ONE surface every agent already shares: a single git
repo bind-mounted into all of them. Hermes injects a plugin tool's schema
description verbatim into every model call. So the description IS the shared
prompt, and owning these tools is the only way to write it once.

Registering these also means dropping the `mcp_servers.crawl4ai` block — two
ways to read a page is the confusion this is meant to end.

This is a DIRECT plugin: no app of ours sits behind it, so the plugin owns the
HTTP call rather than forwarding to an /api/agent/tools endpoint.

Env (profile .env):
  CRAWL4AI_URL        base URL (default http://crawl4ai:11235 — container name,
                      never the public host: traefik hairpins to 404 inside
                      tfk-net)
  CRAWL4AI_API_TOKEN  bearer token. Load-bearing beyond auth: without it
                      crawl4ai's entrypoint binds loopback only and every call
                      dies as a traefik 502 rather than a 401.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

# hermes loads plugins at PROCESS START — copying this file to an agent host
# changes nothing until that agent restarts. register() logs this so a stale
# copy is visible; see notes/__init__.py for the incident that made this
# convention non-optional.
PLUGIN_VERSION = "2026-08-16.1"

DEFAULT_URL = "http://crawl4ai:11235"

# Caps. The model picks the URLs; it does not get to decide how much of the
# internet arrives in one turn. A page read is already 5-20k tokens.
MAX_PAGES = 10
MAX_LINKS = 200


def _env(name: str, default: str = "") -> str:
    """Profile-scoped credential read. The multiplexed gateway keeps each
    profile's .env in an isolated per-turn secret scope and never mutates
    os.environ — a bare os.environ.get returns another profile's value or
    nothing. get_secret honours the scope; on a single-profile gateway it falls
    through to os.environ, so both modes work."""
    try:
        from agent.secret_scope import get_secret

        val = get_secret(name, "")
    except Exception:
        val = os.environ.get(name, "")
    return val or default


def _post(path: str, payload: dict) -> dict:
    """POST to crawl4ai. Never raises — the agent gets a dict either way."""
    base = _env("CRAWL4AI_URL", DEFAULT_URL).rstrip("/")
    url = base + path
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_env('CRAWL4AI_API_TOKEN')}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        # 401 and 502 mean different things and are easy to confuse here: 401
        # is a wrong token, 502 is usually a MISSING one (crawl4ai then binds
        # loopback and traefik cannot reach it). Name both so neither reads as
        # "the crawler is broken".
        hint = ""
        if e.code == 401:
            hint = " — CRAWL4AI_API_TOKEN is wrong or unset for this profile"
        elif e.code == 502:
            hint = " — crawl4ai is likely bound to loopback because its own CRAWL4AI_API_TOKEN is unset"
        return {"ok": False, "message": f"crawl4ai HTTP {e.code} at {url}{hint}: {body}"}
    except Exception as e:  # noqa: BLE001 — surface it, never crash the turn
        # NAME THE URL. A wrong CRAWL4AI_URL otherwise reads as a broken
        # crawler for hours instead of a one-line env fix.
        return {"ok": False, "message": f"crawl4ai unreachable at {url} — check CRAWL4AI_URL: {e}"}


def _read_one(url: str) -> dict:
    """One page -> markdown. `fit` is the cleaned-up filter and the only one
    worth using here: `raw` is the whole DOM, and `llm` is silently broken on
    this deployment (no LLM key configured — it returns success with an empty
    string, ticket #207) as well as being a metered call to summarise a page
    the agent is about to read anyway."""
    out = _post("/md", {"url": url, "f": "fit"})
    if out.get("ok") is False:
        return {"url": url, "ok": False, "message": out["message"]}
    md = out.get("markdown")
    if not md or not md.strip():
        return {
            "url": url,
            "ok": False,
            "message": "crawl4ai returned empty markdown. The page may be "
                       "JS-gated behind a consent wall or a login.",
        }
    return {"url": url, "ok": True, "markdown": md}


def _tool_read_page(args: dict, session_id: str = None, **kwargs) -> str:
    url = (args or {}).get("url", "").strip()
    if not url:
        return json.dumps({"ok": False, "message": "url is required"})
    return json.dumps(_read_one(url))


def _tool_read_pages(args: dict, session_id: str = None, **kwargs) -> str:
    urls = (args or {}).get("urls") or []
    if isinstance(urls, str):  # models sometimes send a JSON string
        try:
            urls = json.loads(urls)
        except Exception:
            urls = [u.strip() for u in urls.split(",") if u.strip()]
    urls = [u for u in urls if isinstance(u, str) and u.strip()][:MAX_PAGES]
    if not urls:
        return json.dumps({"ok": False, "message": "urls must be a non-empty list"})
    results = [_read_one(u) for u in urls]
    return json.dumps({
        "ok": True,
        "requested": len(urls),
        "succeeded": sum(1 for r in results if r.get("ok")),
        "results": results,
    })


def _tool_list_urls(args: dict, session_id: str = None, **kwargs) -> str:
    url = (args or {}).get("url", "").strip()
    if not url:
        return json.dumps({"ok": False, "message": "url is required"})

    out = _post("/crawl", {"urls": [url], "crawler_config": {"cache_mode": "BYPASS"}})
    if out.get("ok") is False:
        return json.dumps(out)

    results = out.get("results") or []
    if not results:
        return json.dumps({"ok": False, "url": url, "message": "crawl4ai returned no result for that URL"})

    links = (results[0].get("links") or {})
    seen, internal = set(), []
    for item in links.get("internal") or []:
        href = (item or {}).get("href")
        if href and href not in seen:
            seen.add(href)
            internal.append({"url": href, "text": (item.get("text") or "").strip()[:120]})
    external = []
    for item in links.get("external") or []:
        href = (item or {}).get("href")
        if href and href not in seen:
            seen.add(href)
            external.append(href)

    return json.dumps({
        "ok": True,
        "url": url,
        "internal": internal[:MAX_LINKS],
        "external": external[:MAX_LINKS],
        "truncated": len(internal) > MAX_LINKS or len(external) > MAX_LINKS,
    })


# ─── Tool descriptions ───────────────────────────────────────────────────────
#
# These reach every agent in the fleet, verbatim, on every call. They are the
# whole reason this plugin exists — write them as instructions, not blurbs.

_READ_PAGE_DESC = (
    "Fetch a web page and return it as clean markdown. THIS IS THE TOOL FOR "
    "READING A URL — use it whenever you need the contents of a page. "
    "Do NOT use web_extract: this fleet configures no extract backend, so it "
    "always fails with 'SearXNG is a search-only backend'. Do NOT fall back to "
    "terminal/curl to fetch pages. "
    "Note that web_search (which is our self-hosted SearXNG) FINDS urls; this "
    "reads them. The two are a pair."
)

_READ_PAGES_DESC = (
    f"Fetch several web pages at once, returning clean markdown for each. Same "
    f"tool as pica_search_read_page, batched — prefer it over calling that one "
    f"repeatedly. Hard cap of {MAX_PAGES} urls per call; anything beyond is "
    "dropped. Each result carries its own ok flag, so a single dead URL does "
    "not lose you the rest. Remember each page costs real context — read what "
    "you need, not everything you can see."
)

_LIST_URLS_DESC = (
    "List the links on a page, split into internal (same site) and external. "
    "Use this BEFORE reading when you do not already know the right URL — it "
    "is far cheaper than fetching pages to discover them, and it stops you "
    "guessing URLs that do not exist. Follow up with pica_search_read_pages on "
    "the handful that look right. This reads ONE page's links; it does not "
    "crawl a whole site."
)

TOOLS = [
    ("pica_search_read_page", _READ_PAGE_DESC,
     {"type": "object",
      "properties": {"url": {"type": "string", "description": "Absolute URL of the page to read"}},
      "required": ["url"]},
     _tool_read_page),
    ("pica_search_read_pages", _READ_PAGES_DESC,
     {"type": "object",
      "properties": {"urls": {"type": "array", "items": {"type": "string"},
                              "description": f"Absolute URLs, max {MAX_PAGES}"}},
      "required": ["urls"]},
     _tool_read_pages),
    ("pica_search_list_urls", _LIST_URLS_DESC,
     {"type": "object",
      "properties": {"url": {"type": "string", "description": "Absolute URL of the page whose links you want"}},
      "required": ["url"]},
     _tool_list_urls),
]


def _fn_schema(name: str, description: str, params: dict) -> dict:
    """hermes registers `schema` VERBATIM as the OpenAI `function` object, so
    name and description must live INSIDE it and the argument schema must sit
    under `parameters`. Registering a bare {"type":"object","properties":...}
    leaves `function.parameters` absent; the schema sanitizer then substitutes
    an empty {"type":"object","properties":{}} and the model sees a tool with
    no arguments and no description. See _template/tool_schema.py."""
    return {"name": name, "description": description, "parameters": params}


def register(ctx) -> None:
    for name, description, schema, handler in TOOLS:
        ctx.register_tool(
            name=name,
            toolset="pica_search",
            schema=_fn_schema(name, description, schema),
            handler=handler,
            description=description,
        )
    print(
        f"[pica-search] registered {len(TOOLS)} tools (v{PLUGIN_VERSION}) -> "
        f"{_env('CRAWL4AI_URL', DEFAULT_URL)} "
        f"{'with token' if _env('CRAWL4AI_API_TOKEN') else 'WITHOUT TOKEN — calls will 401'}",
        flush=True,
    )
