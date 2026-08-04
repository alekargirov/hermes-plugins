"""Tool schemas — what the LLM sees for each sonarr tool.

Generated from the legacy MCP YAML; do not edit by hand.
"""


SCHEMAS = {
    "sonarr_library": {
        "name": "sonarr_library",
        "description": "List TV shows in the Sonarr library (id, title, year, tvdbId, status, monitored). Trimmed to essential fields so large libraries return complete and untruncated.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "sonarr_search": {
        "name": "sonarr_search",
        "description": "Search for a TV show in Sonarr.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "TV show title to search for"
                }
            },
            "required": [
                "query"
            ]
        }
    },
    "sonarr_add": {
        "name": "sonarr_add",
        "description": "Add a TV show to Sonarr. RECIPE (v4 rejects hand-built minimal payloads with an unhelpful bare 400): take the ENTIRE series object returned by sonarr_search for your show (it includes seasons, images, titleSlug, languageProfileId — all required by model binding), then override just: qualityProfileId (from sonarr_qualityprofile), rootFolderPath (from sonarr_rootfolder), monitored:true, and addOptions:{monitor:all, searchForMissingEpisodes:true}. Do NOT construct the object from scratch — that is the cause of ticket #137's 400s. addOptions is what creates/searches episodes; if forgotten, fix after with sonarr_command (RefreshSeries then SeriesSearch).",
        "parameters": {
            "type": "object",
            "properties": {
                "payload": {
                    "type": "object",
                    "description": "Sonarr series object: tvdbId, title, titleSlug, qualityProfileId, rootFolderPath, monitored, seasonFolder, AND addOptions:{\"monitor\":\"all\",\"searchForMissingEpisodes\":true} — the addOptions block is what populates episode records and triggers the initial search."
                }
            },
            "required": [
                "payload"
            ]
        }
    },
    "sonarr_command": {
        "name": "sonarr_command",
        "description": "Run a Sonarr command. If a freshly added series shows no episodes in sonarr_wanted/sonarr_library, call name=RefreshSeries with its seriesId to create the episode records, then name=SeriesSearch with the seriesId to search. (Also valid: RescanSeries, MissingEpisodeSearch.) This is the programmatic equivalent of the manual unmonitor/monitor toggle.",
        "parameters": {
            "type": "object",
            "properties": {
                "payload": {
                    "type": "object",
                    "description": "Command object, e.g. {\"name\":\"RefreshSeries\",\"seriesId\":77} then {\"name\":\"SeriesSearch\",\"seriesId\":77}"
                }
            },
            "required": [
                "payload"
            ]
        }
    },
    "sonarr_calendar": {
        "name": "sonarr_calendar",
        "description": "Get upcoming episodes from Sonarr. Defaults to today through +14 days.",
        "parameters": {
            "type": "object",
            "properties": {
                "start": {
                    "type": "string",
                    "description": "Start date (ISO 8601, e.g. 2026-05-16). Omit for today."
                },
                "end": {
                    "type": "string",
                    "description": "End date (ISO 8601, e.g. 2026-05-23). Omit for today+14d."
                }
            },
            "required": []
        }
    },
    "sonarr_queue": {
        "name": "sonarr_queue",
        "description": "Get the Sonarr download queue.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "sonarr_wanted": {
        "name": "sonarr_wanted",
        "description": "Get missing monitored episodes from Sonarr. Returns 10 per page — increment page for more. totalRecords in response gives the total count.",
        "parameters": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "number",
                    "description": "Page number, starting at 1 (default 1)"
                }
            },
            "required": []
        }
    },
    "sonarr_rootfolder": {
        "name": "sonarr_rootfolder",
        "description": "List Sonarr root folders (id, path, accessible, freeSpace). Call before sonarr_add to get a valid rootFolderPath (use the path value).",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "sonarr_qualityprofile": {
        "name": "sonarr_qualityprofile",
        "description": "List Sonarr quality profiles (id, name). Call before sonarr_add to get a valid qualityProfileId (use the id).",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}


def get(name: str) -> dict:
    return SCHEMAS[name]
