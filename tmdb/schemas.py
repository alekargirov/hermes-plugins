"""Tool schemas — what the LLM sees for each tmdb tool.

Generated from the legacy MCP YAML; do not edit by hand.
"""


SCHEMAS = {
    "tmdb_search": {
        "name": "tmdb_search",
        "description": "Search movies or TV shows using TMDB. type: 'movie' or 'tv'.",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "description": "'movie' or 'tv'"
                },
                "query": {
                    "type": "string",
                    "description": "Search query"
                }
            },
            "required": [
                "type",
                "query"
            ]
        }
    },
    "tmdb_get_details": {
        "name": "tmdb_get_details",
        "description": "Get movie or TV show details by TMDB ID. type: 'movie' or 'tv'.",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "description": "'movie' or 'tv'"
                },
                "id": {
                    "type": "number",
                    "description": "TMDB ID"
                }
            },
            "required": [
                "type",
                "id"
            ]
        }
    },
    "tmdb_get_credits": {
        "name": "tmdb_get_credits",
        "description": "Get cast and crew credits for a movie or TV show by TMDB ID. type: 'movie' or 'tv'.",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "description": "'movie' or 'tv'"
                },
                "id": {
                    "type": "number",
                    "description": "TMDB ID"
                }
            },
            "required": [
                "type",
                "id"
            ]
        }
    },
    "tmdb_get_popular": {
        "name": "tmdb_get_popular",
        "description": "Get popular movies or TV shows from TMDB. type: 'movie' or 'tv'.",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "description": "'movie' or 'tv'"
                },
                "page": {
                    "type": "number",
                    "description": "Page number"
                }
            },
            "required": [
                "type",
                "page"
            ]
        }
    },
    "tmdb_get_top_rated": {
        "name": "tmdb_get_top_rated",
        "description": "Get top-rated movies from TMDB.",
        "parameters": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "number",
                    "description": "Page number"
                }
            },
            "required": [
                "page"
            ]
        }
    }
}


def get(name: str) -> dict:
    return SCHEMAS[name]
