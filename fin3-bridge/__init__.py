"""fin3-bridge — forwards every fin3_* tool call to fin-srv-v3's tool endpoint.

The plugin holds NO logic beyond forwarding. Identity rides in two places,
checked against each other server-side:
  - user_id: this profile's own FIN3_USER_ID (from the profile .env, put there
    by the operator — the model never sees it and cannot set it);
  - session_id: the dispatch context (the turn id fin3 minted), delivered to
    the handler in code, never via the model.
fin-srv-v3 resolves the turn and refuses any call where they disagree.

Every tool registers under toolset="fin3" — its OWN toolset, not `todo`.

The original note here said a plugin-named toolset resolves to ZERO tools,
so everything went into `todo`. That is stale for this hermes:
hermes_cli/tools_config.py::_get_effective_configurable_toolsets() merges
plugin-provided toolsets in, grouped by whatever key the plugin registered
with. Sharing `todo` had a real cost — the model bled hermes' own todo tool
schema into ours and told alek fin3_update_category "only supports target and
content", refusing a change the tool plainly supports. Check the container log
says "registered 33 tools" after any change here; zero means the toolset key
is not reaching platform_toolsets.

Env (profile .env): FIN3_URL (e.g. http://127.0.0.1:3022), FIN3_TOOL_KEY
(shared with fin-srv-v3's TOOL_ENDPOINT_KEY), FIN3_USER_ID (real-user
profiles only — the default `fin3` profile deliberately has none and can
therefore act for nobody).

Tool descriptions port VERBATIM from srv-mcp-yaml/fin.yaml (they are the
agent's only guidance) with fin_ -> fin3_ and tg-related text dropped.
"""

import json
import os
import urllib.error
import urllib.request


def _env(name: str) -> str:
    """Profile-scoped credential read. The multiplexed gateway (hermes 0.18+)
    keeps each profile's .env in an isolated per-turn secret scope and never
    mutates os.environ — a bare os.environ.get returns another profile's value
    or nothing. get_secret honours the scope; on a single-profile gateway
    (prod: one container per user) it falls through to os.environ, so both
    modes work. Fail-open to os.environ only when no scope API is available.
    """
    try:
        from agent.secret_scope import get_secret

        val = get_secret(name, "")
    except Exception:
        val = os.environ.get(name, "")
    return val or ""


def _forward(tool: str, args: dict, session_id) -> str:
    url = _env("FIN3_URL").rstrip("/") + "/api/agent/tools"
    payload = {
        "tool": tool,
        "session_id": session_id,
        "user_id": _env("FIN3_USER_ID"),
        "args": args or {},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "x-fin3-key": _env("FIN3_TOOL_KEY"),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        return json.dumps({"ok": False, "message": f"endpoint HTTP {e.code}: {e.read().decode()[:300]}"})
    except Exception as e:  # noqa: BLE001 — surface the failure to the agent, never crash the turn
        return json.dumps({"ok": False, "message": f"fin3-bridge unreachable: {e}"})


def _make_handler(tool: str):
    def _handler(args: dict, session_id: str = None, **kwargs) -> str:
        return _forward(tool, args, session_id)

    return _handler


def _s(d):
    return {"type": "string", "description": d}


def _n(d):
    return {"type": "number", "description": d}


def _b(d):
    return {"type": "boolean", "description": d}


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


_LIMIT = {"limit": _n("Max entries (default 50, max 500)")}
_CUR_OPT = {"currency": _s("Currency code (EUR) or symbol (€) — or pass currencyId instead. Omit for the user's display currency. NEVER omit when the utterance names a currency ('25 US dollars' -> USD, '30 AUD' -> AUD).")}
_CUR_CHG = {"currency": _s("Currency code (EUR) or symbol (€) — or pass currencyId instead")}
_FREQ_REQ = {"freqId": _n("Frequency id from fin3_reference (frequencyId also accepted)")}
_FREQ_CHG = {"freqId": _n("New frequency id — pass it whenever the utterance implies a period ('a year' -> Annually, 'per month' -> Monthly); an amount with a period is an amount AND frequency change")}
_ACTIVE_ADD = {"active": _b("False to add it disabled (default true)")}
_NOTES = {"notes": _s("Any free-text detail worth keeping")}

TOOLS = [
    # ── Reads ──
    (
        "fin3_overview",
        "THE money question answerer — call this whenever the user asks \"how "
        "much do I have / can I spend / what's my balance\". Returns the whole "
        "assembled dashboard: display currency + frequency, totals (income, "
        "recurring expenses, tracked spending, disposable, remainder), bank "
        "accounts, investments, net worth, and recent tracked expenses — all "
        "amounts already converted to display currency at display frequency. "
        "NEVER compute or estimate balances yourself; read them here.",
        _schema({}),
    ),
    (
        "fin3_income",
        "List the user's income sources (name, amount, currency, frequency). These are RECURRING sources like salary — for one-off income entries see fin3_tracked_income.",
        _schema({}),
    ),
    (
        "fin3_tracked_income",
        "List one-off (tracked) income entries, newest first — individual sums received, as opposed to recurring income sources (fin3_income).",
        _schema({**_LIMIT}),
    ),
    (
        "fin3_recurring",
        "List the user's recurring expenses (rent, subscriptions, ...) with amount, currency, frequency and category. For which of them are due soon, fin3_recurring_due is the sharper read.",
        _schema({}),
    ),
    (
        "fin3_recurring_due",
        "List recurring expenses with their next due date and bucket — call this for \"what bills are coming up\".",
        _schema({}),
    ),
    (
        "fin3_expenses",
        "List tracked (one-off) expenses, newest first, with category and currency. This is the spending log — recurring expenses live in fin3_recurring.",
        _schema({**_LIMIT}),
    ),
    (
        "fin3_accounts",
        "List bank accounts with balances and currencies. Balances here are the STORED values — for the full picture (net worth, disposable) use fin3_overview.",
        _schema({}),
    ),
    (
        "fin3_investments",
        "List investments with current values and currencies.",
        _schema({}),
    ),
    (
        "fin3_categories",
        "List the user's expense/income categories (id, name, emoji — that is the "
        "category's ICON, settable via fin3_update_category — parentId "
        "for subcategories). Call this BEFORE logging an expense — categoryId "
        "is required there and must be one of these ids. Pick the closest "
        "match; if nothing fits, create one with fin3_add_category first.",
        _schema({}),
    ),
    (
        "fin3_reference",
        "Global reference data: all currencies (id, code, symbol, rateToBase), "
        "all frequencies (id + name — the freqId values for income/recurring/"
        "settings writes), and the user's categories. Call this when you need a "
        "currencyId or freqId you don't have yet.",
        _schema({}),
    ),
    (
        "fin3_settings",
        "The user's settings — display currencyId, display freqId, cycleStart, timezone, alertThreshold, language, persona. Display currency/frequency shape every number in fin3_overview.",
        _schema({}),
    ),
    # ── Writes: income ──
    (
        "fin3_add_income",
        "Add a RECURRING income SOURCE that pays out again and again — a salary, "
        "a stipend, rent received. STOP and use fin3_log_tracked_income instead "
        "whenever the money arrived ONCE: a sale, a refund, a gift, a bonus, "
        "'I sold my bike', 'I got paid for a job'. The test is whether it will "
        "pay again on a schedule; if it will not, it is NOT an income source. "
        "Adding a one-off here is a real error, not a formatting choice — it "
        "inflates the person's income in every future cycle, for ever. There is "
        "no 'one-off' frequency: annually is still recurring. Get freqId from "
        "fin3_reference.",
        _schema(
            {
                "name": _s("Source name, e.g. 'Salary'"),
                "recurring": _b("Must be true, and only set it when this genuinely pays out again and again on a schedule. A sale, refund, gift or bonus is NOT recurring — it is refused here and belongs in fin3_log_tracked_income"),
                "amount": _n("Amount per frequency period"),
                **_CUR_OPT,
                **_FREQ_REQ,
                **_ACTIVE_ADD,
            },
            ["name", "recurring", "amount", "freqId"],
        ),
    ),
    (
        "fin3_update_income",
        "Patch an income source (id from fin3_income) — only the fields given "
        "are changed. If the utterance implies a period ('a year', 'per month', "
        "'weekly'), pass the matching freqId from the reference data — an "
        "amount with a period is an amount AND frequency change.",
        _schema(
            {
                "id": _n("The income's id, from fin3_income"),
                "name": _s("New name"),
                "amount": _n("New amount per period"),
                **_CUR_CHG,
                **_FREQ_CHG,
                "active": _b("False to deactivate (deactivated rows drop out of totals)"),
            },
            ["id"],
        ),
    ),
    (
        "fin3_log_tracked_income",
        "Log a one-off income entry — a sum that arrived ONCE and will not repeat: a sale, a refund, a gift, a bonus, a side job. THIS is the tool for 'I sold my bike for 120' or 'I got paid 300 for that job'. Only use fin3_add_income instead when it genuinely recurs on a schedule, like a salary.",
        _schema(
            {
                "description": _s("What it was, in a few words"),
                "amount": _n("Amount received"),
                **_CUR_OPT,
                "categoryId": _n("Category id from fin3_categories (optional for income)"),
                "subcategoryId": _n("Subcategory id from fin3_categories"),
                **_NOTES,
                "incomeDate": _s("Date received, yyyy-MM-dd (default today in the user's timezone)"),
            },
            ["description", "amount"],
        ),
    ),
    # ── Writes: expenses ──
    (
        "fin3_log_expense",
        "Log a one-off expense — the workhorse write, use it whenever the user "
        "says they spent money. categoryId is REQUIRED (an uncategorised "
        "expense is a 400): call fin3_categories first and pick the closest id — "
        "obvious mappings (fuel -> Transport) need no question, just log and "
        "mention the mapping; only ask or fin3_add_category when nothing fits. "
        "Backdating: compute the real yyyy-MM-dd date from the current date "
        "('yesterday' = today minus one day) and pass it in expenseDate — "
        "never leave a stated date implied.",
        _schema(
            {
                "description": _s("What was bought, in a few words (e.g. 'groceries at Lidl')"),
                "amount": _n("Amount spent"),
                **_CUR_OPT,
                "categoryId": _n("REQUIRED category id from fin3_categories — never omit, never invent"),
                "subcategoryId": _n("Subcategory id from fin3_categories"),
                **_NOTES,
                "expenseDate": _s("Date spent, yyyy-MM-dd (default today in the user's timezone) — compute and pass the real date when the utterance says 'yesterday', 'on Friday', etc."),
            },
            ["description", "amount", "categoryId"],
        ),
    ),
    (
        "fin3_update_expense",
        "Correct a logged expense (id from fin3_expenses) — amount, description, category, date, etc. Only the fields given are changed; a passed categoryId must exist (fin3_categories).",
        _schema(
            {
                "id": _n("The expense's id, from fin3_expenses"),
                "description": _s("New description"),
                "amount": _n("New amount"),
                **_CUR_CHG,
                "categoryId": _n("New category id from fin3_categories (must exist; null is refused — an uncategorised expense vanishes from list views)"),
                "subcategoryId": _n("New subcategory id"),
                "notes": _s("New notes"),
                "expenseDate": _s("New date, yyyy-MM-dd"),
            },
            ["id"],
        ),
    ),
    # ── Writes: recurring, accounts, investments, categories ──
    (
        "fin3_add_recurring",
        "Add a recurring expense (rent, subscription, insurance) — it then "
        "counts against every paycycle's totals. For a one-off purchase use "
        "fin3_log_expense. Get freqId from fin3_reference.",
        _schema(
            {
                "name": _s("Expense name, e.g. 'Rent'"),
                "amount": _n("Amount per frequency period"),
                **_CUR_OPT,
                **_FREQ_REQ,
                "categoryId": _n("Category id from fin3_categories"),
                "subcategoryId": _n("Subcategory id from fin3_categories"),
                **_NOTES,
                "startDate": _s("First occurrence, yyyy-MM-dd"),
                "endDate": _s("Last occurrence, yyyy-MM-dd (omit for open-ended)"),
                **_ACTIVE_ADD,
            },
            ["name", "amount", "freqId"],
        ),
    ),
    (
        "fin3_update_recurring",
        "Patch a recurring expense (id from fin3_recurring) — only the fields "
        "given are changed. active=false is the way to stop one without "
        "deleting history.",
        _schema(
            {
                "id": _n("The recurring expense's id, from fin3_recurring"),
                "name": _s("New name"),
                "amount": _n("New amount per period"),
                **_CUR_CHG,
                "freqId": _n("New frequency id from fin3_reference"),
                "categoryId": _n("New category id from fin3_categories (null clears)"),
                "subcategoryId": _n("New subcategory id"),
                "notes": _s("New notes"),
                "startDate": _s("New start date, yyyy-MM-dd"),
                "endDate": _s("New end date, yyyy-MM-dd"),
                "active": _b("False to deactivate"),
            },
            ["id"],
        ),
    ),
    (
        "fin3_add_account",
        "Add a bank account with its current balance. Updating the balance later is fin3_update_account — account balances are stated, never computed from expenses.",
        _schema(
            {
                "name": _s("Account name, e.g. 'DSK checking'"),
                "balance": _n("Current balance"),
                **_CUR_OPT,
                "accountType": _s("Free-form type, e.g. 'checking', 'savings', 'cash'"),
                **_ACTIVE_ADD,
            },
            ["name", "balance"],
        ),
    ),
    (
        "fin3_update_account",
        "Patch an account (id from fin3_accounts) — rename, restate the "
        "balance, change currency/type, or deactivate. Only the fields given "
        "are changed.",
        _schema(
            {
                "id": _n("The account's id, from fin3_accounts"),
                "name": _s("New name"),
                "balance": _n("Restated current balance"),
                **_CUR_CHG,
                "accountType": _s("New free-form type"),
                "active": _b("False to deactivate"),
            },
            ["id"],
        ),
    ),
    (
        "fin3_add_investment",
        "Add an investment holding with its current value (stocks, crypto, pension fund, ...). Values are stated, never computed — restate them later with fin3_update_investment.",
        _schema(
            {
                "name": _s("Holding name, e.g. 'S&P 500 ETF'"),
                "value": _n("Current value"),
                **_CUR_OPT,
                **_NOTES,
                **_ACTIVE_ADD,
            },
            ["name", "value"],
        ),
    ),
    (
        "fin3_update_investment",
        "Patch an investment (id from fin3_investments) — restate value, rename, "
        "change currency, deactivate. Only the fields given are changed. value "
        "vs notes: value is the holding's current worth AS A NUMBER; notes is "
        "free text. A statement like 'this is now worth X' or 'this went up to "
        "X' ALWAYS goes to value, never to notes.",
        _schema(
            {
                "id": _n("The investment's id, from fin3_investments"),
                "name": _s("New name"),
                "value": _n("Restated current worth as a NUMBER — 'this is now worth X' always lands here, never in notes"),
                **_CUR_CHG,
                "notes": _s("Free-text detail only — never a value restatement"),
                "active": _b("False to deactivate"),
            },
            ["id"],
        ),
    ),
    (
        "fin3_add_category",
        "Create a spending/income category when nothing in fin3_categories fits — then use its id in fin3_log_expense. Pass parentId (an existing category id) to make it a subcategory.",
        _schema(
            {
                "name": _s("Category name, e.g. 'Eating out'"),
                "emoji": _s("One emoji for the UI, e.g. '🍕'"),
                "parentId": _n("Parent category id from fin3_categories — makes this a subcategory (null clears)"),
                "sortOrder": _n("Display order, non-negative integer (0 is valid)"),
                **_ACTIVE_ADD,
            },
            ["name"],
        ),
    ),
    (
        "fin3_update_tracked_income",
        "Correct a one-off income entry (id from fin3_tracked_income) — amount, description, date, category. Only the fields given change. Use this for \"actually that sale was 450\"; a pay rise on a recurring source is fin3_update_income instead.",
        _schema(
            {
                "id": _n("The entry's id, from fin3_tracked_income"),
                "description": _s("New description"),
                "amount": _n("New amount"),
                "categoryId": _n("New category id from fin3_categories (null clears — income may be uncategorised)"),
                "subcategoryId": _n("New subcategory id (null clears)"),
                "incomeDate": _s("New date, yyyy-MM-dd"),
                **_CUR_CHG,
                **_NOTES,
            },
            ["id"],
        ),
    ),
    (
        "fin3_update_category",
        "Patch a category (id from fin3_categories) — rename, set its ICON (the emoji field), re-parent it, reorder it, or deactivate it with active=false. Categories DO have an icon: it is the `emoji` argument here, so 'add icons to my categories' is a loop of calls to this tool, one per category. Deactivating keeps past expenses intact; it only stops the category being offered for new ones.",
        _schema(
            {
                "id": _n("The category's id, from fin3_categories"),
                "name": _s("New name"),
                "emoji": _s("The category's ICON/emoji, e.g. '🍕' — one emoji character, shown on the spending breakdown. This IS the icon field: 'add an icon to this category' means setting this"),
                "parentId": _n("New parent category id, making this a subcategory (null makes it top-level)"),
                "sortOrder": _n("New display order, non-negative integer"),
                "active": _b("False to deactivate"),
            },
            ["id"],
        ),
    ),
    (
        "fin3_set_category_icon",
        "Set a category's ICON (its emoji), e.g. a car on Transport. THIS is the tool for \"add an icon to this category\" or \"give my categories icons\" — categories DO support icons and this sets them. One call per category; loop over fin3_categories to do them all.",
        _schema(
            {
                "id": _n("The category's id, from fin3_categories"),
                "icon": _s("One emoji character, e.g. '🚗'. Pass an empty string to clear it"),
            },
            ["id", "icon"],
        ),
    ),
    (
        "fin3_update_settings",
        "Change the user's settings — display currency, display frequency, pay-cycle start, timezone, low-balance alert threshold, language, persona. Only the fields given change. The display currency and frequency shape EVERY figure on the home page and in fin3_overview, so change them only when the user actually asks.",
        _schema(
            {
                "currency": _s("New display currency — code (EUR) or symbol (€), or pass currencyId"),
                "freqId": _n("New display frequency id from fin3_reference — the period totals are shown at"),
                "cycleStart": _s("Pay-cycle start date, yyyy-MM-dd (null clears)"),
                "timezone": _s("A real IANA timezone, e.g. 'Europe/Sofia' — an unknown name is refused"),
                "alertThreshold": _n("Balance threshold for low-balance alerts, >= 0"),
                "language": _s("Language code, e.g. 'bg' (null clears)"),
                "persona": _s("Assistant persona note, 32 chars max (null clears)"),
            },
            [],
        ),
    ),
    # ── IOUs (debts between two real people) ──
    # Lifecycle in one line: create -> the OTHER person accepts or rejects ->
    # payments recorded until it settles. There is no claim/confirm step: a
    # payment is a tally of money that changed hands, not a request.
    (
        "fin3_people",
        "List the people this user can raise an IOU with (id, name). The `id` here is the personUserId for fin3_create_iou — never guess it, and never pass the user's own id.",
        _schema({}),
    ),
    (
        "fin3_ious",
        "List this user's IOUs in both directions with status: pending (waiting to be accepted), accepted (a live debt), settled, rejected, cancelled. Carries amount, paid, outstanding, the counterparty, and awaitingYou — true when THIS user is the one who has to accept or reject it. Use the ids from here for every IOU write.",
        _schema({}),
    ),
    (
        "fin3_iou_summary",
        "The IOU position: gross outstanding per direction per currency, the net per person, and how many are waiting on this user versus on the other side. Sharper than the raw fin3_ious list for \"what am I owed / what do I owe\".",
        _schema({}),
    ),
    (
        "fin3_create_iou",
        "Record a debt between this user and someone from fin3_people. ALWAYS call fin3_people first and copy BOTH the id and the name from the SAME row — pass them as personUserId and personName. If they disagree the write is refused, because booking a debt against the wrong person is the worst mistake this tool can make. It starts PENDING and does NOT count towards anybody's totals until the other person accepts — say so in your reply rather than reporting it as done. Use direction 'they_owe_me' when the user paid for someone else, 'i_owe_them' when someone paid for the user.",
        _schema(
            {
                "personUserId": _n("The other person's id, from fin3_people — never guess it. Their NAME is accepted here too if you only have that"),
                "personName": _s("That person's name from the SAME fin3_people row. Checked against personUserId; a mismatch is refused"),
                "direction": _s("REQUIRED. 'they_owe_me' when the user is OWED ('Lili owes me 25', 'I paid for her lunch'); 'i_owe_them' when the USER owes ('I owe Kristian 40', 'he paid for my dinner'). There is no default — getting this backwards books the debt the wrong way round, so read the utterance again before choosing"),
                "amount": _n("Amount owed, positive"),
                "description": _s("What the debt is for, in a few words"),
                **_CUR_OPT,
            },
            ["personUserId", "personName", "direction", "amount"],
        ),
    ),
    (
        "fin3_respond_iou",
        "Accept or reject a PENDING IOU the other person raised (id from fin3_ious, where awaitingYou is true). Only the person who did NOT raise it can answer. Accepting makes it a live debt that counts in the totals; rejecting closes it.",
        _schema(
            {
                "id": _n("The IOU's id, from fin3_ious"),
                "accept": _b("true to accept the debt, false to reject it"),
            },
            ["id", "accept"],
        ),
    ),
    (
        "fin3_pay_iou",
        "Record money that changed hands against an accepted IOU (id from fin3_ious) — partial or the whole lot. Either party can record it. The IOU settles automatically once the full amount is covered; the tool's message says how much is still outstanding, so quote that rather than assuming it is cleared.",
        _schema(
            {
                "id": _n("The IOU's id, from fin3_ious"),
                "amount": _n("Amount paid, positive. May be less than the total; more than the outstanding balance is refused"),
            },
            ["id", "amount"],
        ),
    ),
    (
        "fin3_cancel_iou",
        "Cancel an IOU (id from fin3_ious). A pending one can be withdrawn by whoever raised it — use this when it was logged by mistake, and fin3_respond_iou with accept=false when the OTHER person is refusing it. An accepted one can only be written off by the person owed, and only while nothing has been paid.",
        _schema({"id": _n("The IOU's id, from fin3_ious")}, ["id"]),
    ),
]


def register(ctx) -> None:
    for name, description, schema in TOOLS:
        ctx.register_tool(
            name=name,
            toolset="fin3",
            schema=schema,
            handler=_make_handler(name),
            description=description,
        )
    print(
        f"[fin3-bridge] registered {len(TOOLS)} tools -> "
        f"{os.environ.get('FIN3_URL', '(FIN3_URL unset)')} "
        f"as user {os.environ.get('FIN3_USER_ID', '(none — impotent profile)')}",
        flush=True,
    )
