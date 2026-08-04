"""Tool schemas — what the LLM sees for each radarr tool.

Generated from the legacy MCP YAML; do not edit by hand.
"""


SCHEMAS = {
    "radarr_library": {
        "name": "radarr_library",
        "description": "List all movies in the Radarr library (id, title, year, tmdbId, hasFile, monitored). Trimmed to essential fields so large libraries return complete and untruncated. Use the id field with radarr_delete to remove movies.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "radarr_search": {
        "name": "radarr_search",
        "description": "Search for a movie in Radarr (lookup, not library search). Matched against title.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Movie title to search for"
                }
            },
            "required": [
                "query"
            ]
        }
    },
    "radarr_add": {
        "name": "radarr_add",
        "description": "Add a movie to Radarr. Use radarr_search first to get tmdbId and titleSlug.",
        "parameters": {
            "type": "object",
            "properties": {
                "tmdbId": {
                    "type": "number",
                    "description": "TMDB id from radarr_search"
                },
                "title": {
                    "type": "string"
                },
                "titleSlug": {
                    "type": "string"
                },
                "qualityProfileId": {
                    "type": "number"
                },
                "rootFolderPath": {
                    "type": "string"
                },
                "monitored": {
                    "type": "boolean"
                }
            },
            "required": [
                "tmdbId",
                "title",
                "titleSlug",
                "qualityProfileId",
                "rootFolderPath"
            ]
        }
    },
    "radarr_delete": {
        "name": "radarr_delete",
        "description": "Delete a movie from Radarr by its id. Set deleteFiles=true to also remove files on disk. Get the id from radarr_library.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "number",
                    "description": "Radarr movie id (from radarr_library)"
                },
                "deleteFiles": {
                    "type": "boolean",
                    "description": "Also remove files on disk (default false)"
                }
            },
            "required": [
                "id"
            ]
        }
    },
    "radarr_queue": {
        "name": "radarr_queue",
        "description": "Get the Radarr download queue.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "radarr_wanted": {
        "name": "radarr_wanted",
        "description": "Get missing/wanted movies from Radarr.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "radarr_rootfolder": {
        "name": "radarr_rootfolder",
        "description": "List Radarr root folders (id, path, accessible, freeSpace). Call before radarr_add to get a valid rootFolderPath (use the path value).",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "radarr_qualityprofile": {
        "name": "radarr_qualityprofile",
        "description": "List Radarr quality profiles (id, name). Call before radarr_add to get a valid qualityProfileId (use the id).",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}


def get(name: str) -> dict:
    return SCHEMAS[name]
