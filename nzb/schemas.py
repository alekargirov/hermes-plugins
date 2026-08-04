"""Tool schemas — what the LLM sees for each nzb tool.

Generated from the legacy MCP YAML; do not edit by hand.
"""


SCHEMAS = {
    "nzb_status": {
        "name": "nzb_status",
        "description": "NZBGet server status — download rate, remaining size, paused state, free disk space.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "nzb_queue": {
        "name": "nzb_queue",
        "description": "List the current NZBGet download queue (active and queued items with NZBID, name, size, progress). Use NZBID with nzb_delete.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "nzb_history": {
        "name": "nzb_history",
        "description": "NZBGet download history (completed/failed items). Returns the full history — can be long.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "nzb_add": {
        "name": "nzb_add",
        "description": "Add a download to NZBGet by NZB file URL. NZBGet fetches the URL itself. Optionally set a category (e.g. movies, tv, music) and a name.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Direct URL to the .nzb file"
                },
                "category": {
                    "type": "string",
                    "description": "NZBGet category (optional, e.g. movies, tv, music)"
                },
                "name": {
                    "type": "string",
                    "description": "Filename to store as (optional — derived from the URL if empty)"
                }
            },
            "required": [
                "url"
            ]
        }
    },
    "nzb_delete": {
        "name": "nzb_delete",
        "description": "Delete a queue item from NZBGet by NZBID (from nzb_queue). Removes the download, keeps nothing.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "number",
                    "description": "NZBID from nzb_queue"
                }
            },
            "required": [
                "id"
            ]
        }
    },
    "nzb_pause": {
        "name": "nzb_pause",
        "description": "Pause all NZBGet downloads.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "nzb_resume": {
        "name": "nzb_resume",
        "description": "Resume all NZBGet downloads.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}


def get(name: str) -> dict:
    return SCHEMAS[name]
