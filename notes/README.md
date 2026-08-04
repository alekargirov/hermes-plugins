# notes

Hermes plugin for the notes vault (notes-srv). Registers nine `notes_*` tools
under its own `notes` toolset and calls notes-srv's **existing `/api/v2` REST
surface** directly.

Tool descriptions port **verbatim** from `/home/repos/srv-mcp-yaml/notes.yaml`
(READ-ONLY — it still flows to prod through the MCP gate). Descriptions are the
agent's only guidance; do not paraphrase them.

## Why there is no `/api/agent/tools` and no `NOTES_USER_ID`

The consolidation spec says a bridge means "the app grows `POST
/api/agent/tools`". **notes-srv is the deliberate exception.**

notes-srv already has `/api/v2` — its own CLAUDE.md calls it "the public surface
for scripts, agents and MCP tools". It has **no users, no authentication and no
per-user data**. Its one auth rule is that the `X-API-Key` string *is* the
writable top-level folder, enforced in `api/lib/vault.ts`. Building a second
agent surface over the same functions would give that scoping rule a second
place to be got wrong.

So the key is the identity. notes-srv's own reply handler says it outright:

> The key is the identity: a reply written with the "fin" key is authored by fin.

`notes.yaml` sends an `X-User-Id` header alongside the key; the app reads only
`X-API-Key` and ignores it. This plugin therefore sends only the key.

**`NOTES_API_KEY` is load-bearing, not merely a credential.** It decides which
folder the agent may write to. Each profile needs its **own** key — a shared one
means every agent writes into one folder as one identity, which is exactly the
isolation this design exists to provide.

## Profile .env

- `NOTES_URL` — notes-srv base URL (dev: `http://notes:3000`; a trailing slash
  is fine, it is stripped).
- `NOTES_API_KEY` — this profile's key, which is also its writable top-level
  folder. Omit it and the plugin still loads: reads are open, every write comes
  back as a 403 refusal.

## Required config.yaml stanza

```yaml
plugins:
  enabled:
    - notes
platform_toolsets:
  <platform>:
    - notes
```

`notes` is the plugin's OWN toolset. Never fold it into a shared one: when
`fin3` shared `todo`, the model read hermes' own todo schema and told alek
`fin3_update_category` "only supports target and content", refusing a change the
tool plainly supports.

## Tools (9)

Reads — `notes_tree`, `notes_list`, `notes_read`, `notes_search`,
`notes_comments`.

Writes — `notes_write`, `notes_comment_reply`, `notes_move`, `notes_delete`.

`notes_delete` is included at alek's explicit direction (2026-08-04): it is a
soft delete and agents have not misused it. This differs from `fin3-bridge`,
where delete tools must not exist at all.

Agents may **reply** to comment threads but never open one — that is a rail in
the app, not a prompt: `addReply` 404s when no root thread exists on the anchor,
and `/api/v2` exposes no thread-creation endpoint.

## Failure behaviour

Every handler returns a JSON string and **never raises**. An HTTP error becomes
`{"ok": false, "message": "notes HTTP 403: ..."}` and an unreachable host
becomes `{"ok": false, "message": "notes unreachable: ..."}`, so a refusal the
model can act on reaches it instead of the turn dying.

## After changing this file

**hermes loads plugins at process start.** Copying this plugin to an agent host
changes nothing until that agent is restarted, and every process holding a copy
of a profile must be restarted — a stale copy offers tools the app has changed
or misses tools entirely. On 2026-08-01 that gap cost alek three account updates
on the fin3 side.

Check the log after any change:

```
[notes] registered 9 tools (v2026-08-04.9) -> http://notes:3000 as key <folder>
```

Nine is the number. Zero means the toolset key never reached
`platform_toolsets`; any other count means a stale copy.

## Tests

```bash
cd /home/repos/hermes-plugins && python3 -m pytest tests/test_notes.py -v
```

These prove the URL builder, the header, and the refusal path — nothing more. A
green suite is not a working plugin: verify a real turn returns real data, and
that a write outside the profile's own folder is refused.
