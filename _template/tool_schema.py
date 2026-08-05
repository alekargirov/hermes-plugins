"""The shape hermes expects from `ctx.register_tool(schema=...)`.

NOT a plugin — the leading underscore keeps it out of hermes' plugin scan.
Each plugin carries its own copy of `_fn_schema`, because hermes loads every
plugin directory independently and there is no shared import path between them.

WHAT WENT WRONG (2026-08-05, cost alek a testing session)
---------------------------------------------------------
Every plugin in this repo registered the bare JSON Schema:

    schema={"type": "object", "properties": {...}, "required": [...]}

That is NOT what hermes wants. `registry.get_definitions` emits the registered
schema **verbatim** as the OpenAI `function` object:

    {"type": "function", "function": {**entry.schema, "name": entry.name}}

so the bare form produced a `function` with no `parameters` and no
`description`. `tools/schema_sanitizer.sanitize_tool_schemas`, which runs on
EVERY outgoing request, then hit its missing-parameters branch:

    params = fn.get("parameters")
    if not isinstance(params, dict):
        fn["parameters"] = {"type": "object", "properties": {}}

and the model received:

    {"type": "function", "function": {..., "name": "tickets_create",
                                      "parameters": {"type": "object",
                                                     "properties": {}}}}

An argument-less, description-less tool. The `description=` kwarg passed to
`register_tool` is stored on the registry entry and used for tool_search
indexing, but it never reaches the model's tool definitions — only what is
INSIDE `schema` does.

Symptoms this produced, none of which pointed at the schema:
  * an agent reporting "all 9 tool schemas are empty — properties: {}"
  * tools invoked with no arguments, then failing on the app's own validation
  * the model guessing argument names from the tool name, sometimes correctly,
    which is why casual testing appeared to work
  * `model_tools.coerce_tool_args` silently skipping every plugin tool, since
    it reads `schema["parameters"]["properties"]` — so "42" was never coerced
    to 42 for any plugin

The bundled google_meet plugin (/opt/hermes/plugins/google_meet/tools.py) has
had the correct shape all along; nothing in the plugin API docs says so.

THE CONTRACT
------------
`schema` IS the function object. Name and description go inside it, and the
JSON Schema for the arguments goes under `parameters`. Keep passing
`description=` as well — tool_search uses it.

Guarded by tests/test_schema_shape.py, which loads every plugin in the repo and
asserts the shape for every registered tool. Do not delete that test.
"""

from __future__ import annotations


def fn_schema(name: str, description: str, params: dict) -> dict:
    """Wrap a bare JSON Schema into the function object hermes registers."""
    return {"name": name, "description": description, "parameters": params}
