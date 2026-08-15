"""lidarr — music.

Ported from the standalone lidarr plugin on 2026-08-15. Auth is Lidarr's own
X-Api-Key. Single-tenant.

Env (profile .env):
  LIDARR_URL      e.g. http://lidarr:8686
  LIDARR_API_KEY  Lidarr's API key (Settings -> General)

Lidarr is the only one of the three *arrs with a metadata profile as well as a
quality profile, and lidarr_add needs both.
"""

from __future__ import annotations

from ._core import Service, Tool, _schema, _b, _bb, _bn, _bs, _n, _s

PLUGIN_VERSION = "2026-08-05.9"


TOOLS = [
    Tool(
        "lidarr_library",
        "List all artists in the Lidarr library (id, artistName, foreignArtistId, monitored). Use the id with lidarr_delete to remove artists.",
        _schema({}),
        "GET",
        "{env.LIDARR_URL}/api/v1/artist",
        body=None,
        select=["id", "artistName", "foreignArtistId", "monitored"],
        limit=None,
    ),
    Tool(
        "lidarr_search",
        "Search for an artist in Lidarr (lookup, not library search). Returns candidates with foreignArtistId (MusicBrainz id) needed by lidarr_add.",
        _schema(
            {
                "query": _s("Artist name to search for"),
            },
            ["query"],
        ),
        "GET",
        "{env.LIDARR_URL}/api/v1/artist/lookup?term={arg.query}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "lidarr_add",
        "Add an artist to Lidarr. Use lidarr_search first to get foreignArtistId and artistName.",
        _schema(
            {
                "foreignArtistId": _s("MusicBrainz artist id from lidarr_search"),
                "artistName": _bs(),
                "qualityProfileId": _bn(),
                "metadataProfileId": _bn(),
                "rootFolderPath": _bs(),
                "monitored": _bb(),
            },
            ["foreignArtistId", "artistName", "qualityProfileId", "metadataProfileId", "rootFolderPath"],
        ),
        "POST",
        "{env.LIDARR_URL}/api/v1/artist",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "lidarr_delete",
        "Delete an artist from Lidarr by id. Set deleteFiles=true to also remove files on disk. Get the id from lidarr_library.",
        _schema(
            {
                "id": _n("Lidarr artist id (from lidarr_library)"),
                "deleteFiles": _b("Also remove files on disk (default false)"),
            },
            ["id"],
        ),
        "DELETE",
        "{env.LIDARR_URL}/api/v1/artist/{arg.id}?deleteFiles={arg.deleteFiles|false}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "lidarr_queue",
        "Get the Lidarr download queue.",
        _schema({}),
        "GET",
        "{env.LIDARR_URL}/api/v1/queue",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "lidarr_wanted",
        "Get missing/wanted albums from Lidarr.",
        _schema({}),
        "GET",
        "{env.LIDARR_URL}/api/v1/wanted/missing?pageSize=50",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "lidarr_rootfolder",
        "List Lidarr root folders (id, path, accessible, freeSpace). Call before lidarr_add to get a valid rootFolderPath (use the path value).",
        _schema({}),
        "GET",
        "{env.LIDARR_URL}/api/v1/rootfolder",
        body=None,
        select=["id", "path", "accessible", "freeSpace"],
        limit=None,
    ),
    Tool(
        "lidarr_qualityprofile",
        "List Lidarr quality profiles (id, name). Call before lidarr_add to get a valid qualityProfileId (use the id).",
        _schema({}),
        "GET",
        "{env.LIDARR_URL}/api/v1/qualityprofile",
        body=None,
        select=["id", "name"],
        limit=None,
    ),
    Tool(
        "lidarr_metadataprofile",
        "List Lidarr metadata profiles (id, name). Call before lidarr_add to get a valid metadataProfileId (use the id).",
        _schema({}),
        "GET",
        "{env.LIDARR_URL}/api/v1/metadataprofile",
        body=None,
        select=["id", "name"],
        limit=None,
    ),
]


SERVICE = Service(
    name="lidarr",
    url_env="LIDARR_URL",
    key_env="LIDARR_API_KEY",
    auth_header="X-Api-Key",
    accept_json=True,
    redact=None,
    log_note=None,
    version=PLUGIN_VERSION,
    tools=TOOLS,
)
