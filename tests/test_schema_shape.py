"""Every registered tool must reach the model with its arguments intact.

This is the regression guard for the 2026-08-05 defect: every plugin in this
repo registered a bare JSON Schema, hermes emits `schema` verbatim as the
OpenAI `function` object, and the schema sanitizer then replaced the absent
`parameters` with an empty one. The model saw argument-less, description-less
tools — for all 139 of them, bridges included.

`test_survives_hermes_pipeline` is the important one: it reproduces hermes'
own two steps rather than trusting a shape assertion. See
_template/tool_schema.py for the full account.
"""
import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

PLUGIN_DIRS = sorted(
    p.parent for p in ROOT.glob("*/plugin.yaml") if not p.parent.name.startswith("_")
)


class FakeCtx:
    def __init__(self):
        self.registered = []

    def register_tool(self, name, toolset, schema, handler, description, **kw):
        self.registered.append(
            {"name": name, "toolset": toolset, "schema": schema,
             "handler": handler, "description": description}
        )


def _load(d: pathlib.Path):
    """Import a plugin by path — app-bridge has a hyphen in its name and
    cannot be imported by name at all.

    `submodule_search_locations` and `__path__` make the directory a PACKAGE,
    so a plugin split across several files can import its own siblings. This
    mirrors what hermes' real loader does (hermes_cli/plugins.py: it passes the
    same argument and sets the same attribute). Without them this helper could
    only ever load single-file plugins — a weaker mirror of hermes than the
    docstring above claims, and both `media` and `app-bridge`, which are
    packages, would fail to import here for a reason hermes would never hit.
    """
    mod_name = "_shape_" + d.name.replace("-", "_")
    spec = importlib.util.spec_from_file_location(
        mod_name, d / "__init__.py", submodule_search_locations=[str(d)]
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__path__ = [str(d)]
    mod.__package__ = mod_name
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _registered(d: pathlib.Path):
    ctx = FakeCtx()
    _load(d).register(ctx)
    assert ctx.registered, f"{d.name} registered no tools"
    return ctx.registered


def test_every_plugin_is_discovered():
    """A plugin dropped in without a plugin.yaml is invisible to hermes AND to
    this test — fail loudly if the count drifts from what the repo ships.

    15 -> 9 on 2026-08-15, in two merges: radarr, sonarr, lidarr, plex, nzb and
    tmdb became one `media` plugin, and vita3-bridge plus fin3-bridge became
    one `app-bridge`. Eight directories left, two arrived.

    9 -> 10 on 2026-08-16: `pica-search` wraps crawl4ai so the fleet's page
    reading has tool descriptions we own. See that plugin's module docstring.
    """
    assert len(PLUGIN_DIRS) == 10, [d.name for d in PLUGIN_DIRS]


@pytest.mark.parametrize("d", PLUGIN_DIRS, ids=lambda d: d.name)
def test_schema_is_a_function_object(d):
    for tool in _registered(d):
        s = tool["schema"]
        name = tool["name"]
        assert s.get("name") == name, f"{name}: schema.name missing or wrong"
        assert s.get("description"), f"{name}: no description inside the schema"
        params = s.get("parameters")
        assert isinstance(params, dict), f"{name}: no parameters object"
        assert params.get("type") == "object", f"{name}: parameters.type"
        assert isinstance(params.get("properties"), dict), f"{name}: properties"
        # The bare form leaked `properties` to the top level. If that key is
        # here, someone has re-introduced the original bug.
        assert "properties" not in s, f"{name}: bare JSON Schema registered"


@pytest.mark.parametrize("d", PLUGIN_DIRS, ids=lambda d: d.name)
def test_survives_hermes_pipeline(d):
    """Reproduce what hermes actually does to a registered schema.

    Step 1, tools/registry.get_definitions:
        {"type": "function", "function": {**entry.schema, "name": entry.name}}
    Step 2, tools/schema_sanitizer.sanitize_tool_schemas, on every request:
        params = fn.get("parameters")
        if not isinstance(params, dict):
            fn["parameters"] = {"type": "object", "properties": {}}

    Under the old shape, step 2 fired for every tool and wiped the arguments.
    """
    for tool in _registered(d):
        declared = tool["schema"]["parameters"].get("properties", {})

        fn = {**tool["schema"], "name": tool["name"]}
        params = fn.get("parameters")
        if not isinstance(params, dict):
            fn["parameters"] = {"type": "object", "properties": {}}

        assert fn["parameters"]["properties"] == declared, (
            f"{tool['name']}: arguments did not survive — the model would see "
            f"{fn['parameters']['properties']!r} instead of {declared!r}"
        )
        assert fn.get("description"), f"{tool['name']}: description lost"


@pytest.mark.parametrize("d", PLUGIN_DIRS, ids=lambda d: d.name)
def test_argument_coercion_can_find_the_schema(d):
    """model_tools.coerce_tool_args reads schema["parameters"]["properties"] and
    returns args untouched when it finds nothing. Under the old shape it found
    nothing for every plugin tool, so "42" was never coerced to 42 and every
    numeric argument reached the app as a string."""
    for tool in _registered(d):
        props = (tool["schema"].get("parameters") or {}).get("properties")
        assert props is not None, f"{tool['name']}: coercion would be skipped"


@pytest.mark.parametrize("d", PLUGIN_DIRS, ids=lambda d: d.name)
def test_tool_names_are_namespaced_by_their_toolset(d):
    """Tool names are GLOBAL in hermes, not scoped to a toolset, and the
    registry refuses a duplicate outright — whichever registration loses
    depends on import order. The minimax plugin shipped the gate's names
    verbatim, so its `web_search` collided with hermes' built-in one and one of
    the two was silently dropped. Prefixing every tool with its toolset is what
    stops that happening again."""
    for tool in _registered(d):
        assert tool["name"].startswith(tool["toolset"] + "_"), (
            f"{tool['name']} is not namespaced by its toolset "
            f"{tool['toolset']!r} — it can collide with a hermes built-in"
        )


@pytest.mark.parametrize("d", PLUGIN_DIRS, ids=lambda d: d.name)
def test_description_kwarg_still_passed(d):
    """tool_search indexes the registry entry's own description, which is a
    separate kwarg from the one inside the schema. Both must be set."""
    for tool in _registered(d):
        assert tool["description"], f"{tool['name']}: description= kwarg empty"
        assert tool["description"] == tool["schema"]["description"]
