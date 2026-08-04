"""Generate Hermes plugins from the legacy MCP YAML tool specs.

For each ``*.yaml`` in this directory, creates a plugin under
``~/.hermes/plugins/<name>/`` with:

  plugin.yaml    manifest
  __init__.py    registers every tool on the given PluginContext
  schemas.py     one schema dict per tool (what the LLM sees)
  tools.py       one handler per tool (all delegating to _http.execute)
  _http.py       the template engine (copied verbatim from _build/)

Also rewrites ``{user.id}`` and ``{user.username}`` placeholders to
``{env.USER_ID}`` / ``{env.USER_NAME}`` so the values come from
``~/.hermes/.env`` instead of a runtime user context.

Re-run after editing any YAML.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml


SOURCE_DIR = Path(__file__).resolve().parent.parent
BUILD_DIR = Path(__file__).resolve().parent
HELPER_SRC = BUILD_DIR / "http_helper.py"
PLUGIN_ROOT = Path.home() / ".hermes" / "plugins"

# {user.id} -> {env.USER_ID}  (case-insensitive on the placeholder name)
_USER_REWRITE_RE = re.compile(r"\{user\.([a-zA-Z_][a-zA-Z0-9_]*)\}")
USER_RENAMES = {
    "id": "USER_ID",
    "username": "USER_NAME",
}

# Map each YAML filename to a plugin name + short description.
PLUGIN_META = {
    "weather.yaml": ("weather", "Open-Meteo weather — current conditions and daily forecast."),
    "plex.yaml": ("plex", "Plex Media Server — sessions, on-deck, library search."),
    "tmdb.yaml": ("tmdb", "TMDB — movie and TV search, details, credits, popular, top-rated."),
    "nzb.yaml": ("nzb", "NZBGet JSON-RPC — queue, history, add, delete, pause, resume."),
    "minimax.yaml": ("minimax", "MiniMax — web search, image understanding, image gen, music gen."),
    "lidarr.yaml": ("lidarr", "Lidarr — artist library, search, add, delete, queue, profiles."),
    "radarr.yaml": ("radarr", "Radarr — movie library, search, add, delete, queue, profiles."),
    "sonarr.yaml": ("sonarr", "Sonarr — series library, search, add, command, calendar, queue."),
    "notes.yaml": ("notes", "Notes vault (notes-srv v2) — tree, list, read, write, search, comments."),
    "tickets.yaml": ("tickets", "Internal ticket system — create, list, get, update, assign, close."),
    "recipes.yaml": ("recipes", "Recipes (recipe-srv v2) — list, get, search, ingredients, steps, tags."),
}

PLACEHOLDER_RE = re.compile(
    r"\{env\.([A-Za-z_][A-Za-z0-9_]*)|\{arg\.([A-Za-z_][A-Za-z0-9_]*)"
)


def rewrite_user_placeholders(text: str) -> tuple[str, set[str]]:
    """Rewrite {user.X} placeholders to {env.USER_X} and collect needed env vars."""
    needed: set[str] = set()

    def repl(m: re.Match) -> str:
        name = m.group(1)
        env_name = USER_RENAMES.get(name, f"USER_{name.upper()}")
        needed.add(env_name)
        return "{env." + env_name + "}"

    return _USER_REWRITE_RE.sub(repl, text), needed


def collect_env_vars(spec: dict[str, Any]) -> set[str]:
    """Find every ``{env.X}`` reference in a tool spec."""
    fields: list[str] = []
    fields.append(spec.get("url", ""))
    fields.append(spec.get("body", ""))
    for header in (spec.get("headers") or {}).values():
        fields.append(header)

    found: set[str] = set()
    for field in fields:
        if not field:
            continue
        for m in re.finditer(r"\{env\.([A-Za-z_][A-Za-z0-9_]*)", field):
            found.add(m.group(1))
    return found


def rewrite_spec(spec: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    """Apply the {user.X} -> {env.X} rewrite to a single tool spec."""
    needed: set[str] = set()
    for key in ("url", "body"):
        if key in spec and isinstance(spec[key], str):
            new, used = rewrite_user_placeholders(spec[key])
            spec[key] = new
            needed.update(used)
    if "headers" in spec and isinstance(spec["headers"], dict):
        new_headers = {}
        for k, v in spec["headers"].items():
            if isinstance(v, str):
                new_v, used = rewrite_user_placeholders(v)
                new_headers[k] = new_v
                needed.update(used)
            else:
                new_headers[k] = v
        spec["headers"] = new_headers
    return spec, needed


def py_repr(value: Any, indent: int = 0) -> str:
    """Render a Python literal in stable form (strings use double quotes)."""
    pad = "    " * indent
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if value is None:
        return "None"
    if isinstance(value, list):
        if not value:
            return "[]"
        inner = ",\n".join(pad + "    " + py_repr(v, indent + 1) for v in value)
        return "[\n" + inner + "\n" + pad + "]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = []
        for k, v in value.items():
            items.append(pad + "    " + py_repr(k, 0) + ": " + py_repr(v, indent + 1).lstrip())
        return "{\n" + ",\n".join(items) + "\n" + pad + "}"
    raise TypeError(f"unsupported literal: {type(value).__name__}")


def build_schema(tool: dict[str, Any]) -> dict[str, Any]:
    args = tool.get("args") or {}
    properties = {name: {k: v for k, v in meta.items() if k != "required"} for name, meta in args.items()}
    required = [name for name, meta in args.items() if meta.get("required")]
    schema = {
        "name": tool["name"],
        "description": tool["description"].strip(),
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }
    return schema


SCHEMA_TEMPLATE = '''"""Tool schemas — what the LLM sees for each {plugin} tool.

Generated from the legacy MCP YAML; do not edit by hand.
"""


SCHEMAS = {body}


def get(name: str) -> dict:
    return SCHEMAS[name]
'''

TOOLS_TEMPLATE = '''"""Tool handlers — what runs when the LLM calls each {plugin} tool.

Every handler delegates to ``_http.execute`` with its spec. Generated from the
legacy MCP YAML; do not edit by hand.
"""
from __future__ import annotations

from ._http import execute


_SPECS = {body}


{handlers}
'''

HANDLER_TEMPLATE = '''def {name}(args: dict, **kwargs) -> str:
    return execute(_SPECS["{name}"], args)


'''


INIT_TEMPLATE = '''"""{title} plugin — registers {count} tool(s) on the given context.

Generated from the legacy MCP YAML; do not edit by hand.
"""
from __future__ import annotations

from . import schemas, tools


PLUGIN_NAME = {name_repr}
TOOLSET = {toolset_repr}
VERSION = {version_repr}
{requires_env_block}


def register(ctx) -> None:
    """Wire every schema to its own handler."""
    for name, schema in schemas.SCHEMAS.items():
        ctx.register_tool(
            name=name,
            toolset=TOOLSET,
            schema=schema,
            handler=getattr(tools, name),
            description=schema["description"],
        )
'''


def render_init(plugin_name: str, requires_env: list[str], count: int) -> str:
    requires_env_block = ""
    if requires_env:
        lines = ",\n    ".join(f'"{v}"' for v in requires_env)
        requires_env_block = (
            "\nREQUIRES_ENV = [\n    " + lines + ",\n]\n"
        )
    return INIT_TEMPLATE.format(
        title=plugin_name,
        count=count,
        name_repr=py_repr(plugin_name),
        toolset_repr=py_repr(plugin_name),
        version_repr=py_repr("1.0.0"),
        requires_env_block=requires_env_block,
    )


PLUGIN_YAML_TEMPLATE = '''name: {name}
version: "1.0.0"
description: {description}
provides_tools:
{tools_block}
{requires_env_block}
'''


def render_plugin_yaml(
    plugin_name: str,
    description: str,
    tool_names: list[str],
    requires_env: list[str],
) -> str:
    tools_block = "\n".join(f"  - {n}" for n in tool_names)
    requires_env_block = ""
    if requires_env:
        items = "\n".join(f"  - {v}" for v in requires_env)
        requires_env_block = f"requires_env:\n{items}\n"
    return PLUGIN_YAML_TEMPLATE.format(
        name=plugin_name,
        description=description,
        tools_block=tools_block,
        requires_env_block=requires_env_block,
    )


def process_yaml(path: Path) -> dict[str, Any]:
    raw = path.read_text()
    data = yaml.safe_load(raw)
    all_env: set[str] = set()
    all_user: set[str] = set()

    tools_out = []
    for tool in data.get("tools") or []:
        tool, used = rewrite_spec(tool)
        all_env.update(collect_env_vars(tool))
        all_env.update(used)
        all_user.update(used)
        tools_out.append(tool)

    return {
        "name": path.stem,
        "tools": tools_out,
        "env_vars": sorted(all_env),
        "user_vars": sorted(all_user),
    }


def write_plugin(meta: dict[str, Any], dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(HELPER_SRC, dest / "_http.py")

    plugin_name = meta["name"]
    description = PLUGIN_META[plugin_name + ".yaml"][1]
    tools_list = meta["tools"]
    tool_names = [t["name"] for t in tools_list]

    schemas_dict = {t["name"]: build_schema(t) for t in tools_list}
    (dest / "schemas.py").write_text(
        SCHEMA_TEMPLATE.format(
            plugin=plugin_name,
            body=py_repr(schemas_dict),
        )
    )

    specs_dict = {}
    for t in tools_list:
        spec = {
            "method": t["method"],
            "url": t["url"],
        }
        if t.get("headers"):
            spec["headers"] = t["headers"]
        if t.get("body"):
            spec["body"] = t["body"]
        if t.get("select"):
            spec["select"] = t["select"]
        specs_dict[t["name"]] = spec
    handlers = "".join(HANDLER_TEMPLATE.format(name=n) for n in tool_names)
    (dest / "tools.py").write_text(
        TOOLS_TEMPLATE.format(plugin=plugin_name, body=py_repr(specs_dict), handlers=handlers)
    )

    (dest / "__init__.py").write_text(
        render_init(plugin_name, meta["env_vars"], len(tools_list))
    )

    (dest / "plugin.yaml").write_text(
        render_plugin_yaml(plugin_name, description, tool_names, meta["env_vars"])
    )


def main() -> int:
    if not HELPER_SRC.exists():
        print(f"helper missing: {HELPER_SRC}", file=sys.stderr)
        return 1

    PLUGIN_ROOT.mkdir(parents=True, exist_ok=True)

    all_env_vars: set[str] = set()
    for yaml_path in sorted(SOURCE_DIR.glob("*.yaml")):
        meta = process_yaml(yaml_path)
        plugin_name, _ = PLUGIN_META[yaml_path.name]
        dest = PLUGIN_ROOT / plugin_name
        write_plugin(meta, dest)
        all_env_vars.update(meta["env_vars"])
        print(f"wrote {dest} ({len(meta['tools'])} tools, {len(meta['env_vars'])} env vars)")

    env_example = PLUGIN_ROOT.parent / ".env.example"
    env_lines = ["# Generated from MCP YAML tool specs\n"]
    for var in sorted(all_env_vars):
        env_lines.append(f"# {var}=")
    env_example.write_text("\n".join(env_lines) + "\n")
    print(f"wrote {env_example} ({len(all_env_vars)} vars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())