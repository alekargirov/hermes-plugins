"""Tool schemas — what the LLM sees for each weather tool.

Generated from the legacy MCP YAML; do not edit by hand.
"""


SCHEMAS = {
    "weather_current": {
        "name": "weather_current",
        "description": "Get current weather conditions (temperature, humidity, wind, visibility) for the configured location.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "weather_forecast": {
        "name": "weather_forecast",
        "description": "Get daily weather forecast for the configured location. days defaults to 3, max 7.",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "number",
                    "description": "Number of forecast days (1–7, default 3)"
                }
            },
            "required": []
        }
    }
}


def get(name: str) -> dict:
    return SCHEMAS[name]
