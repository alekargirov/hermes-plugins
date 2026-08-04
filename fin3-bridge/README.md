# fin3-bridge

Hermes plugin for fin-srv-v3. Registers the shipped `fin3_*` tool set and
forwards every call to fin-srv-v3's `POST /api/agent/tools` with:

- `session_id` — the dispatch context (the turn id fin3 minted), delivered to
  the handler in code, never via the model;
- `user_id` — the profile's own `FIN3_USER_ID` from its `.env` (the model
  never sees it);
- header `x-fin3-key: $FIN3_TOOL_KEY` — shared with fin-srv-v3's
  `TOOL_ENDPOINT_KEY`.

The plugin holds **no logic beyond forwarding**. fin-srv-v3 resolves the turn
and refuses any call where turn user and `FIN3_USER_ID` disagree — identity is
enforced server-side, in exactly one place.

Tool descriptions port **verbatim** from `/home/repos/srv-mcp-yaml/fin.yaml`
(READ-ONLY — it flows to prod) with `fin_` → `fin3_` and tg-related text
dropped. Descriptions are the agent's only guidance; do not paraphrase them.

Shipped set (34 tools).

Reads: `fin3_overview`, `fin3_income`, `fin3_tracked_income`, `fin3_recurring`,
`fin3_recurring_due`, `fin3_expenses`, `fin3_accounts`, `fin3_investments`,
`fin3_categories`, `fin3_reference`, `fin3_settings`, `fin3_people`,
`fin3_ious`, `fin3_iou_summary`.

Writes: `fin3_add_income`, `fin3_update_income`, `fin3_log_tracked_income`,
`fin3_update_tracked_income`, `fin3_log_expense`, `fin3_update_expense`,
`fin3_add_recurring`, `fin3_update_recurring`, `fin3_add_investment`,
`fin3_update_investment`, `fin3_add_account`, `fin3_update_account`,
`fin3_add_category`, `fin3_update_category`, `fin3_set_category_icon`,
`fin3_update_settings`,
`fin3_create_iou`, `fin3_respond_iou`, `fin3_pay_iou`, `fin3_cancel_iou`.

**No delete tools — they must not exist.** `test/tool-parity.test.ts` asserts
that, and that this list matches the endpoint's `TOOLS` map exactly: they had
drifted once (`fin3_set_income_amount` lived in the endpoint and not here, so
only a tool-key holder could reach it).

Deliberately NOT ported from `fin.yaml`: `fin_analytics` (a JSON tool to read
numbers aloud is what made analytics useless in v1 and v2 — the /analytics page
visualises them instead), `fin_add_currency` (writes the GLOBAL currency list;
belongs to an admin, not a per-user agent), `fin_invite_person` /
`fin_connected_people` / `fin_revoke_person` (identity ops, and revoke unlinks a
Telegram account v3 doesn't have), and the IOU claim/confirm pair
`fin_repay_iou` / `fin_confirm_iou` / `fin_withdraw_repayment` — v3 records a
payment in one step, see the IOU note below.

**IOUs, where v3 deliberately differs from v2.** Every IOU starts *pending*
whichever direction it is in, and the person who did NOT raise it accepts or
rejects (v2 auto-accepted "I owe them"). A payment is one step: `fin3_pay_iou`
moves `paidAmount` and settles at full, either party may record it, and an
overpayment is refused with the real outstanding figure. The lifecycle lives in
`src/lib/server/ious.ts`, shared with the `/people` buttons, so the voice path
and the UI cannot disagree about who may do what.

This is the canonical copy of the plugin, living inside the canonical profile
at `hermes/profile/plugins/fin3-bridge/`. On dev it is also deployed to
`~/.hermes/profiles/{fin3,fin3-template,fin3-u2,fin3-u5,fin3-u11}/plugins/fin3-bridge/`.
Keep them in sync (the profiles do NOT share plugin dirs):

```bash
for p in fin3 fin3-template fin3-u2 fin3-u5 fin3-u11; do
  cp hermes/profile/plugins/fin3-bridge/{__init__.py,plugin.yaml} ~/.hermes/profiles/$p/plugins/fin3-bridge/
done
```

## Profile .env additions

- `FIN3_URL` — fin-srv-v3 base URL (dev: `http://127.0.0.1:3022`). All profiles.
- `FIN3_TOOL_KEY` — shared secret, all profiles.
- `FIN3_USER_ID` — real-user profiles only (`fin3-u2/u5/u11`). The default
  `fin3` profile deliberately has none: without it every forwarded call fails
  the server-side identity check, so the impotent default can act for nobody.

## Required config.yaml stanza

```yaml
plugins:
  enabled:
    - fin3-bridge
platform_toolsets:
  api_server:
    - fin3
    - session_search
    - memory
```

- `fin3` — the plugin's OWN toolset (`toolset="fin3"`), since 2026-07-30.
  **This changed.** It used to be `todo`, on the belief that a plugin-named
  toolset resolves to zero tools because `fin3` is not in
  `CONFIGURABLE_TOOLSETS`. That is not true for this hermes:
  `hermes_cli/tools_config.py::_get_effective_configurable_toolsets()` merges
  plugin-provided toolsets in, grouped by whatever key the plugin registered
  with.
  Sharing `todo` had a real cost. Asked to "add some icons to all the
  categories", the agent replied that `fin3_update_category` "only supports
  target and content" — `content` is a property of hermes' own **todo** tool.
  It was reading a neighbour's schema. After the split that reply changed, and
  after `fin3_set_category_icon` was added all 13 categories got icons in one
  turn.
  **Verify after any change here:** the container log must say
  `registered NN tools`, and a real turn must come back with data. Zero tools
  is the failure this note originally warned about, and it is still the thing
  to check for.
- `session_search` — lets the agent search past conversations.
- `memory` — required for per-user isolation: without it the api_server agent
  has no memory tool, so nothing is ever written to the profile's
  `memories/USER.md` and the per-user isolation the design rests on does not
  exist. (Verified 2026-07-28: with only `[todo, session_search]` a
  "remember this" turn wrote nothing; adding `memory` made
  `fin3-u2/memories/USER.md` persist while `fin3-u5` stayed empty.)

## Deliberately absent toolsets

`terminal`, `file`, `code_execution`, and `browser` stay **off**. This agent is
web-facing; giving it shell/filesystem/code-execution access is an unnecessary
attack surface. This is about exposure to the web, not about cross-user
leaking (per-user profiles handle that).

## Profile layout

- `fin3` — default profile, binds the gateway listener (`API_SERVER_*` in its
  `.env`), carries **no** `FIN3_USER_ID`: it must never act for anyone.
- `fin3-template` — clone source; no `API_SERVER_*`, no `FIN3_USER_ID`.
- `fin3-u2` / `fin3-u5` / `fin3-u11` — the three real users (alek, lili,
  kristian). Each has `FIN3_USER_ID=<id>` in `.env`, no `API_SERVER_*`, its own
  `memories/` and `state.db`. The service accounts in the `User` table get no
  profile.

The gateway runs multiplexed from the default profile only:

```bash
HERMES_HOME=~/.hermes/profiles/fin3 hermes gateway run --replace
```

`HERMES_HOME` is not optional: without it the gateway starts, logs "No
messaging platforms enabled" and never binds 8642, because the `API_SERVER_*`
env and `multiplex_profiles: true` live in the `fin3` profile.
`--replace` did NOT take the port from a running instance when tried on
2026-07-30 — the old process kept 8642 and two gateways ran at once. Stop the
old one and confirm `ss -lptn | grep 8642` is empty before starting.

`gateway.pid` contains JSON, not a bare pid — never `kill $(cat ...)`. After
any restart, `grep -c "already running" <log>` must be `0`.

**Every hermes process holding a copy of a profile must be restarted after the
plugin changes** — the per-user containers AND this gateway. A stale copy means
the agent offers tools the app has changed, or misses tools entirely.
