"""nzb — NZBGet, over JSON-RPC.

Ported from the standalone nzb plugin on 2026-08-15.

TWO THINGS HERE ARE DELIBERATE AND MUST STAY THAT WAY:

1. The PASSWORD is in the URL path ({NZB_URL}{user}:{pass}/jsonrpc), so the URL
   can never appear in anything returned to the model. `_redact` below is
   handed to the Service and _core scrubs the URL before it reaches any
   message. There is no key guard because there is no key header — the
   credential is rendered into the path by the template.

2. The RPC method is baked into each tool's body. The model supplies
   parameters, never the method, so it cannot invoke arbitrary NZBGet RPCs.
   tests/test_direct_plugins.py enforces both.

Env (profile .env):
  NZB_URL       needs its TRAILING SLASH, e.g. http://nzb:6789/
  NZB_USER
  NZB_PASSWORD
"""

from __future__ import annotations

import re

from ._core import Service, Tool, _schema, _n, _s

PLUGIN_VERSION = "2026-08-05.7"


def _redact(u: str) -> str:
    """The PASSWORD is in the URL path ({NZB_URL}{user}:{pass}/jsonrpc), so the
    URL can never appear in anything returned to the model."""
    return re.sub(r"(https?://[^/]+/)[^/]*:[^/]*/", r"\1***:***/", u)


TOOLS = [
    Tool(
        "nzb_status",
        "NZBGet server status — download rate, remaining size, paused state, free disk space.",
        _schema({}),
        "POST",
        "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        body="{\"method\":\"status\"}",
        select=None,
        limit=None,
    ),
    Tool(
        "nzb_queue",
        "List the current NZBGet download queue (active and queued items with NZBID, name, size, progress). Use NZBID with nzb_delete.",
        _schema({}),
        "POST",
        "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        body="{\"method\":\"listgroups\"}",
        select=None,
        limit=None,
    ),
    Tool(
        "nzb_history",
        "NZBGet download history (completed/failed items). Returns the full history — can be long.",
        _schema({}),
        "POST",
        "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        body="{\"method\":\"history\",\"params\":[false]}",
        select=None,
        limit=None,
    ),
    Tool(
        "nzb_add",
        "Add a download to NZBGet by NZB file URL. NZBGet fetches the URL itself. Optionally set a category (e.g. movies, tv, music) and a name.",
        _schema(
            {
                "url": _s("Direct URL to the .nzb file"),
                "category": _s("NZBGet category (optional, e.g. movies, tv, music)"),
                "name": _s("Filename to store as (optional — derived from the URL if empty)"),
            },
            ["url"],
        ),
        "POST",
        "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        body="{\"method\":\"append\",\"params\":[\"{arg.name|}\",\"{arg.url}\",\"{arg.category|}\",0,false,false,\"\",0,\"SCORE\"]}",
        select=None,
        limit=None,
    ),
    Tool(
        "nzb_delete",
        "Delete a queue item from NZBGet by NZBID (from nzb_queue). Removes the download, keeps nothing.",
        _schema(
            {
                "id": _n("NZBID from nzb_queue"),
            },
            ["id"],
        ),
        "POST",
        "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        body="{\"method\":\"editqueue\",\"params\":[\"GroupDelete\",0,\"\",[{arg.id}]]}",
        select=None,
        limit=None,
    ),
    Tool(
        "nzb_pause",
        "Pause all NZBGet downloads.",
        _schema({}),
        "POST",
        "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        body="{\"method\":\"pausedownload\"}",
        select=None,
        limit=None,
    ),
    Tool(
        "nzb_resume",
        "Resume all NZBGet downloads.",
        _schema({}),
        "POST",
        "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        body="{\"method\":\"resumedownload\"}",
        select=None,
        limit=None,
    ),
]


SERVICE = Service(
    name="nzb",
    url_env="NZB_URL",
    key_env=None,
    auth_header=None,
    accept_json=False,
    redact=_redact,
    log_note=None,
    version=PLUGIN_VERSION,
    tools=TOOLS,
)
