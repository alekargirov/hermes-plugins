"""radarr — movies.

Ported from the standalone radarr plugin on 2026-08-15. The tool table is
unchanged; everything above it now lives in _core.py.

Auth is Radarr's own X-Api-Key. Single-tenant — there is no user id and nothing
to scope, because everyone shares one movie library.

Env (profile .env):
  RADARR_URL      e.g. http://radarr:7878
  RADARR_API_KEY  Radarr's API key (Settings -> General)

radarr_library declares `select`: a full Radarr movie object is enormous and
there are thousands of them, so the tool projects each row down to six fields.
Without that the model gets a truncated wall of JSON instead of a usable list.
"""

from __future__ import annotations

from ._core import Service, Tool, _schema, _b, _bb, _bn, _bs, _n, _s

PLUGIN_VERSION = "2026-08-05.8"


TOOLS = [
    Tool(
        "radarr_library",
        "List all movies in the Radarr library (id, title, year, tmdbId, hasFile, monitored). Trimmed to essential fields so large libraries return complete and untruncated. Use the id field with radarr_delete to remove movies.",
        _schema({}),
        "GET",
        "{env.RADARR_URL}/api/v3/movie",
        body=None,
        select=["id", "title", "year", "tmdbId", "hasFile", "monitored"],
        limit=None,
    ),
    Tool(
        "radarr_search",
        "Search for a movie in Radarr (lookup, not library search). Matched against title.",
        _schema(
            {
                "query": _s("Movie title to search for"),
            },
            ["query"],
        ),
        "GET",
        "{env.RADARR_URL}/api/v3/movie/lookup?term={arg.query}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "radarr_add",
        "Add a movie to Radarr. Use radarr_search first to get tmdbId and titleSlug.",
        _schema(
            {
                "tmdbId": _n("TMDB id from radarr_search"),
                "title": _bs(),
                "titleSlug": _bs(),
                "qualityProfileId": _bn(),
                "rootFolderPath": _bs(),
                "monitored": _bb(),
            },
            ["tmdbId", "title", "titleSlug", "qualityProfileId", "rootFolderPath"],
        ),
        "POST",
        "{env.RADARR_URL}/api/v3/movie",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "radarr_delete",
        "Delete a movie from Radarr by its id. Set deleteFiles=true to also remove files on disk. Get the id from radarr_library.",
        _schema(
            {
                "id": _n("Radarr movie id (from radarr_library)"),
                "deleteFiles": _b("Also remove files on disk (default false)"),
            },
            ["id"],
        ),
        "DELETE",
        "{env.RADARR_URL}/api/v3/movie/{arg.id}?deleteFiles={arg.deleteFiles|false}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "radarr_queue",
        "Get the Radarr download queue.",
        _schema({}),
        "GET",
        "{env.RADARR_URL}/api/v3/queue?includeMovie=true",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "radarr_wanted",
        "Get missing/wanted movies from Radarr.",
        _schema({}),
        "GET",
        "{env.RADARR_URL}/api/v3/wanted/missing?pageSize=50",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "radarr_rootfolder",
        "List Radarr root folders (id, path, accessible, freeSpace). Call before radarr_add to get a valid rootFolderPath (use the path value).",
        _schema({}),
        "GET",
        "{env.RADARR_URL}/api/v3/rootfolder",
        body=None,
        select=["id", "path", "accessible", "freeSpace"],
        limit=None,
    ),
    Tool(
        "radarr_qualityprofile",
        "List Radarr quality profiles (id, name). Call before radarr_add to get a valid qualityProfileId (use the id).",
        _schema({}),
        "GET",
        "{env.RADARR_URL}/api/v3/qualityprofile",
        body=None,
        select=["id", "name"],
        limit=None,
    ),
]


SERVICE = Service(
    name="radarr",
    url_env="RADARR_URL",
    key_env="RADARR_API_KEY",
    auth_header="X-Api-Key",
    accept_json=True,
    redact=None,
    log_note=None,
    version=PLUGIN_VERSION,
    tools=TOOLS,
)
