# scout

Hermes plugin for the Scout research store (scout-srv). Registers nine
`scout_*` tools under its own `scout` toolset and calls scout-srv's
**existing `/api/v1` REST surface** directly.

Tool descriptions are ported **byte-identical** from
`/home/apps/scout-srv/src/lib/server/mcp.ts`. That file is scout-srv's own
in-process MCP surface — it dispatches into the same `apiRouter` that serves
REST, so the two never drift from each other. This plugin is a second,
independent caller of that same REST surface, over HTTP instead of in-process.
Two languages means two copies: editing one means editing the other, and a
drift means the agent is told something untrue about a tool it's about to
call.

## Auth: a shared secret, not an identity

scout is single-user. `X-Api-Key` is a shared secret checked against
`SCOUT_API_KEY` on the server — it does not select a user or a scope the way
notes-srv's key selects a writable folder. Every Scout agent profile can use
the same key; there is no per-profile isolation to preserve.

## Profile .env

- `SCOUT_URL` — scout-srv base URL (dev default: `http://scout:3026`; a
  trailing slash is fine, it is stripped).
- `SCOUT_API_KEY` — the shared key. Omit it and the plugin still loads: every
  call refuses by name (`SCOUT_API_KEY is not set in this agent's .env —
  cannot call scout.`) instead of going out and coming back a bare 401.

## Required config.yaml stanza

```yaml
plugins:
  enabled:
    - scout
platform_toolsets:
  <platform>:
    - scout
```

`scout` is the plugin's OWN toolset. Never fold it into a shared one — see
notes/README.md for the `fin3`/`todo` incident this convention exists to
prevent.

## Tools (9)

Writes — `scout_subject_upsert`, `scout_fact_add`, `scout_mission_create`.

Reads — `scout_mission_list`, `scout_search`, `scout_nearby`, `scout_score`,
`scout_stale`, `scout_rejected`.

There is no delete tool: scout-srv's REST surface does not expose one, so
none is wrapped here.

### Two tools reshape their arguments before the REST call

Both mirror what `mcp.ts` itself does in-process, so a Python caller and a
same-process MCP caller behave identically:

- **`scout_nearby`** takes separate `lat`/`lon` and folds them into `/search`'s
  single `near="lat,lon"` query param before dispatch.
- **`scout_mission_list`**'s `rootId` never reaches the REST call — `GET
  /missions` always returns the whole forest. `rootId` instead filters the
  already-returned tree down to one subtree, client-side, after the fact.

### Unverified data is a first-class rail, not a footnote

Several tool descriptions carry explicit instructions about coordinates and
citations — copied verbatim from `mcp.ts`, not paraphrased here:

- Coordinates supplied to `scout_subject_upsert` are stored **unverified**
  unless a human confirms them; the model must say so when reporting back.
- `verified:true` requires lat/lon and is refused with a 400 otherwise —
  verification is a human action the model cannot assert its way into.
- A `researched` fact requires `sourceUrl`, refused with a 400 without one.
  Use `inferred` for reasoning/estimation, never `researched` without a real
  citation.
- `scout_search`, `scout_nearby` and `scout_score` all report `geomVerified`
  (or a `"pin unverified"` caveat) on results that depend on an unverified
  pin — the model is instructed to surface that caveat, not launder a match
  against unconfirmed geometry as a clean hit.

These are read straight into the descriptions the model sees; this plugin
does not re-derive or enforce them independently. scout-srv's `apiRouter`
enforces the hard rules (400/422 refusals) regardless of what the model does
with the guidance.

## Failure behaviour

Every handler returns a plain string and **never raises**:

- Missing key: a named refusal, no request sent —
  `SCOUT_API_KEY is not set in this agent's .env — cannot call scout.`
- HTTP error: `scout <code> at <url>: <body...>` (body truncated to 400 chars).
- Unreachable host: `scout unreachable at <url> (SCOUT_URL): <err>` — the URL
  and the variable name are both in the message on purpose; see
  `notes/__init__.py`'s comment on the sibling incident that convention
  exists to prevent.

## After changing this file

**hermes loads plugins at process start.** Copying this plugin to an agent
host changes nothing until that agent is restarted, and every process holding
a copy of a profile must be restarted — a stale copy offers tools the app has
changed, or misses tools entirely.

Check the log after any change:

```
[scout] registered 9 tools (v2026-08-08.1) -> http://scout:3026 as key (set)
```

Nine is the number. Zero means the toolset key never reached
`platform_toolsets`; any other count means a stale copy.

## Tests

```bash
cd /home/repos/hermes-plugins && python3 -m pytest tests/test_scout.py -v
```

These prove the URL/path builder, the header, the refusal path, and the two
argument-reshaping tools (`scout_nearby`, `scout_mission_list`) — nothing
more. A green suite is not a working plugin: verify a real turn reaches the
database, and that the missing-key path returns the named refusal rather than
a raw 401.
