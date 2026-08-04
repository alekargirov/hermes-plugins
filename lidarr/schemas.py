"""Tool schemas — what the LLM sees for each lidarr tool.

Generated from the legacy MCP YAML; do not edit by hand.
"""


SCHEMAS = {
    "lidarr_library": {
        "name": "lidarr_library",
        "description": "List all artists in the Lidarr library (id, artistName, foreignArtistId, monitored). Use the id with lidarr_delete to remove artists.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "lidarr_search": {
        "name": "lidarr_search",
        "description": "Search for an artist in Lidarr (lookup, not library search). Returns candidates with foreignArtistId (MusicBrainz id) needed by lidarr_add.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Artist name to search for"
                }
            },
            "required": [
                "query"
            ]
        }
    },
    "lidarr_add": {
        "name": "lidarr_add",
        "description": "Add an artist to Lidarr. Use lidarr_search first to get foreignArtistId and artistName.",
        "parameters": {
            "type": "object",
            "properties": {
                "foreignArtistId": {
                    "type": "string",
                    "description": "MusicBrainz artist id from lidarr_search"
                },
                "artistName": {
                    "type": "string"
                },
                "qualityProfileId": {
                    "type": "number"
                },
                "metadataProfileId": {
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
                "foreignArtistId",
                "artistName",
                "qualityProfileId",
                "metadataProfileId",
                "rootFolderPath"
            ]
        }
    },
    "lidarr_delete": {
        "name": "lidarr_delete",
        "description": "Delete an artist from Lidarr by id. Set deleteFiles=true to also remove files on disk. Get the id from lidarr_library.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "number",
                    "description": "Lidarr artist id (from lidarr_library)"
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
    "lidarr_queue": {
        "name": "lidarr_queue",
        "description": "Get the Lidarr download queue.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "lidarr_wanted": {
        "name": "lidarr_wanted",
        "description": "Get missing/wanted albums from Lidarr.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "lidarr_rootfolder": {
        "name": "lidarr_rootfolder",
        "description": "List Lidarr root folders (id, path, accessible, freeSpace). Call before lidarr_add to get a valid rootFolderPath (use the path value).",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "lidarr_qualityprofile": {
        "name": "lidarr_qualityprofile",
        "description": "List Lidarr quality profiles (id, name). Call before lidarr_add to get a valid qualityProfileId (use the id).",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "lidarr_metadataprofile": {
        "name": "lidarr_metadataprofile",
        "description": "List Lidarr metadata profiles (id, name). Call before lidarr_add to get a valid metadataProfileId (use the id).",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}


def get(name: str) -> dict:
    return SCHEMAS[name]
