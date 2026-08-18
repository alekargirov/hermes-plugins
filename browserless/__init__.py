"""browserless — Hermes plugin for DRIVING a web page, via our browserless.

WHY THIS EXISTS, given pica-search already reads pages.

crawl4ai (behind pica_search_read_page) fetches: one request in, markdown out.
It cannot log in, dismiss a consent wall, fill a form, or do anything that
takes a second step. Everything in this plugin is about that gap, and nothing
in it should be used for a plain read — two tools that fetch a page is the
confusion ticket #212 was made of.

WHY NOT HERMES' OWN browser_* TOOLSET. Hermes drives browsers by shelling out
to the agent-browser CLI. Measured on dev 2026-08-18 with agent-browser 0.27.0:
`--cdp` fails with HTTP 400 against our browserless AND against a plain Chrome
151 handed its own webSocketDebuggerUrl, while the same binary in local mode
works fine. A hand-rolled curl websocket handshake to both endpoints returns
101, so the endpoints are healthy and agent-browser's CDP client is not. The
HTTP API is therefore the only route in, and it has the side benefit of needing
no browser binary inside the agent images.

THE SCRIPTS RUN UNDER PUPPETEER, NOT PLAYWRIGHT. browserless' /function
endpoint hands the caller a Puppeteer `page`. This is worth stating loudly in
the tool descriptions because a model that assumes Playwright writes
`page.waitForLoadState(...)`, which does not exist there and fails at runtime
with nothing useful to learn from.

This is a DIRECT plugin: no app of ours sits behind it, so the plugin owns the
HTTP call rather than forwarding to an /api/agent/tools endpoint.

Env (profile .env):
  BROWSERLESS_URL    base URL (default http://browserless:3000 — container
                     name, never the public host: traefik hairpins to 404
                     inside tfk-net)
  BROWSERLESS_TOKEN  every browserless route requires ?token=. A missing or
                     wrong one is a 401; a malformed websocket handshake is a
                     400. Different faults, easy to confuse.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

# hermes loads plugins at PROCESS START — copying this file to an agent host
# changes nothing until that agent restarts. register() logs this so a stale
# copy is visible; see pica-search/__init__.py for the same convention.
PLUGIN_VERSION = "2026-08-18.1"

DEFAULT_URL = "http://browserless:3000"

# Caps. The model picks the work; it does not get to decide how much of it
# lands in one turn.
MAX_STEPS = 25
MAX_TEXT = 20000
# browserless kills any session past its own TIMEOUT (60s in our compose).
# Wait a little longer than that so a server-side kill surfaces as its own
# error rather than as a client timeout, which reads like a network fault.
HTTP_TIMEOUT = 90

SHOT_DIR = "/tmp/browserless-shots"


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


def _post(path: str, payload: dict, raw: bool = False):
    """POST to browserless. Never raises — the agent gets a dict either way.

    Returns bytes when raw=True (screenshots), otherwise a parsed dict.
    """
    base = _env("BROWSERLESS_URL", DEFAULT_URL).rstrip("/")
    token = _env("BROWSERLESS_TOKEN")
    url = f"{base}{path}?token={urllib.parse.quote(token)}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read()
            if raw:
                return body
            text = body.decode()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"ok": False, "message": f"browserless returned non-JSON: {text[:300]}"}
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:400]
        # NAME the likely cause. A 401 here is nearly always the profile
        # missing BROWSERLESS_TOKEN, which otherwise reads as "the browser is
        # broken" for as long as it takes someone to check.
        hint = ""
        if e.code == 401:
            hint = " — BROWSERLESS_TOKEN is wrong or unset for this profile"
        elif e.code == 429:
            hint = " — every browser slot is busy; retry in a moment"
        return {"ok": False, "message": f"browserless HTTP {e.code}{hint}: {body}"}
    except Exception as e:  # noqa: BLE001 — surface it, never crash the turn
        # NAME THE URL. A wrong BROWSERLESS_URL otherwise reads as a broken
        # browser for hours instead of a one-line env fix.
        return {"ok": False, "message": f"browserless unreachable at {base} — check BROWSERLESS_URL: {e}"}


# ─── steps -> puppeteer ──────────────────────────────────────────────────────
#
# The declarative step list exists so the common flows — open a page, accept a
# banner, type into two fields, submit — need no JavaScript at all. Anything
# this cannot express is what browserless_script is for.

_STEP_JS = {
    "goto": "await page.goto({arg}, {{ waitUntil: 'domcontentloaded' }});",
    "click": "await page.click({arg});",
    "click_wait": (
        "await Promise.all(["
        "page.waitForNavigation({{ waitUntil: 'domcontentloaded' }}), "
        "page.click({arg})"
        "]);"
    ),
    "type": "await page.type({sel}, {val});",
    "press": "await page.keyboard.press({arg});",
    "wait_for": "await page.waitForSelector({arg}, {{ timeout: 15000 }});",
    "wait_ms": "await new Promise(r => setTimeout(r, Math.min({arg}, 15000)));",
    "scroll_bottom": "await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));",
}


def _js(value) -> str:
    """JSON is a valid JavaScript literal, and json.dumps is the only escaping
    that can be trusted with a selector containing quotes or a password
    containing a backslash. Never build these by concatenation."""
    return json.dumps(value)


def _build_script(steps: list) -> tuple:
    """Return (js_source, error). Validates every step before emitting."""
    lines = []
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            return None, f"step {i} is not an object"
        action = (step.get("action") or "").strip()
        if action not in _STEP_JS:
            return None, (
                f"step {i}: unknown action {action!r}. "
                f"Valid actions: {', '.join(sorted(_STEP_JS))}"
            )
        if action == "type":
            sel, val = step.get("selector"), step.get("value")
            if not sel or val is None:
                return None, f"step {i}: type needs both selector and value"
            lines.append(_STEP_JS[action].format(sel=_js(sel), val=_js(str(val))))
        elif action == "scroll_bottom":
            lines.append(_STEP_JS[action])
        elif action == "wait_ms":
            try:
                ms = int(step.get("value") or step.get("selector") or 0)
            except (TypeError, ValueError):
                return None, f"step {i}: wait_ms needs a number in value"
            lines.append(_STEP_JS[action].format(arg=ms))
        else:
            arg = step.get("selector") or step.get("value") or step.get("url")
            if not arg:
                return None, f"step {i}: {action} needs a selector (or url for goto)"
            lines.append(_STEP_JS[action].format(arg=_js(str(arg))))

    body = "\n  ".join(lines)
    return (
        "export default async function ({ page }) {\n"
        "  " + body + "\n"
        "  const text = await page.evaluate(() => document.body ? document.body.innerText : '');\n"
        "  return { data: { url: page.url(), title: await page.title(), text: text.slice(0, "
        + str(MAX_TEXT)
        + ") }, type: 'application/json' };\n"
        "}\n"
    ), None


def _tool_actions(args: dict, session_id: str = None, **kwargs) -> str:
    args = args or {}
    steps = args.get("steps") or []
    if isinstance(steps, str):  # models sometimes send a JSON string
        try:
            steps = json.loads(steps)
        except Exception:
            return json.dumps({"ok": False, "message": "steps must be a list of step objects"})
    if not isinstance(steps, list) or not steps:
        return json.dumps({"ok": False, "message": "steps must be a non-empty list"})
    if len(steps) > MAX_STEPS:
        return json.dumps({"ok": False, "message": f"too many steps (max {MAX_STEPS})"})

    # `url` is a convenience: it saves the model writing a goto step every time,
    # which it forgets to do often enough to matter.
    url = (args.get("url") or "").strip()
    if url:
        steps = [{"action": "goto", "url": url}] + list(steps)

    script, err = _build_script(steps)
    if err:
        return json.dumps({"ok": False, "message": err})

    out = _post("/function", {"code": script, "context": {}})
    if out.get("ok") is False:
        return json.dumps(out)
    if "error" in out:
        # A script error is the agent's fault, not the browser's — hand back the
        # message so the next attempt can fix the selector.
        return json.dumps({"ok": False, "message": f"script failed: {out['error']}"})

    data = out.get("data") or {}
    return json.dumps({
        "ok": True,
        "url": data.get("url"),
        "title": data.get("title"),
        "text": data.get("text", ""),
        "truncated": len(data.get("text", "")) >= MAX_TEXT,
    })


def _tool_script(args: dict, session_id: str = None, **kwargs) -> str:
    code = (args or {}).get("code", "")
    if not code or not code.strip():
        return json.dumps({"ok": False, "message": "code is required"})
    if "export default" not in code:
        return json.dumps({
            "ok": False,
            "message": "code must be an ES module: export default async function ({ page }) { ... }",
        })

    context = (args or {}).get("context") or {}
    if isinstance(context, str):
        try:
            context = json.loads(context)
        except Exception:
            context = {}

    out = _post("/function", {"code": code, "context": context})
    if out.get("ok") is False:
        return json.dumps(out)
    if "error" in out:
        return json.dumps({"ok": False, "message": f"script failed: {out['error']}"})
    return json.dumps({"ok": True, "data": out.get("data")})


def _tool_screenshot(args: dict, session_id: str = None, **kwargs) -> str:
    args = args or {}
    url = (args.get("url") or "").strip()
    if not url:
        return json.dumps({"ok": False, "message": "url is required"})

    options = {"type": "png", "fullPage": bool(args.get("full_page"))}
    selector = (args.get("selector") or "").strip()
    payload = {"url": url, "options": options}
    if selector:
        # Element shots ignore fullPage; browserless rejects the pair.
        payload["selector"] = selector
        options.pop("fullPage", None)

    body = _post("/screenshot", payload, raw=True)
    if isinstance(body, dict):  # error path
        return json.dumps(body)

    try:
        os.makedirs(SHOT_DIR, exist_ok=True)
        path = os.path.join(SHOT_DIR, f"shot-{int(time.time() * 1000)}.png")
        with open(path, "wb") as fh:
            fh.write(body)
    except Exception as e:  # noqa: BLE001
        return json.dumps({"ok": False, "message": f"could not save screenshot: {e}"})

    return json.dumps({"ok": True, "path": path, "bytes": len(body), "url": url})


# ─── Tool descriptions ───────────────────────────────────────────────────────
#
# These reach every agent in the fleet, verbatim, on every call. They are the
# whole reason this plugin exists — write them as instructions, not blurbs.
#
# Say what to do, never quote an error string the model has not seen. A tool
# description that quotes a verbatim failure gives a model something to
# "remember" experiencing; ticket #212 was exactly that, filed against a tool
# the agent never called.

_ACTIONS_DESC = (
    "Drive a web page through a sequence of steps and return the page it ends "
    "on. USE THIS WHEN READING IS NOT ENOUGH — a login, a cookie or consent "
    "wall, a search box, a form, a 'load more' button, anything needing a "
    "second step. For simply reading a URL use pica_search_read_page instead; "
    "it is cheaper and this tool has no advantage there. "
    "Steps are objects with an `action`: goto (url), click (selector), "
    "click_wait (selector — use when the click navigates), type (selector + "
    "value), press (key name), wait_for (selector), wait_ms (value), "
    "scroll_bottom. Selectors are CSS. Pass `url` to open a page first without "
    "writing a goto step. You get back the final url, title and visible text."
)

_SCRIPT_DESC = (
    "Run a Puppeteer script against a real browser and return whatever it "
    "returns. This is the escape hatch for flows browserless_actions cannot "
    "express — reading a value mid-flow, conditional branching, iterating over "
    "elements. Reach for browserless_actions first; it needs no code and fails "
    "in ways you can read. "
    "IT IS PUPPETEER, NOT PLAYWRIGHT: page.waitForNavigation and page.$eval "
    "exist, page.waitForLoadState and page.locator do not. "
    "Shape: export default async function ({ page, context }) { ... return "
    "{ data: <json>, type: 'application/json' }; } — `context` is whatever you "
    "pass in the context argument, which is where credentials and URLs belong "
    "rather than baked into the code string."
)

_SCREENSHOT_DESC = (
    "Screenshot a page and save it to a file on this machine, returning the "
    "path. Use it when the QUESTION IS VISUAL — what a page looks like, "
    "whether a layout is broken, showing someone a rendering — or to attach "
    "the image to a reply. Do NOT use it to read a page's contents: you get a "
    "file path back, not the text, and pica_search_read_page answers that "
    "better. full_page captures past the fold; selector captures one element."
)

TOOLS = [
    ("browserless_actions", _ACTIONS_DESC,
     {"type": "object",
      "properties": {
          "url": {"type": "string",
                  "description": "Absolute URL to open before the steps run (optional)"},
          "steps": {"type": "array", "items": {"type": "object"},
                    "description": f"Ordered steps, max {MAX_STEPS}. Each is "
                                   "{action, selector?, value?, url?}"},
      },
      "required": ["steps"]},
     _tool_actions),
    ("browserless_script", _SCRIPT_DESC,
     {"type": "object",
      "properties": {
          "code": {"type": "string",
                   "description": "ES module exporting an async default function ({ page, context })"},
          "context": {"type": "object",
                      "description": "Values passed to the script as `context` (optional)"},
      },
      "required": ["code"]},
     _tool_script),
    ("browserless_screenshot", _SCREENSHOT_DESC,
     {"type": "object",
      "properties": {
          "url": {"type": "string", "description": "Absolute URL to capture"},
          "full_page": {"type": "boolean",
                        "description": "Capture the whole scrollable page, not just the viewport"},
          "selector": {"type": "string",
                       "description": "CSS selector to capture one element instead of the page"},
      },
      "required": ["url"]},
     _tool_screenshot),
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
            toolset="browserless",
            schema=_fn_schema(name, description, schema),
            handler=handler,
            description=description,
        )
    print(
        f"[browserless] registered {len(TOOLS)} tools (v{PLUGIN_VERSION}) -> "
        f"{_env('BROWSERLESS_URL', DEFAULT_URL)} "
        f"{'with token' if _env('BROWSERLESS_TOKEN') else 'WITHOUT TOKEN — calls will 401'}",
        flush=True,
    )
