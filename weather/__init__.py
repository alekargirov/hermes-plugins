"""weather plugin — registers 2 tool(s) on the given context.

Generated from the legacy MCP YAML; do not edit by hand.
"""
from __future__ import annotations

from . import schemas, tools


PLUGIN_NAME = "weather"
TOOLSET = "weather"
VERSION = "1.0.0"

REQUIRES_ENV = [
    "WEATHER_LAT",
    "WEATHER_LON",
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
