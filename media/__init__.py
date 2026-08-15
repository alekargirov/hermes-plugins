"""media — Radarr, Sonarr, Lidarr, Plex, NZBGet and TMDB in one plugin.

WHAT THIS IS
Six third-party media backends that used to be six plugin directories. They
were merged on 2026-08-15 because ~85% of each file was the same copied
boilerplate: the URL template, the response shaping, the HTTP call and the
schema helpers. That now lives once, in _core.py.

ONE PLUGIN, SIX TOOLSETS — READ THIS BEFORE "SIMPLIFYING" IT
Every tool still registers under its own toolset (radarr, sonarr, lidarr, plex,
nzb, tmdb), NOT under a flat `media`. Merging the directories was the point;
merging the toolsets is not. 42 tools in one bucket re-creates the failure this
repo already paid for once — when fin3 shared the `todo` toolset the model read
a neighbour's schema and refused a change the tool actually supported.
tests/test_direct_plugins.py holds that line.

Tool names and env variable names are unchanged from the standalone plugins, so
nothing in any profile .env moves.

A DIRECT plugin: these are third-party services on the LAN (and one public
API), so there is no endpoint of ours to forward to and _core owns the HTTP
call. Single-tenant throughout — everyone shares one library, so there is no
user to scope to.

ADDING A SERVICE
Write <name>.py with a TOOLS table and a SERVICE descriptor, then add it to
SERVICES below. If its URL or query string carries a credential, give the
Service a `redact` — _core scrubs the URL with it before any failure message
reaches the model.
"""

from __future__ import annotations

from . import lidarr, nzb, plex, radarr, sonarr, tmdb
from ._core import register_service

SERVICES = [
    radarr.SERVICE,
    sonarr.SERVICE,
    lidarr.SERVICE,
    plex.SERVICE,
    nzb.SERVICE,
    tmdb.SERVICE,
]


def register(ctx) -> None:
    for svc in SERVICES:
        register_service(ctx, svc)
