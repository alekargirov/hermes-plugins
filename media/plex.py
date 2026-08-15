"""plex — the player, and now collections.

Ported from the standalone plex plugin on 2026-08-15. Auth is X-Plex-Token,
and the Accept header matters: without it Plex answers XML and the model gets
a wall of markup it cannot parse.

Read tools plus collection management. Collections are the one thing here that
WRITES, and they write only to the grouping — no tool in this file deletes,
moves or edits a film. Kometa is untouched by them: its config runs
`sync_mode: append` with `delete_collections: {configured: false, managed:
true}`, so it only removes collections it made and has since dropped a
definition for. Anything created here is unmanaged, which Kometa lists
(`show_unmanaged: true`) and leaves alone.

Env (profile .env):
  PLEX_URL          e.g. http://plex:32400
  PLEX_TOKEN        a Plex auth token
  PLEX_MACHINE_ID   the server's machineIdentifier, from GET /identity.
                    Needed ONLY by the collection writes; the read tools work
                    without it, and the two that need it refuse by name.
"""

from __future__ import annotations

from ._core import Service, Tool, _n, _schema, _s

PLUGIN_VERSION = "2026-08-15.11"


TOOLS = [
    Tool(
        "plex_now_playing",
        "Get currently active Plex playback sessions.",
        _schema({}),
        "GET",
        "{env.PLEX_URL}/status/sessions",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "plex_on_deck",
        "Get Plex on-deck (continue watching) items.",
        _schema({}),
        "GET",
        "{env.PLEX_URL}/library/onDeck",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "plex_recently_added",
        "Get recently added content in Plex.",
        _schema({}),
        "GET",
        "{env.PLEX_URL}/library/recentlyAdded",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "plex_search",
        "Search the Plex library.",
        _schema(
            {
                "query": _s("Search query"),
            },
            ["query"],
        ),
        "GET",
        "{env.PLEX_URL}/search?query={arg.query}",
        body=None,
        select=None,
        limit=None,
    ),
    # --- collections ------------------------------------------------------
    #
    # Plex's collection endpoints are undocumented but stable, and verified
    # against the live server (Plex 1.43.2) on 2026-08-15 before this was
    # written: create, add, remove and delete were each run end to end and the
    # test collections removed afterwards.
    #
    # The one non-obvious part is the `uri` parameter. Items are addressed by a
    # SERVER uri, not a bare ratingKey:
    #
    #   server://<machineIdentifier>/com.plexapp.plugins.library/library/metadata/721,1378
    #
    # It is accepted unencoded (only the ratingKeys are quoted, since they are
    # the substituted arg) — also verified, not assumed. The machineIdentifier
    # is a fixed per-server string from GET /identity; it lives in
    # PLEX_MACHINE_ID rather than being fetched per call so a missing value
    # fails loudly at the guard instead of silently creating empty collections.
    Tool(
        "plex_sections",
        "List Plex libraries with their section ids. Needed before working "
        "with collections — the movie library's id is what the collection "
        "tools take as section_id.",
        _schema({}),
        "GET",
        "{env.PLEX_URL}/library/sections",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "plex_collections",
        "List the collections in a Plex library section. Each has a "
        "ratingKey — that is the collection_key the other collection tools "
        "take.",
        _schema(
            {
                "section_id": _s("Library section id, from plex_sections"),
            },
            ["section_id"],
        ),
        "GET",
        "{env.PLEX_URL}/library/sections/{arg.section_id}/collections",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "plex_collection_items",
        "List the items inside a Plex collection.",
        _schema(
            {
                "collection_key": _s("The collection's ratingKey"),
            },
            ["collection_key"],
        ),
        "GET",
        "{env.PLEX_URL}/library/collections/{arg.collection_key}/children",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "plex_collection_create",
        "Create a Plex collection containing the given items. Get the "
        "ratingKeys from plex_search first. Plex does not merge by title — "
        "creating a collection whose name already exists makes a second one, "
        "so check plex_collections and use plex_collection_add instead when "
        "it is already there.",
        _schema(
            {
                "title": _s("Name of the collection"),
                "section_id": _s("Library section id, from plex_sections"),
                "rating_keys": _s(
                    "Comma-separated ratingKeys of the items to put in it, "
                    "e.g. '721,1378'. At least one is required — Plex will "
                    "not create an empty collection."
                ),
                "item_type": _n(
                    "Type of the items: 1 for movies, 2 for TV shows. "
                    "Defaults to 1."
                ),
            },
            ["title", "section_id", "rating_keys"],
        ),
        "POST",
        "{env.PLEX_URL}/library/collections"
        "?type={arg.item_type|1}&smart=0"
        "&title={arg.title}&sectionId={arg.section_id}"
        "&uri=server://{env.PLEX_MACHINE_ID}"
        "/com.plexapp.plugins.library/library/metadata/{arg.rating_keys}",
        # An empty body, not the default `json.dumps(args)`: these endpoints
        # take everything in the query string, and the verified call sent no
        # body at all.
        body="",
        select=None,
        limit=None,
        requires_env=("PLEX_MACHINE_ID",),
    ),
    Tool(
        "plex_collection_add",
        "Add items to an existing Plex collection.",
        _schema(
            {
                "collection_key": _s("The collection's ratingKey"),
                "rating_keys": _s(
                    "Comma-separated ratingKeys of the items to add, "
                    "e.g. '721,1378'"
                ),
            },
            ["collection_key", "rating_keys"],
        ),
        "PUT",
        "{env.PLEX_URL}/library/collections/{arg.collection_key}/items"
        "?uri=server://{env.PLEX_MACHINE_ID}"
        "/com.plexapp.plugins.library/library/metadata/{arg.rating_keys}",
        body="",
        select=None,
        limit=None,
        requires_env=("PLEX_MACHINE_ID",),
    ),
    Tool(
        "plex_collection_remove",
        "Remove ONE item from a Plex collection. The film stays in the "
        "library; only its membership goes.",
        _schema(
            {
                "collection_key": _s("The collection's ratingKey"),
                "rating_key": _s("ratingKey of the single item to remove"),
            },
            ["collection_key", "rating_key"],
        ),
        "DELETE",
        "{env.PLEX_URL}/library/collections/{arg.collection_key}"
        "/children/{arg.rating_key}",
        body=None,
        select=None,
        limit=None,
    ),
    Tool(
        "plex_collection_delete",
        "Delete a Plex collection. The films inside it are NOT deleted — "
        "only the grouping.",
        _schema(
            {
                "collection_key": _s("The collection's ratingKey"),
            },
            ["collection_key"],
        ),
        "DELETE",
        "{env.PLEX_URL}/library/metadata/{arg.collection_key}",
        body=None,
        select=None,
        limit=None,
    ),
]


SERVICE = Service(
    name="plex",
    url_env="PLEX_URL",
    key_env="PLEX_TOKEN",
    auth_header="X-Plex-Token",
    accept_json=True,
    redact=None,
    log_note=None,
    version=PLUGIN_VERSION,
    tools=TOOLS,
)
