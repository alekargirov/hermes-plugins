"""Tool handlers — what runs when the LLM calls each radarr tool.

Every handler delegates to ``_http.execute`` with its spec. Generated from the
legacy MCP YAML; do not edit by hand.
"""
from __future__ import annotations

from ._http import execute


_SPECS = {
    "radarr_library": {
        "method": "GET",
        "url": "{env.RADARR_URL}/api/v3/movie",
        "headers": {
            "X-Api-Key": "{env.RADARR_API_KEY}"
        },
        "select": [
            "id",
            "title",
            "year",
            "tmdbId",
            "hasFile",
            "monitored"
        ]
    },
    "radarr_search": {
        "method": "GET",
        "url": "{env.RADARR_URL}/api/v3/movie/lookup?term={arg.query}",
        "headers": {
            "X-Api-Key": "{env.RADARR_API_KEY}"
        }
    },
    "radarr_add": {
        "method": "POST",
        "url": "{env.RADARR_URL}/api/v3/movie",
        "headers": {
            "X-Api-Key": "{env.RADARR_API_KEY}"
        }
    },
    "radarr_delete": {
        "method": "DELETE",
        "url": "{env.RADARR_URL}/api/v3/movie/{arg.id}?deleteFiles={arg.deleteFiles|false}",
        "headers": {
            "X-Api-Key": "{env.RADARR_API_KEY}"
        }
    },
    "radarr_queue": {
        "method": "GET",
        "url": "{env.RADARR_URL}/api/v3/queue?includeMovie=true",
        "headers": {
            "X-Api-Key": "{env.RADARR_API_KEY}"
        }
    },
    "radarr_wanted": {
        "method": "GET",
        "url": "{env.RADARR_URL}/api/v3/wanted/missing?pageSize=50",
        "headers": {
            "X-Api-Key": "{env.RADARR_API_KEY}"
        }
    },
    "radarr_rootfolder": {
        "method": "GET",
        "url": "{env.RADARR_URL}/api/v3/rootfolder",
        "headers": {
            "X-Api-Key": "{env.RADARR_API_KEY}"
        },
        "select": [
            "id",
            "path",
            "accessible",
            "freeSpace"
        ]
    },
    "radarr_qualityprofile": {
        "method": "GET",
        "url": "{env.RADARR_URL}/api/v3/qualityprofile",
        "headers": {
            "X-Api-Key": "{env.RADARR_API_KEY}"
        },
        "select": [
            "id",
            "name"
        ]
    }
}


def radarr_library(args: dict, **kwargs) -> str:
    return execute(_SPECS["radarr_library"], args)


def radarr_search(args: dict, **kwargs) -> str:
    return execute(_SPECS["radarr_search"], args)


def radarr_add(args: dict, **kwargs) -> str:
    return execute(_SPECS["radarr_add"], args)


def radarr_delete(args: dict, **kwargs) -> str:
    return execute(_SPECS["radarr_delete"], args)


def radarr_queue(args: dict, **kwargs) -> str:
    return execute(_SPECS["radarr_queue"], args)


def radarr_wanted(args: dict, **kwargs) -> str:
    return execute(_SPECS["radarr_wanted"], args)


def radarr_rootfolder(args: dict, **kwargs) -> str:
    return execute(_SPECS["radarr_rootfolder"], args)


def radarr_qualityprofile(args: dict, **kwargs) -> str:
    return execute(_SPECS["radarr_qualityprofile"], args)



