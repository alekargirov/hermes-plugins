"""Tool handlers — what runs when the LLM calls each sonarr tool.

Every handler delegates to ``_http.execute`` with its spec. Generated from the
legacy MCP YAML; do not edit by hand.
"""
from __future__ import annotations

from ._http import execute


_SPECS = {
    "sonarr_library": {
        "method": "GET",
        "url": "{env.SONARR_URL}/api/v3/series",
        "headers": {
            "X-Api-Key": "{env.SONARR_API_KEY}"
        },
        "select": [
            "id",
            "title",
            "year",
            "tvdbId",
            "status",
            "monitored"
        ]
    },
    "sonarr_search": {
        "method": "GET",
        "url": "{env.SONARR_URL}/api/v3/series/lookup?term={arg.query}",
        "headers": {
            "X-Api-Key": "{env.SONARR_API_KEY}"
        }
    },
    "sonarr_add": {
        "method": "POST",
        "url": "{env.SONARR_URL}/api/v3/series",
        "headers": {
            "X-Api-Key": "{env.SONARR_API_KEY}"
        },
        "body": "{arg.payload}"
    },
    "sonarr_command": {
        "method": "POST",
        "url": "{env.SONARR_URL}/api/v3/command",
        "headers": {
            "X-Api-Key": "{env.SONARR_API_KEY}"
        },
        "body": "{arg.payload}"
    },
    "sonarr_calendar": {
        "method": "GET",
        "url": "{env.SONARR_URL}/api/v3/calendar?start={arg.start|{now}}&end={arg.end|{now+14d}}&includeSeries=true",
        "headers": {
            "X-Api-Key": "{env.SONARR_API_KEY}"
        }
    },
    "sonarr_queue": {
        "method": "GET",
        "url": "{env.SONARR_URL}/api/v3/queue?includeSeries=true&includeEpisode=true",
        "headers": {
            "X-Api-Key": "{env.SONARR_API_KEY}"
        }
    },
    "sonarr_wanted": {
        "method": "GET",
        "url": "{env.SONARR_URL}/api/v3/wanted/missing?pageSize=10&includeSeries=true&page={arg.page|1}",
        "headers": {
            "X-Api-Key": "{env.SONARR_API_KEY}"
        }
    },
    "sonarr_rootfolder": {
        "method": "GET",
        "url": "{env.SONARR_URL}/api/v3/rootfolder",
        "headers": {
            "X-Api-Key": "{env.SONARR_API_KEY}"
        },
        "select": [
            "id",
            "path",
            "accessible",
            "freeSpace"
        ]
    },
    "sonarr_qualityprofile": {
        "method": "GET",
        "url": "{env.SONARR_URL}/api/v3/qualityprofile",
        "headers": {
            "X-Api-Key": "{env.SONARR_API_KEY}"
        },
        "select": [
            "id",
            "name"
        ]
    }
}


def sonarr_library(args: dict, **kwargs) -> str:
    return execute(_SPECS["sonarr_library"], args)


def sonarr_search(args: dict, **kwargs) -> str:
    return execute(_SPECS["sonarr_search"], args)


def sonarr_add(args: dict, **kwargs) -> str:
    return execute(_SPECS["sonarr_add"], args)


def sonarr_command(args: dict, **kwargs) -> str:
    return execute(_SPECS["sonarr_command"], args)


def sonarr_calendar(args: dict, **kwargs) -> str:
    return execute(_SPECS["sonarr_calendar"], args)


def sonarr_queue(args: dict, **kwargs) -> str:
    return execute(_SPECS["sonarr_queue"], args)


def sonarr_wanted(args: dict, **kwargs) -> str:
    return execute(_SPECS["sonarr_wanted"], args)


def sonarr_rootfolder(args: dict, **kwargs) -> str:
    return execute(_SPECS["sonarr_rootfolder"], args)


def sonarr_qualityprofile(args: dict, **kwargs) -> str:
    return execute(_SPECS["sonarr_qualityprofile"], args)



