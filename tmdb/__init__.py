"""tmdb plugin — registers 5 tool(s) on the given context.

Generated from the legacy MCP YAML; do not edit by hand.
"""
from __future__ import annotations

from . import schemas, tools


PLUGIN_NAME = "tmdb"
TOOLSET = "tmdb"
VERSION = "1.0.0"

REQUIRES_ENV = [
    "TMDB_API_KEY",
]



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
