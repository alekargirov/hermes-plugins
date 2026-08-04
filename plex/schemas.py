"""Tool schemas — what the LLM sees for each plex tool.

Generated from the legacy MCP YAML; do not edit by hand.
"""


SCHEMAS = {
    "plex_now_playing": {
        "name": "plex_now_playing",
        "description": "Get currently active Plex playback sessions.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "plex_on_deck": {
        "name": "plex_on_deck",
        "description": "Get Plex on-deck (continue watching) items.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "plex_recently_added": {
        "name": "plex_recently_added",
        "description": "Get recently added content in Plex.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "plex_search": {
        "name": "plex_search",
        "description": "Search the Plex library.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                }
            },
            "required": [
                "query"
            ]
        }
    }
}


def get(name: str) -> dict:
    return SCHEMAS[name]
