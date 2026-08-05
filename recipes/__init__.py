"""recipes — Hermes plugin for the recipe library (recipe-srv).

Calls recipe-srv's existing /api/v2 REST surface directly. Like notes-srv, and
unlike fin3/vita3, there is no /api/agent/tools endpoint and no reason for one:
recipe-srv is a SINGLE-USER LAN app with no auth at all ("anyone who can reach
the host can edit", per its README). There is no identity to carry, so there is
nothing for a forwarding endpoint to enforce.

The gate sent an X-User-Id header for its own audit line only; the app ignores
it. This plugin does not send one.

Env (profile .env):
  RECIPES_URL  base URL (default http://recipes:3019)

Tool descriptions port VERBATIM from srv-mcp-yaml/recipes.yaml. They are the
agent's only guidance; do not paraphrase them.

rawText is authoritative: a tool fills the parsed fields AROUND an ingredient
line, never over it. That rule lives in the app; the descriptions restate it.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

PLUGIN_VERSION = "2026-08-05.26"

DEFAULT_URL = "http://recipes:3019"


def _env(name: str, default: str = "") -> str:
    """Profile-scoped credential read — see the notes plugin for why a bare
    os.environ.get is wrong under the multiplexed gateway."""
    try:
        from agent.secret_scope import get_secret

        val = get_secret(name, "")
    except Exception:
        val = os.environ.get(name, "")
    return val or default


def _call(method: str, path: str, args: dict, arg_style: str) -> str:
    base = _env("RECIPES_URL", DEFAULT_URL).rstrip("/")
    args = args or {}
    url = base + path
    data = None
    headers = {}

    if arg_style == "query":
        clean = {k: v for k, v in args.items() if v is not None and v != ""}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    else:
        headers["Content-Type"] = "application/json"
        data = json.dumps(args).encode()

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        return json.dumps(
            {"ok": False, "message": f"recipes HTTP {e.code}: {e.read().decode()[:300]}"}
        )
    except Exception as e:  # noqa: BLE001 — surface it to the agent, never crash the turn
        # NAME THE URL. A port-less VITA3_URL cost a night on 2026-08-04
        # because the bridge only said "unreachable: <errno>".
        return json.dumps(
            {"ok": False, "message": f"recipes unreachable at {url} — check RECIPES_URL: {e}"}
        )


def _make_handler(method: str, path: str, arg_style: str):
    def _handler(args: dict, session_id: str = None, **kwargs) -> str:
        return _call(method, path, args, arg_style)

    return _handler


def _s(d):
    return {"type": "string", "description": d}


def _n(d):
    return {"type": "number", "description": d}


def _b(d):
    return {"type": "boolean", "description": d}


# The spec deliberately leaves some field args undescribed — the tool's own
# description carries the guidance and the field name is the whole story.
def _bs():
    return {"type": "string"}


def _bn():
    return {"type": "number"}


def _bb():
    return {"type": "boolean"}


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


TOOLS = [
    (
        "recipes_list",
        "List recipes (id, slug, title, image). Optionally filter by a tag slug.",
        _schema(
            {
                "tag": _s("Tag or cuisine slug to filter by (e.g. \"balkan\", \"soup\"). Omit for all."),
                "limit": _n("Max recipes (default 500)"),
            },
        ),
        "GET",
        "/api/v2/recipes",
        "query",
    ),
    (
        "recipes_get",
        "Full recipe by slug — fields, ingredients (with parsed qty/unit/name and the raw line), steps, tags.",
        _schema(
            {
                "slug": _s("Recipe slug (from recipes_list / recipes_search)"),
            },
            ["slug"],
        ),
        "GET",
        "/api/v2/recipes/get",
        "query",
    ),
    (
        "recipes_search",
        "Full-text search over titles, ingredients AND steps. \"star anise\" finds recipes where it is only an ingredient.",
        _schema(
            {
                "q": _s("Search query"),
                "limit": _n("Max results (default 50)"),
            },
            ["q"],
        ),
        "GET",
        "/api/v2/recipes/search",
        "query",
    ),
    (
        "recipes_by_ingredients",
        "The fridge query — \"what can I make with what I have\". Returns recipes that contain EVERY listed ingredient term (AND match over ingredient text).",
        _schema(
            {
                "have": _s("Comma-separated ingredients you have, e.g. \"chicken,ginger,star anise\""),
                "limit": _n("Max results (default 50)"),
            },
            ["have"],
        ),
        "GET",
        "/api/v2/recipes/by-ingredients",
        "query",
    ),
    (
        "recipes_unparsed",
        "Ingredients the importer could not fully structure (empty name, or a line that starts with a number but no quantity was captured). The starting point for tidying free-form ingredients into fields. Returns ingredient id + recipe slug/title + the raw line.",
        _schema(
            {
                "limit": _n("Max rows (default 200)"),
            },
        ),
        "GET",
        "/api/v2/recipes/unparsed",
        "query",
    ),
    (
        "recipes_raw",
        "The original Paprika JSON payload for a recipe, exactly as imported (nothing lost on import lives here).",
        _schema(
            {
                "slug": _s("Recipe slug"),
            },
            ["slug"],
        ),
        "GET",
        "/api/v2/recipes/raw",
        "query",
    ),
    (
        "recipes_tags",
        "All tags and cuisines with recipe counts (name, slug, isCuisine, count).",
        _schema({}),
        "GET",
        "/api/v2/tags",
        "query",
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
        "GET",
        "/api/v2/recipes/scale",
        "query",
    ),
    (
        "recipes_create",
        "Create a new (empty) recipe with a title. Returns the new recipe incl. its slug.",
        _schema(
            {
                "title": _s("Recipe title"),
            },
            ["title"],
        ),
        "POST",
        "/api/v2/recipes/create",
        "body",
    ),
    (
        "recipes_field_set",
        "Set recipe-level fields (only those provided change). Free-text prepText / cookText / servingsText re-derive their parsed numbers automatically.",
        _schema(
            {
                "slug": _s("Recipe slug"),
                "title": _bs(),
                "notes": _bs(),
                "sourceName": _bs(),
                "sourceUrl": _bs(),
                "difficulty": _bs(),
                "rating": _bn(),
                "nutritionalInfo": _bs(),
                "prepText": _s("e.g. \"20 minutes\""),
                "cookText": _bs(),
                "servingsText": _s("e.g. \"Serves 4 to 6\""),
                "servingsBase": _n("Explicit scaler base, overrides the parse"),
            },
            ["slug"],
        ),
        "POST",
        "/api/v2/recipes/field-set",
        "body",
    ),
    (
        "recipes_delete",
        "Soft-delete a recipe (moves it to trash). Returns the row.",
        _schema(
            {
                "slug": _s("Recipe slug"),
            },
            ["slug"],
        ),
        "POST",
        "/api/v2/recipes/delete",
        "body",
    ),
    (
        "recipes_restore",
        "Restore a soft-deleted recipe from trash.",
        _schema(
            {
                "slug": _s("Recipe slug"),
            },
            ["slug"],
        ),
        "POST",
        "/api/v2/recipes/restore",
        "body",
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
        "POST",
        "/api/v2/recipes/upload-image",
        "body",
    ),
    (
        "recipes_ingredient_add",
        "Add an ingredient to a recipe from a raw line (\"2 tbsp olive oil, warmed\"); qty/unit/name/prep are parsed out. Returns the new ingredient.",
        _schema(
            {
                "slug": _s("Recipe slug"),
                "rawText": _s("The ingredient line as written"),
                "groupName": _s("Optional group, e.g. \"For the sauce\""),
            },
            ["slug", "rawText"],
        ),
        "POST",
        "/api/v2/ingredient/add",
        "body",
    ),
    (
        "recipes_ingredient_set",
        "Update one ingredient by id. Editing rawText re-derives qty/unit/name/prep; passing an explicit field (qty/unit/name/preparation/groupName/sort) sets just that. rawText is never overwritten except by an explicit rawText edit.",
        _schema(
            {
                "id": _n("Ingredient id (from recipes_get / recipes_unparsed)"),
                "rawText": _bs(),
                "qty": _bs(),
                "unit": _bs(),
                "name": _bs(),
                "preparation": _bs(),
                "groupName": _bs(),
                "sort": _bn(),
            },
            ["id"],
        ),
        "POST",
        "/api/v2/ingredient/set",
        "body",
    ),
    (
        "recipes_ingredient_delete",
        "Delete an ingredient by id.",
        _schema(
            {
                "id": _n("Ingredient id"),
            },
            ["id"],
        ),
        "POST",
        "/api/v2/ingredient/delete",
        "body",
    ),
    (
        "recipes_ingredients_set_group",
        "Assign a group name to several ingredients at once (bucket them under \"For the sauce\" etc.). Returns the updated rows.",
        _schema(
            {
                "ids": _s("Ingredient ids"),
                "groupName": _s("Group name to assign (empty string clears it)"),
            },
            ["ids", "groupName"],
        ),
        "POST",
        "/api/v2/ingredient/set-group",
        "body",
    ),
    (
        "recipes_step_add",
        "Add a method step to a recipe. Returns the new step.",
        _schema(
            {
                "slug": _s("Recipe slug"),
                "body": _s("Step text"),
                "groupName": _s("Optional section, e.g. \"For the sauce\""),
            },
            ["slug", "body"],
        ),
        "POST",
        "/api/v2/step/add",
        "body",
    ),
    (
        "recipes_step_set",
        "Update a step by id (body / groupName / sort).",
        _schema(
            {
                "id": _n("Step id"),
                "body": _bs(),
                "groupName": _bs(),
                "sort": _bn(),
            },
            ["id"],
        ),
        "POST",
        "/api/v2/step/set",
        "body",
    ),
    (
        "recipes_step_delete",
        "Delete a step by id.",
        _schema(
            {
                "id": _n("Step id"),
            },
            ["id"],
        ),
        "POST",
        "/api/v2/step/delete",
        "body",
    ),
    (
        "recipes_steps_reorder",
        "Reorder a recipe's steps. Pass step ids in the new order; sort is renumbered.",
        _schema(
            {
                "slug": _s("Recipe slug"),
                "orderedIds": _s("Step ids in the desired order"),
            },
            ["slug", "orderedIds"],
        ),
        "POST",
        "/api/v2/step/reorder",
        "body",
    ),
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
        "POST",
        "/api/v2/tag/add",
        "body",
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
        "POST",
        "/api/v2/tag/remove",
        "body",
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
        "POST",
        "/api/v2/tag/rename",
        "body",
    ),
    (
        "recipes_tag_merge",
        "Merge one tag into another — every recipe tagged `source` becomes tagged `target`, then `source` is deleted. Fixes duplicates like \"Desert\" -> \"Dessert\".",
        _schema(
            {
                "source": _s("Slug of the tag to merge away"),
                "target": _s("Slug of the tag to keep"),
            },
            ["source", "target"],
        ),
        "POST",
        "/api/v2/tag/merge",
        "body",
    ),
    (
        "recipes_tag_set_cuisine",
        "Flag (or unflag) a tag as a cuisine, controlling whether it appears as a cuisine folder/facet.",
        _schema(
            {
                "tagSlug": _s("Slug of the tag"),
                "isCuisine": _b("true = cuisine"),
            },
            ["tagSlug", "isCuisine"],
        ),
        "POST",
        "/api/v2/tag/set-cuisine",
        "body",
    ),
]


def register(ctx) -> None:
    for name, description, schema, method, path, arg_style in TOOLS:
        ctx.register_tool(
            name=name,
            toolset="recipes",
            schema=schema,
            handler=_make_handler(method, path, arg_style),
            description=description,
        )
    print(
        f"[recipes] registered {len(TOOLS)} tools (v{PLUGIN_VERSION}) -> "
        f"{_env('RECIPES_URL', DEFAULT_URL)}",
        flush=True,
    )
