"""minimax — Hermes plugin for MiniMax (web search, image understanding, image
and music generation).

A DIRECT plugin against a paid third-party API. The base URL is literal and the
key travels as `Authorization: Bearer`.

Body arguments are JSON-ESCAPED before substitution. The bodies here are string
templates with the model's text dropped into them, so a prompt containing a
quote or a newline would otherwise produce invalid JSON and a 400 the model
cannot make sense of. mcp-srv learned this the same way (92a1b28).

Single-tenant: one account, no user scoping.

Env (profile .env):
  MINIMAX_API_KEY  a MiniMax API key

Tool descriptions and bodies port VERBATIM from srv-mcp-yaml/minimax.yaml.
"""


from __future__ import annotations

import datetime as _dt
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import NamedTuple, Optional

PLUGIN_VERSION = "2026-08-05.4"

_NOW = re.compile(r"\{now([^}]*)\}")
_TOKEN = re.compile(r"\{(env|arg)([^}]*)\}")
_NOW_SHIFT = re.compile(r"^([+-])(\d+)d$")


class Tool(NamedTuple):
    name: str
    description: str
    schema: dict
    method: str
    url: str
    body: Optional[str] = None
    select: Optional[list] = None
    limit: Optional[int] = None
    # Seconds to wait for a response. 60 suits search, vision and images, all
    # of which answer in a few seconds. Music generation does NOT: MiniMax
    # composes the whole track before replying, and a full set of lyrics blew
    # straight through 60s while three short lines squeaked under it — so the
    # tool looked like it worked until someone wrote a real song.
    timeout: int = 60


def _env(name: str, default: str = "") -> str:
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


def _render(template: str, args: dict, *, quote: bool, json_escape: bool = False) -> str:
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
        val = str(val)
        if quote:
            return urllib.parse.quote(val, safe="")
        if json_escape:
            # These bodies are STRING templates with the model's text dropped
            # in. A prompt containing a quote or a newline would otherwise
            # produce invalid JSON and a 400 the model cannot act on.
            return json.dumps(val)[1:-1]
        return val

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


def _is_timeout(e: Exception) -> bool:
    """urllib surfaces a read timeout as a bare TimeoutError, and a connect
    timeout wrapped in URLError.reason. Both mean 'we gave up waiting', and
    neither means the credential is wrong."""
    if isinstance(e, TimeoutError):
        return True
    return isinstance(getattr(e, "reason", None), TimeoutError)


def _call(tool: Tool, args: dict) -> str:
    if not _env("MINIMAX_API_KEY"):
        return json.dumps(
            {"ok": False, "message": "MINIMAX_API_KEY is not set for this profile"}
        )
    url = _render(tool.url, args, quote=True)
    headers = {"Authorization": "Bearer " + _env("MINIMAX_API_KEY"), "MM-API-Source": "Minimax-MCP", "Content-Type": "application/json"}

    data = None
    if tool.body is not None:
        headers["Content-Type"] = "application/json"
        data = _render(tool.body, args, quote=False, json_escape=True).encode()
    elif tool.method in ("POST", "PUT"):
        headers["Content-Type"] = "application/json"
        data = json.dumps(args or {}).encode()

    req = urllib.request.Request(url, data=data, headers=headers, method=tool.method)
    try:
        with urllib.request.urlopen(req, timeout=tool.timeout) as resp:
            return _shape(resp.read().decode(), tool.select, tool.limit)
    except urllib.error.HTTPError as e:
        return json.dumps(
            {"ok": False, "message": f"minimax HTTP {e.code}: {e.read().decode()[:300]}"}
        )
    except Exception as e:  # noqa: BLE001 — surface it, never crash the turn
        # A timeout is NOT an auth problem, and this used to say "check
        # MINIMAX_API_KEY" for every failure — so a music generation that ran
        # long told the operator to go and rotate a perfectly good key. Say
        # which of the two actually happened.
        if _is_timeout(e):
            return json.dumps(
                {
                    "ok": False,
                    "message": f"minimax timed out after {tool.timeout}s — the request may "
                               f"still be generating on their side. This is not an auth "
                               f"problem; the key was accepted.",
                }
            )
        return json.dumps(
            {"ok": False, "message": f"minimax unreachable at {url}: {e}"}
        )


def _make_handler(tool: Tool):
    def _handler(args: dict, session_id: str = None, **kwargs) -> str:
        return _call(tool, args)

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


TOOLS = [
    Tool(
        # NOT `web_search`, which is what the MCP gate called it. Inside hermes
        # that name is already taken by the built-in `web` toolset, and the
        # registry REFUSES the second registration — so whichever loaded second
        # was silently dropped, and which one that was depended on import
        # order. Renaming leaves both reachable.
        "minimax_web_search",
        "Search the web using MiniMax's real-time search. Returns organic results with titles, URLs, snippets, and dates. Use for current events, facts, prices, or anything that needs live information.",
        _schema(
            {
                "query": _s("Search query. Aim for 3–5 keywords. Include dates for time-sensitive topics (e.g. \"MiniMax M3 release 2026\")."),
            },
            ["query"],
        ),
        "POST",
        "https://api.minimax.io/v1/coding_plan/search",
        body="{\"q\":\"{arg.query}\"}",
        select=None,
        limit=None,
    ),
    Tool(
        "minimax_understand_image",
        "Analyse an image from a URL using MiniMax M3 vision. Describe, extract text, identify objects, or answer questions about image content. The reply may start with a <think>…</think> reasoning block — ignore it and use the text after it. JPEG/PNG/GIF/WebP up to 20MB; the URL must be publicly fetchable (hosts that block hotlinking, e.g. Wikimedia, fail with \"remote returned status 403\").",
        _schema(
            {
                "image_url": _s("HTTPS URL to a JPEG, PNG, GIF, or WebP image (publicly fetchable)."),
                "prompt": _s("What to do with the image — describe it, extract text, identify objects, answer a question about it, etc."),
            },
            ["image_url", "prompt"],
        ),
        "POST",
        "https://api.minimax.io/v1/chat/completions",
        body="{\"model\":\"MiniMax-M3\",\"messages\":[{\"role\":\"user\",\"content\":[{\"type\":\"image_url\",\"image_url\":{\"url\":\"{arg.image_url}\"}},{\"type\":\"text\",\"text\":\"{arg.prompt}\"}]}],\"max_tokens\":2048}",
        select=None,
        limit=None,
    ),
    Tool(
        "minimax_generate_image",
        "Generate an image from a text prompt using MiniMax image-01. Returns a temporary download URL (expires after ~24h — fetch/save it promptly). Describe subject, style, lighting, and composition in the prompt for best results.",
        _schema(
            {
                "prompt": _s("Detailed description of the desired image — subject, style, lighting, composition."),
                "aspect_ratio": _s("Aspect ratio: 1:1 (default), 16:9, 9:16, 4:3, 3:4, 3:2, 2:3, or 21:9."),
            },
            ["prompt"],
        ),
        "POST",
        "https://api.minimax.io/v1/image_generation",
        body="{\"model\":\"image-01\",\"prompt\":\"{arg.prompt}\",\"aspect_ratio\":\"{arg.aspect_ratio|1:1}\",\"response_format\":\"url\",\"n\":1}",
        select=None,
        limit=None,
    ),
    Tool(
        "minimax_generate_music",
        "Generate a song (vocals + instruments) from a style prompt and lyrics using MiniMax music-2.6. Returns a temporary MP3 URL (expires after ~24h — fetch/save it promptly). The finished songs run roughly 1–3 minutes, and MiniMax composes the whole track before replying, so a full set of lyrics can take a couple of minutes to come back. Expect to wait.",
        _schema(
            {
                "style": _s("Style/mood description, comma-separated works well (e.g. \"Soulful Blues, Rainy Night, Melancholy, Male Vocals, Slow Tempo\")."),
                "lyrics": _s("Song lyrics, 10–1000 characters. Use newlines between lines and section tags like [Verse], [Chorus], [Bridge] for structure."),
            },
            ["style", "lyrics"],
        ),
        "POST",
        "https://api.minimax.io/v1/music_generation",
        body="{\"model\":\"music-2.6\",\"prompt\":\"{arg.style}\",\"lyrics\":\"{arg.lyrics}\",\"audio_setting\":{\"sample_rate\":44100,\"bitrate\":256000,\"format\":\"mp3\"},\"output_format\":\"url\"}",
        select=None,
        limit=None,
        timeout=300,
    ),
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
    for tool in TOOLS:
        ctx.register_tool(
            name=tool.name,
            toolset="minimax",
            schema=_fn_schema(tool.name, tool.description, tool.schema),
            handler=_make_handler(tool),
            description=tool.description,
        )
    print(
        f"[minimax] registered {len(TOOLS)} tools (v{PLUGIN_VERSION}) -> "
        f"api.minimax.io {'(key set)' if _env('MINIMAX_API_KEY') else '(MINIMAX_API_KEY UNSET)'}",
        flush=True,
    )
