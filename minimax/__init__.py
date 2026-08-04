"""minimax — MiniMax web search, image understanding, image gen, music gen.

Four POSTs against api.minimax.io/v1.

- web_search is for current events, prices, anything needing live data.
- understand_image accepts a publicly fetchable URL (some hosts block
  hotlinking, e.g. Wikimedia 403s). Max 20MB, JPEG/PNG/GIF/WebP.
- generate_image returns a temporary URL (~24h expiry — fetch and save).
- generate_music returns a temporary MP3 URL (~24h expiry).

Env (profile .env): MINIMAX_API_KEY.
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


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


_HDR = {"Authorization": "Bearer {env.MINIMAX_API_KEY}"}


TOOLS = [
    (
        "web_search",
        "Search the web using MiniMax's real-time search. Returns organic results with titles, URLs, snippets, and dates. Use for current events, facts, prices, or anything that needs live information.",
        _schema(
            {
                "query": _s(
                    "Search query. Aim for 3-5 keywords. Include dates for time-sensitive topics (e.g. 'MiniMax M3 release 2026')."
                ),
            },
            ["query"],
        ),
        _make_handler({
            "method": "POST",
            "url": "https://api.minimax.io/v1/coding_plan/search",
            "headers": {**_HDR, "MM-API-Source": "Minimax-MCP"},
            "body": '{"q":"{arg.query}"}',
        }),
    ),
    (
        "understand_image",
        "Analyse an image from a URL using MiniMax M3 vision. Describe, extract text, identify objects, or answer questions about image content. The reply may start with a <think>...</think> reasoning block — ignore it and use the text after it. JPEG/PNG/GIF/WebP up to 20MB; the URL must be publicly fetchable (hosts that block hotlinking, e.g. Wikimedia, fail with 'remote returned status 403').",
        _schema(
            {
                "image_url": _s(
                    "HTTPS URL to a JPEG, PNG, GIF, or WebP image (publicly fetchable)."
                ),
                "prompt": _s(
                    "What to do with the image — describe it, extract text, identify objects, answer a question about it, etc."
                ),
            },
            ["image_url", "prompt"],
        ),
        _make_handler({
            "method": "POST",
            "url": "https://api.minimax.io/v1/chat/completions",
            "headers": _HDR,
            "body": '{"model":"MiniMax-M3","messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"{arg.image_url}"}},{"type":"text","text":"{arg.prompt}"}]}],"max_tokens":2048}',
        }),
    ),
    (
        "generate_image",
        "Generate an image from a text prompt using MiniMax image-01. Returns a temporary download URL (expires after ~24h — fetch/save it promptly). Describe subject, style, lighting, and composition in the prompt for best results.",
        _schema(
            {
                "prompt": _s(
                    "Detailed description of the desired image — subject, style, lighting, composition."
                ),
                "aspect_ratio": _s(
                    "Aspect ratio: 1:1 (default), 16:9, 9:16, 4:3, 3:4, 3:2, 2:3, or 21:9."
                ),
            },
            ["prompt"],
        ),
        _make_handler({
            "method": "POST",
            "url": "https://api.minimax.io/v1/image_generation",
            "headers": _HDR,
            "body": '{"model":"image-01","prompt":"{arg.prompt}","aspect_ratio":"{arg.aspect_ratio|1:1}","response_format":"url","n":1}',
        }),
    ),
    (
        "generate_music",
        "Generate a song (vocals + instruments) from a style prompt and lyrics using MiniMax music-2.6. Returns a temporary MP3 URL (expires after ~24h — fetch/save it promptly). Songs run roughly 1-3 minutes.",
        _schema(
            {
                "style": _s(
                    'Style/mood description, comma-separated works well (e.g. "Soulful Blues, Rainy Night, Melancholy, Male Vocals, Slow Tempo").'
                ),
                "lyrics": _s(
                    "Song lyrics, 10-1000 characters. Use newlines between lines and section tags like [Verse], [Chorus], [Bridge] for structure."
                ),
            },
            ["style", "lyrics"],
        ),
        _make_handler({
            "method": "POST",
            "url": "https://api.minimax.io/v1/music_generation",
            "headers": _HDR,
            "body": '{"model":"music-2.6","prompt":"{arg.style}","lyrics":"{arg.lyrics}","audio_setting":{"sample_rate":44100,"bitrate":256000,"format":"mp3"},"output_format":"url"}',
        }),
    ),
]


def register(ctx) -> None:
    for name, description, schema, handler in TOOLS:
        ctx.register_tool(
            name=name,
            toolset="minimax",
            schema=schema,
            handler=handler,
            description=description,
        )
    key = _env("MINIMAX_API_KEY")
    print(
        f"[minimax] registered {len(TOOLS)} tools (key {'set' if key else 'UNSET'})",
        flush=True,
    )