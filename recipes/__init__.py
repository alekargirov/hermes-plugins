"""recipes — Recipes (recipe-srv v2). 26 tools.

Sections: reads, recipe writes, ingredient writes, step writes, tag writes.
Every write returns the resulting object. rawText is authoritative: a write
fills the parsed fields (qty/unit/name) around an ingredient line, never
over it — pass rawText to rewrite the line, pass a specific field to adjust
just that.

Env (profile .env): RECIPES_URL (default http://recipes:3019), USER_ID
(sent for audit, no real auth — single-user LAN app).
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


_BASE = "{env.RECIPES_URL|http://recipes:3019}"
_HDR = {"X-User-Id": "{env.USER_ID}"}


TOOLS = [
    # ── reads ──
    (
        "recipes_list",
        "List recipes (id, slug, title, image). Optionally filter by a tag slug.",
        _schema(
            {
                "tag": _s('Tag or cuisine slug to filter by (e.g. "balkan", "soup"). Omit for all.'),
                "limit": _n("Max recipes (default 500)"),
            }
        ),
        _make_handler({
            "method": "GET",
            "url": f"{_BASE}/api/v2/recipes?tag={{arg.tag}}&limit={{arg.limit}}",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_get",
        "Full recipe by slug — fields, ingredients (with parsed qty/unit/name and the raw line), steps, tags.",
        _schema({"slug": _s("Recipe slug (from recipes_list / recipes_search)")}, ["slug"]),
        _make_handler({
            "method": "GET",
            "url": f"{_BASE}/api/v2/recipes/get?slug={{arg.slug}}",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_search",
        "Full-text search over titles, ingredients AND steps. 'star anise' finds recipes where it is only an ingredient.",
        _schema(
            {
                "q": _s("Search query"),
                "limit": _n("Max results (default 50)"),
            },
            ["q"],
        ),
        _make_handler({
            "method": "GET",
            "url": f"{_BASE}/api/v2/recipes/search?q={{arg.q}}&limit={{arg.limit}}",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_by_ingredients",
        'The fridge query — "what can I make with what I have". Returns recipes that contain EVERY listed ingredient term (AND match over ingredient text).',
        _schema(
            {
                "have": _s(
                    'Comma-separated ingredients you have, e.g. "chicken,ginger,star anise"'
                ),
                "limit": _n("Max results (default 50)"),
            },
            ["have"],
        ),
        _make_handler({
            "method": "GET",
            "url": f"{_BASE}/api/v2/recipes/by-ingredients?have={{arg.have}}&limit={{arg.limit}}",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_unparsed",
        "Ingredients the importer could not fully structure (empty name, or a line that starts with a number but no quantity was captured). The starting point for tidying free-form ingredients into fields. Returns ingredient id + recipe slug/title + the raw line.",
        _schema({"limit": _n("Max rows (default 200)")}),
        _make_handler({
            "method": "GET",
            "url": f"{_BASE}/api/v2/recipes/unparsed?limit={{arg.limit}}",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_raw",
        "The original Paprika JSON payload for a recipe, exactly as imported (nothing lost on import lives here).",
        _schema({"slug": _s("Recipe slug")}, ["slug"]),
        _make_handler({
            "method": "GET",
            "url": f"{_BASE}/api/v2/recipes/raw?slug={{arg.slug}}",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_tags",
        "All tags and cuisines with recipe counts (name, slug, isCuisine, count).",
        _schema({}),
        _make_handler({
            "method": "GET",
            "url": f"{_BASE}/api/v2/tags",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_scale",
        "A recipe's ingredients rewritten for N servings (read-only — nothing is saved). Returns original + scaled lines.",
        _schema(
            {
                "slug": _s("Recipe slug"),
                "servings": _n("Target servings"),
            },
            ["slug", "servings"],
        ),
        _make_handler({
            "method": "GET",
            "url": f"{_BASE}/api/v2/recipes/scale?slug={{arg.slug}}&servings={{arg.servings}}",
            "headers": _HDR,
        }),
    ),
    # ── recipe writes ──
    (
        "recipes_create",
        "Create a new (empty) recipe with a title. Returns the new recipe incl. its slug.",
        _schema({"title": _s("Recipe title")}, ["title"]),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/recipes/create",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_field_set",
        "Set recipe-level fields (only those provided change). Free-text prepText / cookText / servingsText re-derive their parsed numbers automatically.",
        _schema(
            {
                "slug": _s("Recipe slug"),
                "title": _s("New title"),
                "notes": _s("New notes"),
                "sourceName": _s("New source name"),
                "sourceUrl": _s("New source URL"),
                "difficulty": _s("New difficulty"),
                "rating": _n("New rating (0-5)"),
                "nutritionalInfo": _s("New nutritional info"),
                "prepText": _s("New prep text (e.g. '20 minutes')"),
                "cookText": _s("New cook text"),
                "servingsText": _s('New servings text (e.g. "Serves 4 to 6")'),
                "servingsBase": _n("Explicit scaler base, overrides the parse"),
            },
            ["slug"],
        ),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/recipes/field-set",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_delete",
        "Soft-delete a recipe (moves it to trash). Returns the row.",
        _schema({"slug": _s("Recipe slug")}, ["slug"]),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/recipes/delete",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_restore",
        "Restore a soft-deleted recipe from trash.",
        _schema({"slug": _s("Recipe slug")}, ["slug"]),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/recipes/restore",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_upload_image",
        "Download an image from a public URL and set it as the recipe's cover. Returns the updated recipe.",
        _schema(
            {
                "slug": _s("Recipe slug"),
                "imageUrl": _s("Public image URL (jpg/png/gif/webp/avif)"),
            },
            ["slug", "imageUrl"],
        ),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/recipes/upload-image",
            "headers": _HDR,
        }),
    ),
    # ── ingredient writes ──
    (
        "recipes_ingredient_add",
        'Add an ingredient to a recipe from a raw line ("2 tbsp olive oil, warmed"); qty/unit/name/prep are parsed out. Returns the new ingredient.',
        _schema(
            {
                "slug": _s("Recipe slug"),
                "rawText": _s("The ingredient line as written"),
                "groupName": _s('Optional group, e.g. "For the sauce"'),
            },
            ["slug", "rawText"],
        ),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/ingredient/add",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_ingredient_set",
        "Update one ingredient by id. Editing rawText re-derives qty/unit/name/prep; passing an explicit field (qty/unit/name/preparation/groupName/sort) sets just that. rawText is never overwritten except by an explicit rawText edit.",
        _schema(
            {
                "id": _n("Ingredient id (from recipes_get / recipes_unparsed)"),
                "rawText": _s("New raw text (re-derives parsed fields)"),
                "qty": _s("New quantity"),
                "unit": _s("New unit"),
                "name": _s("New name"),
                "preparation": _s("New preparation"),
                "groupName": _s("New group name"),
                "sort": _n("New sort order"),
            },
            ["id"],
        ),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/ingredient/set",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_ingredient_delete",
        "Delete an ingredient by id.",
        _schema({"id": _n("Ingredient id")}, ["id"]),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/ingredient/delete",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_ingredients_set_group",
        'Assign a group name to several ingredients at once (bucket them under "For the sauce" etc.). Returns the updated rows.',
        _schema(
            {
                "ids": {"type": "array", "items": {"type": "number"}, "description": "Ingredient ids"},
                "groupName": _s('Group name to assign (empty string clears it)'),
            },
            ["ids", "groupName"],
        ),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/ingredient/set-group",
            "headers": _HDR,
        }),
    ),
    # ── step writes ──
    (
        "recipes_step_add",
        "Add a method step to a recipe. Returns the new step.",
        _schema(
            {
                "slug": _s("Recipe slug"),
                "body": _s("Step text"),
                "groupName": _s('Optional section, e.g. "For the sauce"'),
            },
            ["slug", "body"],
        ),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/step/add",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_step_set",
        "Update a step by id (body / groupName / sort).",
        _schema(
            {
                "id": _n("Step id"),
                "body": _s("New step text"),
                "groupName": _s("New group name"),
                "sort": _n("New sort order"),
            },
            ["id"],
        ),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/step/set",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_step_delete",
        "Delete a step by id.",
        _schema({"id": _n("Step id")}, ["id"]),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/step/delete",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_steps_reorder",
        "Reorder a recipe's steps. Pass step ids in the new order; sort is renumbered.",
        _schema(
            {
                "slug": _s("Recipe slug"),
                "orderedIds": {"type": "array", "items": {"type": "number"}, "description": "Step ids in the desired order"},
            },
            ["slug", "orderedIds"],
        ),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/step/reorder",
            "headers": _HDR,
        }),
    ),
    # ── tag writes ──
    (
        "recipes_tag_add",
        "Add a tag (or cuisine) to a recipe. Creates the tag if new. Returns the tag.",
        _schema(
            {
                "slug": _s("Recipe slug"),
                "name": _s("Tag name"),
                "isCuisine": _b("Mark this tag as a cuisine (default false)"),
            },
            ["slug", "name"],
        ),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/tag/add",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_tag_remove",
        "Remove a tag from a recipe (by tag id, from recipes_get).",
        _schema(
            {
                "slug": _s("Recipe slug"),
                "tagId": _n("Tag id"),
            },
            ["slug", "tagId"],
        ),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/tag/remove",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_tag_rename",
        "Rename a tag (all recipes carrying it are affected). Identify it by slug.",
        _schema(
            {
                "tagSlug": _s("Slug of the tag to rename"),
                "name": _s("New display name"),
            },
            ["tagSlug", "name"],
        ),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/tag/rename",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_tag_merge",
        'Merge one tag into another — every recipe tagged `source` becomes tagged `target`, then `source` is deleted. Fixes duplicates like "Desert" -> "Dessert".',
        _schema(
            {
                "source": _s("Slug of the tag to merge away"),
                "target": _s("Slug of the tag to keep"),
            },
            ["source", "target"],
        ),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/tag/merge",
            "headers": _HDR,
        }),
    ),
    (
        "recipes_tag_set_cuisine",
        "Flag (or unflag) a tag as a cuisine, controlling whether it appears as a cuisine folder/facet.",
        _schema(
            {
                "tagSlug": _s("Slug of the tag"),
                "isCuisine": _b("true = cuisine, false = ordinary tag"),
            },
            ["tagSlug", "isCuisine"],
        ),
        _make_handler({
            "method": "POST",
            "url": f"{_BASE}/api/v2/tag/set-cuisine",
            "headers": _HDR,
        }),
    ),
]


def register(ctx) -> None:
    for name, description, schema, handler in TOOLS:
        ctx.register_tool(
            name=name,
            toolset="recipes",
            schema=schema,
            handler=handler,
            description=description,
        )
    print(
        f"[recipes] registered {len(TOOLS)} tools -> {_env('RECIPES_URL') or '(RECIPES_URL unset)'} as {_env('USER_ID') or '(USER_ID unset)'}",
        flush=True,
    )