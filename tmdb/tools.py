"""Tool handlers — what runs when the LLM calls each tmdb tool.

Every handler delegates to ``_http.execute`` with its spec. Generated from the
legacy MCP YAML; do not edit by hand.
"""
from __future__ import annotations

from ._http import execute


_SPECS = {
    "tmdb_search": {
        "method": "GET",
        "url": "https://api.themoviedb.org/3/search/{arg.type}?api_key={env.TMDB_API_KEY}&query={arg.query}"
    },
    "tmdb_get_details": {
        "method": "GET",
        "url": "https://api.themoviedb.org/3/{arg.type}/{arg.id}?api_key={env.TMDB_API_KEY}"
    },
    "tmdb_get_credits": {
        "method": "GET",
        "url": "https://api.themoviedb.org/3/{arg.type}/{arg.id}/credits?api_key={env.TMDB_API_KEY}"
    },
    "tmdb_get_popular": {
        "method": "GET",
        "url": "https://api.themoviedb.org/3/{arg.type}/popular?api_key={env.TMDB_API_KEY}&page={arg.page}"
    },
    "tmdb_get_top_rated": {
        "method": "GET",
        "url": "https://api.themoviedb.org/3/movie/top_rated?api_key={env.TMDB_API_KEY}&page={arg.page}"
    }
}


def tmdb_search(args: dict, **kwargs) -> str:
    return execute(_SPECS["tmdb_search"], args)


def tmdb_get_details(args: dict, **kwargs) -> str:
    return execute(_SPECS["tmdb_get_details"], args)


def tmdb_get_credits(args: dict, **kwargs) -> str:
    return execute(_SPECS["tmdb_get_credits"], args)


def tmdb_get_popular(args: dict, **kwargs) -> str:
    return execute(_SPECS["tmdb_get_popular"], args)


def tmdb_get_top_rated(args: dict, **kwargs) -> str:
    return execute(_SPECS["tmdb_get_top_rated"], args)



