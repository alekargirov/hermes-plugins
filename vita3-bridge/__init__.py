"""vita3-bridge — forwards every vita3_* tool call to vita-srv-v3's tool endpoint.

The plugin holds NO logic beyond forwarding. Identity rides in two places,
checked against each other server-side:
  - user_id: this profile's own VITA3_USER_ID (from the profile .env, put there
    by the operator — the model never sees it and cannot set it);
  - session_id: the dispatch context (the turn id vita minted), delivered to
    the handler in code, never via the model.
vita-srv-v3 resolves the turn and refuses any call where they disagree.

VITA3_USER_ID is OPTIONAL. One container per person sets it and gets a
cross-check; ONE SHARED container for the whole household leaves it unset and
the turn alone decides — the app minted that turn for a logged-in user, and the
session id arrives in the dispatch context, never through the model. A shared
agent must therefore run with hermes MEMORY OFF: the profile's memory store is
per profile, not per person, and this is health data.

It also refuses any tool that is not in scope for the surface the person spoke
from: the home button cannot create or edit, a row mic can only touch its own
row. That gate lives in the app, not here — this file offers every tool and the
server decides. Which means a tool being LISTED is not a promise it will work
from where you are; read the refusal, it names what is available instead.

Every tool registers under toolset="vita3" — its OWN toolset, not `todo`.
Sharing `todo` let fin3's model bleed a neighbour's schema into ours.

Env (profile .env): VITA3_URL (e.g. http://10.0.1.198:3023), VITA3_TOOL_KEY
(shared with vita-srv-v3's TOOL_ENDPOINT_KEY), VITA3_USER_ID (the LOCAL
app_user id — real profiles only).
"""

import json
import os
import urllib.error
import urllib.request

# The tool surface this file was built for, stamped onto every call. hermes
# loads plugins at PROCESS START, so editing this file changes nothing until
# the agent is restarted. vita-srv-v3 compares this against its own
# PLUGIN_VERSION and says so, in its log and in the tool's answer. Bump BOTH
# whenever a tool is added or removed.
PLUGIN_VERSION = "2026-08-04.1"


def _env(name: str) -> str:
    """Profile-scoped credential read. The multiplexed gateway keeps each
    profile's .env in an isolated per-turn secret scope and never mutates
    os.environ — a bare os.environ.get returns another profile's value or
    nothing. On a single-profile gateway (one container per user) get_secret
    falls through to os.environ, so both modes work."""
    try:
        from agent.secret_scope import get_secret

        val = get_secret(name, "")
    except Exception:
        val = os.environ.get(name, "")
    return val or ""


def _forward(tool: str, args: dict, session_id) -> str:
    url = _env("VITA3_URL").rstrip("/") + "/api/agent/tools"
    payload = {
        "tool": tool,
        "session_id": session_id,
        "user_id": _env("VITA3_USER_ID"),
        "args": args or {},
        "plugin_version": PLUGIN_VERSION,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "x-vita3-key": _env("VITA3_TOOL_KEY"),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        return json.dumps({"ok": False, "message": f"endpoint HTTP {e.code}: {e.read().decode()[:300]}"})
    except Exception as e:  # noqa: BLE001 — surface the failure, never crash the turn
        return json.dumps({"ok": False, "message": f"vita3-bridge unreachable: {e}"})


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


_ITEM_ID = {
    "itemId": _n(
        "The item's numeric id, from vita3_stack or from the list you were given in the request. "
        "When the request names a row (\"item 14\"), that id is the answer — never look for another"
    )
}

_RULES = (
    "with_food, with_fat, with_small_meal, empty, bedtime, morning, anytime. "
    "Anything else is refused, so pick the closest of these seven or ask"
)

_CATEGORIES = (
    "legs, back, chest, shoulders, arms, core, full body, cardio, mobility. "
    "Anything else is refused, so pick the closest of these nine or ask"
)

_TYPES = (
    "cleanser, moisturiser, serum, sunscreen, treatment, deodorant. "
    "Anything else is refused, so pick the closest of these six or ask"
)

_CONDITION_KINDS = (
    "condition, allergy, intolerance. An allergy or intolerance is a FILTER — "
    "something they must NOT be given or have suggested, not just a diagnosis. "
    "Anything else is refused, so pick the closest of these three or ask"
)

_CONDITION_STATUSES = (
    "active, managed, resolved. Anything else is refused — and resolved is a "
    "status, not an erasure: nothing here is ever deleted"
)

# Rules live HERE, on the tool they constrain, not in the request envelope: at
# fourteen instruction lines in the envelope this model stopped calling tools
# altogether and reported their schemas as empty.
TOOLS = [
    (
        "vita3_stack",
        "The whole supplement stack in one call: every item with its id, dose, intake rule, "
        "schedule, whether it is due today and whether it has been taken. Also the day's counts. "
        "Call this ONLY if the request needs something the list you were given does not show "
        "(for example stopped items, with includeInactive) — otherwise use the list already in front of you.",
        _schema({"includeInactive": _b("true to include things they have stopped taking")}),
    ),
    (
        "vita3_log_intake",
        "Log a dose or application as done RIGHT NOW (\"took my magnesium\", \"had the D3\", \"used my cleanser\"). "
        "One item per call — for \"took my morning lot\", call it once per item that is due this morning. "
        "It cannot backdate: it stamps the current time, and a date argument is refused. "
        "An item that is NOT DUE today is refused too, with the next due date — say so and tell them the tick "
        "on /stack will ask and then log it; do not try to route around it. "
        "Use status='skipped' only when they say they deliberately skipped it.",
        _schema({**_ITEM_ID, "status": _s("'done' (default) or 'skipped'")}, ["itemId"]),
    ),
    (
        "vita3_add_supplement",
        "Add something NEW to the stack. Only from the stack page — from the home button this is refused. "
        "dose and intakeRule are REQUIRED and have no defaults: a supplement whose dose you guessed is worse "
        "than one you asked about. Copy the dose exactly as they say it, units and all (\"2 capsules\", \"500 mg\", "
        "\"20,000 IU\"). If the name is already in the stack the call is refused with the existing id — edit that instead.",
        _schema(
            {
                "name": _s("The product name ONLY, as printed — brand and product. Do NOT put the dose in the name; it has its own field"),
                "dose": _s("REQUIRED. The dose exactly as stated, WITH its unit — mg, mcg, IU, capsules. Never convert, never assume"),
                "intakeRule": _s(f"REQUIRED. One of: {_RULES}"),
                "hour": _n("Whole hour 0-23 they take it, if they said. Omit for no schedule — schedules have no minutes"),
                "daysOfWeek": _s("Days as numbers 0-6, 0 = Sunday (e.g. '1,3,5'). Omit for every day"),
                "purpose": _s("What it is for, if they said"),
                "fatSoluble": _b("true for A, D, E, K and fish oil"),
            },
            ["name", "dose", "intakeRule"],
        ),
    ),
    (
        "vita3_set_dose",
        "Change ONE item's dose (\"make the magnesium 480\", \"it's two capsules not one\"). "
        "The dose is a free-text label — write what they said, with the unit, and change nothing else about the item.",
        _schema({**_ITEM_ID, "dose": _s("The new dose as stated, with its unit")}, ["itemId", "dose"]),
    ),
    (
        "vita3_set_intake_rule",
        f"Change ONE item's intake rule — when/how it should be taken. Must be one of: {_RULES}.",
        _schema({**_ITEM_ID, "intakeRule": _s(f"One of: {_RULES}")}, ["itemId", "intakeRule"]),
    ),
    (
        "vita3_set_schedule",
        "Set WHEN an item is taken: a whole hour, plus how often — every day, every N days, or named weekdays. "
        "\"every other day\" is everyNDays 2; \"twice a week\" is not a repeat this understands, ask which days. "
        "Replaces the existing schedule for that item, so a wrong hour REPLACES a right one. "
        "\"Move the D3 to the evening\" needs an hour: if they did not name one, ASK — never pick a number to get "
        "the call through, and never fall back to 0. A refused call means the schedule is unchanged, which is safe; "
        "a guessed hour is a wrong time they will not notice.",
        _schema(
            {
                **_ITEM_ID,
                "hour": _n("Whole hour 0-23, as a NUMBER (19 = 7pm). There are no minutes. Omit and ask rather than guess"),
                "everyNDays": _n("Every N days ('every other day' = 2, 'every third day' = 3). Counts from today unless a cycle is already set. Wins over daysOfWeek — the two are different sentences"),
                "daysOfWeek": _s("Named days as numbers 0-6, 0 = Sunday (e.g. '1,3,5' for Mon/Wed/Fri). Omit for every day"),
            },
            ["itemId", "hour"],
        ),
    ),
    (
        "vita3_set_purpose",
        "Set what an item is FOR (\"the glycine is for sleep\"). One field, on one item.",
        _schema({**_ITEM_ID, "purpose": _s("What it is for, in their words")}, ["itemId", "purpose"]),
    ),
    (
        "vita3_set_active",
        "Stop or resume a STACK item (\"I've stopped the copper\", \"I'm back on the biotin\"). "
        "Stopping keeps the item and its history — nothing is ever deleted here, and you have no tool that deletes. "
        "Exercises are REFUSED: on /fitness the schedule is the only switch — set days with vita3_set_schedule, "
        "or clear them to stop the movement.",
        _schema({**_ITEM_ID, "active": _b("false = stopped taking it, true = taking it again")}, ["itemId", "active"]),
    ),
    (
        "vita3_fitness",
        "The exercise library in one call: every movement with its id, category, plan "
        "(sets × reps · planned load), schedule (days only — workouts have no hour), whether "
        "it is due today and whether it has been done, plus the last few logged ACTUALS. "
        "Call this ONLY if the request needs something the list you were given does not show.",
        _schema({}),
    ),
    (
        "vita3_log_workout",
        "Log an exercise as done RIGHT NOW (\"did my lunges\", \"did that at 17.5 today\"). "
        "One item per call. It cannot backdate. An item that is NOT DUE today is refused with "
        "the next due date — say so and tell them the tick on /fitness will ask and then log it. "
        "load/sets/reps/note are the ACTUAL for this session only: pass them when they say what "
        "they really did, never to rewrite the plan. If the actual keeps beating the plan, SUGGEST "
        "moving the plan in your reply — never change it silently.",
        _schema(
            {
                **_ITEM_ID,
                "load": _s("The load they ACTUALLY moved, as they said it (\"17.5 kg\"). Optional. The key is exactly `load`"),
                "sets": _n("Sets actually done. Optional"),
                "reps": _n("Reps actually done. Optional"),
                "note": _s("Anything else about the session (\"left knee twinged\"). Optional. The key is exactly `note` (singular)"),
            },
            ["itemId"],
        ),
    ),
    (
        "vita3_add_exercise",
        "Add a NEW movement to the library. Only from the fitness page. name and category are "
        "REQUIRED. It lands in the library with NO schedule — pass daysOfWeek or everyNDays only "
        "if they said when. NEVER pass an hour: workouts are due that day, any time, and an hour "
        "is refused.",
        _schema(
            {
                "name": _s("The movement name (\"Bulgarian Split Squat\")"),
                "category": _s(f"REQUIRED. One of: {_CATEGORIES}"),
                "sets": _n("Planned sets, if they said"),
                "reps": _n("Planned reps, if they said"),
                "load": _s("Planned load as said, free text (\"bodyweight\", \"10 kg/hand\")"),
                "durationSec": _n("Planned hold seconds instead of reps (plank = 20)"),
                "daysOfWeek": _s("Days as numbers 0-6, 0 = Sunday. Omit for no schedule"),
                "everyNDays": _n("Every N days ('every other day' = 2). Omit for no schedule"),
                "notes": _s("The how-to, if they described one"),
            },
            ["name", "category"],
        ),
    ),
    (
        "vita3_set_training",
        "Change ONE exercise's PLAN — sets, reps, load or durationSec (\"make it 3 sets of 12\", "
        "\"the plan is 20 kg now\"). Only the fields named are changed. This edits the PLAN; what "
        "they actually lifted today goes through vita3_log_workout.",
        _schema(
            {
                **_ITEM_ID,
                "sets": _n("New planned sets"),
                "reps": _n("New planned reps"),
                "load": _s("New planned load, free text"),
                "durationSec": _n("New planned hold seconds"),
            },
            ["itemId"],
        ),
    ),
    (
        "vita3_set_category",
        f"Change ONE exercise's category. Must be one of: {_CATEGORIES}.",
        _schema({**_ITEM_ID, "category": _s(f"One of: {_CATEGORIES}")}, ["itemId", "category"]),
    ),
    (
        "vita3_cosmetics",
        "The cosmetics routine in one call: every item with its id, brand, type, site, purpose, "
        "timing rule, schedule (hours included — a routine is morning/evening), whether it is due "
        "today and whether it has been used. Call this ONLY if the request needs something the list "
        "you were given does not show.",
        _schema({"includeInactive": _b("true to include things they have stopped using")}),
    ),
    (
        "vita3_add_cosmetic",
        "Add something NEW to the cosmetics routine. Only from the cosmetics page — from the home "
        "button this is refused. name and type are REQUIRED. Copy what the label says: brand, site, "
        "and the usage line as timingRule. If they said when, pass the whole hour (routines have "
        "hours — morning/evening) and daysOfWeek. A duplicate name is refused with the existing id.",
        _schema(
            {
                "name": _s("The product name as printed — do NOT put the brand here; it has its own field"),
                "type": _s(f"REQUIRED. One of: {_TYPES}"),
                "brand": _s("The brand, if shown (CeraVe, The Ordinary, Ben & Anna)"),
                "site": _s("Where it goes, free text (face, body, feet, underarms)"),
                "timingRule": _s("The how-to/when line as said (\"PM, after cleansing, before SPF\")"),
                "purpose": _s("What it is for, if they said"),
                "hour": _n("Whole hour 0-23 they use it, if they said. Omit for no schedule"),
                "daysOfWeek": _s("Days as numbers 0-6, 0 = Sunday. Omit for every day"),
            },
            ["name", "type"],
        ),
    ),
    (
        "vita3_set_cosmetic",
        f"Change ONE cosmetic's details — brand, type, site or timingRule. Only the fields named are "
        f"changed. type must be one of: {_TYPES}.",
        _schema(
            {
                **_ITEM_ID,
                "brand": _s("The new brand"),
                "type": _s(f"One of: {_TYPES}"),
                "site": _s("Where it goes, free text"),
                "timingRule": _s("The new how-to/when line"),
            },
            ["itemId"],
        ),
    ),
    (
        "vita3_profile",
        "The standing facts in one call: the facts (date of birth, age derived from it, sex, height, "
        "city), the history (procedures; conditions with their kind and status), the tenets that "
        "govern you, the goals with their latest measurements, the four nutrition ceilings, and the "
        "allergies/intolerances AGAIN as their own list — those are things they must NOT be given. "
        "Call this ONLY if the request needs something the context you were given does not show.",
        _schema({}),
    ),
    (
        "vita3_set_fact",
        "Set ONE standing fact about the person (\"I'm 182 now\", \"I moved to Sofia\"). One field per "
        "call — for two facts, call it twice. field must be one of: heightCm (whole number 50-300, "
        "centimetres), city (the name as they say it), dob (date of birth as yyyy-mm-dd, in the past), "
        "sex (one of: male, female, unknown — \"woman\" becomes female, \"man\" becomes male; anything "
        "else is refused). Anything outside these four is refused, naming the four.",
        _schema(
            {
                "field": _s("One of: heightCm, city, dob, sex"),
                "value": _s("The new value: a whole cm number for heightCm, yyyy-mm-dd for dob, male/female/unknown for sex"),
            },
            ["field", "value"],
        ),
    ),
    (
        "vita3_set_ceiling",
        "Set ONE daily nutrition ceiling (\"my carb ceiling is 20 grams\"). One number, one field: "
        "carb, protein, fat or kcal. value is a whole number — 1-999 for grams, 1-9999 for kcal — "
        "or null to clear the ceiling; a cleared ceiling means the food grid shows a plain sum. A "
        "value outside the range is REFUSED, never clamped — if they said 12000, ask; do not shrink it to fit.",
        _schema(
            {
                "field": _s("One of: carb, protein, fat, kcal"),
                "value": _n("Whole number 1-999 for carb/protein/fat grams, 1-9999 for kcal, or null to clear the ceiling"),
            },
            ["field"],
        ),
    ),
    (
        "vita3_add_condition",
        f"Add a NEW condition, allergy or intolerance to the history (\"I'm allergic to peanuts\", "
        f"\"I have neuropathy\"). kind must be one of: {_CONDITION_KINDS}. onsetDate is how they "
        f"remember it — yyyy-mm-dd, yyyy-mm or just yyyy — never invent a month they did not say. "
        f"A duplicate name is refused with the existing id — change that one's status instead. "
        f"Nothing is ever deleted here, and you have no tool that deletes.",
        _schema(
            {
                "name": _s("The condition or allergen as they named it (\"neuropathy\", \"peanuts\")"),
                "kind": _s(f"One of: {_CONDITION_KINDS}. Omit for a plain condition"),
                "onsetDate": _s("When it started, as they remember it: yyyy-mm-dd, yyyy-mm or yyyy. Omit if not said"),
                "notes": _s("Anything else they said about it. Optional"),
            },
            ["name"],
        ),
    ),
    (
        "vita3_set_condition_status",
        f"Change ONE condition's status (\"the neuropathy is under control\", \"the shingles is gone\"). "
        f"status must be one of: {_CONDITION_STATUSES}. On a condition row mic the id comes from the "
        f"row itself; otherwise use the id from vita3_profile.",
        _schema(
            {
                "conditionId": _n("The condition's numeric id, from vita3_profile. When the request names a row, that id is the answer"),
                "status": _s(f"One of: {_CONDITION_STATUSES}"),
            },
            ["conditionId", "status"],
        ),
    ),
    (
        "vita3_add_tenet",
        "Add a NEW tenet — a standing belief that governs how you answer them (\"I don't want "
        "medication when a habit would do\"). statement is required, in their words. scope and "
        "strength are short labels if they said them. A duplicate statement is refused with the "
        "existing id — toggle that one instead.",
        _schema(
            {
                "statement": _s("The tenet, in their words (500 characters or fewer)"),
                "scope": _s("What it applies to, if they said (a short label, 24 characters or fewer). Omit for general"),
                "strength": _s("How firmly held, if they said (a short label, 24 characters or fewer). Omit for strong"),
            },
            ["statement"],
        ),
    ),
    (
        "vita3_set_tenet_active",
        "Switch ONE tenet on or off (\"that rule about sugar doesn't hold any more\"). active=false "
        "sets it aside — the tenet stays on the record, and nothing is ever deleted. On a tenet row "
        "mic the id comes from the row itself; otherwise use the id from vita3_profile.",
        _schema(
            {
                "tenetId": _n("The tenet's numeric id, from vita3_profile. When the request names a row, that id is the answer"),
                "active": _b("true = it governs the agent, false = set aside"),
            },
            ["tenetId", "active"],
        ),
    ),
    (
        "vita3_log_meal",
        "Log a meal as eaten — spoken from the home mic (\"had a chicken salad for lunch\") or read "
        "from a plate photo. Same call either way: name the meal in description, then break it into "
        "components, one per thing on the plate, each with name and ALL FOUR macros. Every macro is "
        "required per component — an explicit 0 is fine, an omission is refused, naming the component "
        "and the field. From a photo, make your BEST GUESS at portions and macros rather than asking "
        "— the person reviews the numbers and fixes them after. eatenAt ONLY when the sentence names "
        "a mealtime (\"for lunch\", \"this morning\"), as a whole hour, never invented — omit it and "
        "the meal is stamped now. A simple one-thing meal may skip components and take the four "
        "macros at the top level instead.",
        _schema(
            {
                "description": _s("What the meal is, short (\"chicken salad with bread\")"),
                "components": {
                    "type": "array",
                    "description": "One entry per thing on the plate. Every entry needs name and all four macros — 0 is fine, omission is refused. Omit the array for a simple meal and pass the four macros at the top level instead",
                    "items": _schema(
                        {
                            "name": _s("The component as you would name it (\"chicken breast\", \"sourdough\")"),
                            "grams": _n("Portion in grams, if known. Optional"),
                            "kcal": _n("REQUIRED per component — best guess beats asking, the person reviews after"),
                            "carbs": _n("REQUIRED per component, grams. 0 is fine"),
                            "protein": _n("REQUIRED per component, grams. 0 is fine"),
                            "fat": _n("REQUIRED per component, grams. 0 is fine"),
                        },
                        ["name", "kcal", "carbs", "protein", "fat"],
                    ),
                },
                "kcal": _n("Meal-level kcal — ONLY when components are omitted; with components the server sums them and this is ignored"),
                "carbs": _n("Meal-level carbs, grams — only when components are omitted"),
                "protein": _n("Meal-level protein, grams — only when components are omitted"),
                "fat": _n("Meal-level fat, grams — only when components are omitted"),
                "eatenAt": _s("ONLY when the sentence names a mealtime — ISO or \"yyyy-mm-dd HH:MM\", a whole hour. Never invented; omit for right now"),
                "notes": _s("Anything else they said about the meal. Optional"),
            },
            ["description"],
        ),
    ),
    (
        "vita3_set_meal",
        "Fix ONE meal's description or its four macros (\"that was 600 kcal\", \"rename it to chicken "
        "salad\"). Only the fields named are changed. This is for LEGACY flat meals and description "
        "fixes: a meal that has components is REFUSED for macro edits — its numbers are the sums of "
        "its components, so fix the component with vita3_set_component and the meal follows. On a "
        "meal row mic the id comes from the row itself; otherwise from the context you were given.",
        _schema(
            {
                "mealId": _n("The meal's numeric id. When the request names a row, that id is the answer"),
                "description": _s("The new description, if renaming"),
                "kcal": _n("New meal kcal — refused if the meal has components"),
                "carbs": _n("New meal carbs, grams — refused if the meal has components"),
                "protein": _n("New meal protein, grams — refused if the meal has components"),
                "fat": _n("New meal fat, grams — refused if the meal has components"),
            },
            ["mealId"],
        ),
    ),
    (
        "vita3_set_component",
        "Fix ONE component of an itemized meal — grams or any of the four macros (\"the rice was "
        "200 g\", \"the chicken is 40 g protein\"). Only the fields named are changed, and the "
        "parent meal's totals are recomputed from its components — never edit the meal's numbers "
        "directly. The id comes from the row pin on a component mic, else from the context you "
        "were given.",
        _schema(
            {
                "componentId": _n("The component's numeric id, from the row pin. When the request names a row, that id is the answer"),
                "grams": _n("New portion in grams"),
                "kcal": _n("New kcal"),
                "carbs": _n("New carbs, grams"),
                "protein": _n("New protein, grams"),
                "fat": _n("New fat, grams"),
            },
            ["componentId"],
        ),
    ),
]


def register(ctx) -> None:
    for name, description, schema in TOOLS:
        ctx.register_tool(
            name=name,
            toolset="vita3",
            schema=schema,
            handler=_make_handler(name),
            description=description,
        )
    print(
        f"[vita3-bridge] registered {len(TOOLS)} tools -> "
        f"{os.environ.get('VITA3_URL', '(VITA3_URL unset)')} "
        f"as user {os.environ.get('VITA3_USER_ID') or '(shared — identity comes from each turn)'}",
        flush=True,
    )
