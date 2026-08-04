"""Tool handlers — what runs when the LLM calls each lidarr tool.

Every handler delegates to ``_http.execute`` with its spec. Generated from the
legacy MCP YAML; do not edit by hand.
"""
from __future__ import annotations

from ._http import execute


_SPECS = {
    "lidarr_library": {
        "method": "GET",
        "url": "{env.LIDARR_URL}/api/v1/artist",
        "headers": {
            "X-Api-Key": "{env.LIDARR_API_KEY}"
        },
        "select": [
            "id",
            "artistName",
            "foreignArtistId",
            "monitored"
        ]
    },
    "lidarr_search": {
        "method": "GET",
        "url": "{env.LIDARR_URL}/api/v1/artist/lookup?term={arg.query}",
        "headers": {
            "X-Api-Key": "{env.LIDARR_API_KEY}"
        }
    },
    "lidarr_add": {
        "method": "POST",
        "url": "{env.LIDARR_URL}/api/v1/artist",
        "headers": {
            "X-Api-Key": "{env.LIDARR_API_KEY}"
        }
    },
    "lidarr_delete": {
        "method": "DELETE",
        "url": "{env.LIDARR_URL}/api/v1/artist/{arg.id}?deleteFiles={arg.deleteFiles|false}",
        "headers": {
            "X-Api-Key": "{env.LIDARR_API_KEY}"
        }
    },
    "lidarr_queue": {
        "method": "GET",
        "url": "{env.LIDARR_URL}/api/v1/queue",
        "headers": {
            "X-Api-Key": "{env.LIDARR_API_KEY}"
        }
    },
    "lidarr_wanted": {
        "method": "GET",
        "url": "{env.LIDARR_URL}/api/v1/wanted/missing?pageSize=50",
        "headers": {
            "X-Api-Key": "{env.LIDARR_API_KEY}"
        }
    },
    "lidarr_rootfolder": {
        "method": "GET",
        "url": "{env.LIDARR_URL}/api/v1/rootfolder",
        "headers": {
            "X-Api-Key": "{env.LIDARR_API_KEY}"
        },
        "select": [
            "id",
            "path",
            "accessible",
            "freeSpace"
        ]
    },
    "lidarr_qualityprofile": {
        "method": "GET",
        "url": "{env.LIDARR_URL}/api/v1/qualityprofile",
        "headers": {
            "X-Api-Key": "{env.LIDARR_API_KEY}"
        },
        "select": [
            "id",
            "name"
        ]
    },
    "lidarr_metadataprofile": {
        "method": "GET",
        "url": "{env.LIDARR_URL}/api/v1/metadataprofile",
        "headers": {
            "X-Api-Key": "{env.LIDARR_API_KEY}"
        },
        "select": [
            "id",
            "name"
        ]
    }
}


def lidarr_library(args: dict, **kwargs) -> str:
    return execute(_SPECS["lidarr_library"], args)


def lidarr_search(args: dict, **kwargs) -> str:
    return execute(_SPECS["lidarr_search"], args)


def lidarr_add(args: dict, **kwargs) -> str:
    return execute(_SPECS["lidarr_add"], args)


def lidarr_delete(args: dict, **kwargs) -> str:
    return execute(_SPECS["lidarr_delete"], args)


def lidarr_queue(args: dict, **kwargs) -> str:
    return execute(_SPECS["lidarr_queue"], args)


def lidarr_wanted(args: dict, **kwargs) -> str:
    return execute(_SPECS["lidarr_wanted"], args)


def lidarr_rootfolder(args: dict, **kwargs) -> str:
    return execute(_SPECS["lidarr_rootfolder"], args)


def lidarr_qualityprofile(args: dict, **kwargs) -> str:
    return execute(_SPECS["lidarr_qualityprofile"], args)


def lidarr_metadataprofile(args: dict, **kwargs) -> str:
    return execute(_SPECS["lidarr_metadataprofile"], args)



