"""sonarr — series.

Ported from the standalone sonarr plugin on 2026-08-15. Auth is Sonarr's own
X-Api-Key. Single-tenant.

Env (profile .env):
  SONARR_URL      e.g. http://sonarr:8989
  SONARR_API_KEY  Sonarr's API key (Settings -> General)

sonarr_calendar's date range is the reason _render resolves date macros before
argument tokens: `start={arg.start|{now}}&end={arg.end|{now+14d}}` nests a
macro INSIDE a default. See _template/url_template.py.
"""

from __future__ import annotations

from ._core import Service, Tool, _schema, _n, _s

PLUGIN_VERSION = "2026-08-05.9"


TOOLS = [
    Tool(
        "sonarr_library",
        "List TV shows in the Sonarr library (id, title, year, tvdbId, status, monitored). Trimmed to essential fields so large libraries return complete and untruncated.",
        _schema({}),
        "GET",
        "{env.SONARR_URL}/api/v3/series",
        body=None,
        select=["id", "title", "year", "tvdbId", "status", "monitored"],
        limit=None,
    ),
    Tool(
        "sonarr_search",
        "Search for a TV show in Sonarr.",
        _schema(
            {
                "query": _s("TV show title to search for"),
            },
            ["query"],
        ),
        "GET",
        "{env.SONARR_URL}/api/v3/series/lookup?term={arg.query}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "sonarr_add",
        "Add a TV show to Sonarr. RECIPE (v4 rejects hand-built minimal payloads with an unhelpful bare 400): take the ENTIRE series object returned by sonarr_search for your show (it includes seasons, images, titleSlug, languageProfileId — all required by model binding), then override just: qualityProfileId (from sonarr_qualityprofile), rootFolderPath (from sonarr_rootfolder), monitored:true, and addOptions:{monitor:all, searchForMissingEpisodes:true}. Do NOT construct the object from scratch — that is the cause of ticket #137's 400s. addOptions is what creates/searches episodes; if forgotten, fix after with sonarr_command (RefreshSeries then SeriesSearch).",
        _schema(
            {
                "payload": _s("Sonarr series object: tvdbId, title, titleSlug, qualityProfileId, rootFolderPath, monitored, seasonFolder, AND addOptions:{\"monitor\":\"all\",\"searchForMissingEpisodes\":true} — the addOptions block is what populates episode records and triggers the initial search."),
            },
            ["payload"],
        ),
        "POST",
        "{env.SONARR_URL}/api/v3/series",
        body="{arg.payload}",
        select=None,
        limit=None,
    ),
    Tool(
        "sonarr_command",
        "Run a Sonarr command. If a freshly added series shows no episodes in sonarr_wanted/sonarr_library, call name=RefreshSeries with its seriesId to create the episode records, then name=SeriesSearch with the seriesId to search. (Also valid: RescanSeries, MissingEpisodeSearch.) This is the programmatic equivalent of the manual unmonitor/monitor toggle.",
        _schema(
            {
                "payload": _s("Command object, e.g. {\"name\":\"RefreshSeries\",\"seriesId\":77} then {\"name\":\"SeriesSearch\",\"seriesId\":77}"),
            },
            ["payload"],
        ),
        "POST",
        "{env.SONARR_URL}/api/v3/command",
        body="{arg.payload}",
        select=None,
        limit=None,
    ),
    Tool(
        "sonarr_calendar",
        "Get upcoming episodes from Sonarr. Defaults to today through +14 days.",
        _schema(
            {
                "start": _s("Start date (ISO 8601, e.g. 2026-05-16). Omit for today."),
                "end": _s("End date (ISO 8601, e.g. 2026-05-23). Omit for today+14d."),
            },
        ),
        "GET",
        "{env.SONARR_URL}/api/v3/calendar?start={arg.start|{now}}&end={arg.end|{now+14d}}&includeSeries=true",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "sonarr_queue",
        "Get the Sonarr download queue.",
        _schema({}),
        "GET",
        "{env.SONARR_URL}/api/v3/queue?includeSeries=true&includeEpisode=true",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "sonarr_wanted",
        "Get missing monitored episodes from Sonarr. Returns 10 per page — increment page for more. totalRecords in response gives the total count.",
        _schema(
            {
                "page": _n("Page number, starting at 1 (default 1)"),
            },
        ),
        "GET",
        "{env.SONARR_URL}/api/v3/wanted/missing?pageSize=10&includeSeries=true&page={arg.page|1}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "sonarr_rootfolder",
        "List Sonarr root folders (id, path, accessible, freeSpace). Call before sonarr_add to get a valid rootFolderPath (use the path value).",
        _schema({}),
        "GET",
        "{env.SONARR_URL}/api/v3/rootfolder",
        body=None,
        select=["id", "path", "accessible", "freeSpace"],
        limit=None,
    ),
    Tool(
        "sonarr_qualityprofile",
        "List Sonarr quality profiles (id, name). Call before sonarr_add to get a valid qualityProfileId (use the id).",
        _schema({}),
        "GET",
        "{env.SONARR_URL}/api/v3/qualityprofile",
        body=None,
        select=["id", "name"],
        limit=None,
    ),
]


SERVICE = Service(
    name="sonarr",
    url_env="SONARR_URL",
    key_env="SONARR_API_KEY",
    auth_header="X-Api-Key",
    accept_json=True,
    redact=None,
    log_note=None,
    version=PLUGIN_VERSION,
    tools=TOOLS,
)
