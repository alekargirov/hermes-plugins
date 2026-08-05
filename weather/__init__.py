"""weather — Hermes plugin for Open-Meteo.

The only KEYLESS plugin in this repo. Open-Meteo needs no credential, so there
is nothing to leak and nothing to rotate: the whole configuration is a latitude
and a longitude. Do not go looking for a WEATHER_API_KEY; there isn't one.

This is a DIRECT plugin — there is no app of ours behind it, so the plugin owns
the HTTP call rather than forwarding to an /api/agent/tools endpoint.

Env (profile .env):
  WEATHER_LAT  latitude of the configured location
  WEATHER_LON  longitude

Tool descriptions port VERBATIM from srv-mcp-yaml/weather.yaml.

The fixed query fields (which variables to ask Open-Meteo for) are part of the
tool, not the agent's business: the model chooses the number of forecast days
and nothing else. Widening that is an edit here, deliberately.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

PLUGIN_VERSION = "2026-08-05.2"

BASE = "https://api.open-meteo.com/v1/forecast"

# What we ask Open-Meteo for. Fixed, not model-controlled.
CURRENT_FIELDS = (
    "temperature_2m,apparent_temperature,relative_humidity_2m,"
    "weather_code,wind_speed_10m,visibility"
)
DAILY_FIELDS = "temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum"


def _env(name: str, default: str = "") -> str:
    """Profile-scoped read — see the notes plugin for why a bare
    os.environ.get is wrong under the multiplexed gateway."""
    try:
        from agent.secret_scope import get_secret

        val = get_secret(name, "")
    except Exception:
        val = os.environ.get(name, "")
    return val or default


def _clamp_days(raw) -> int:
    """1–7, default 3. Open-Meteo 400s on anything else, and a 400 the model
    can't read is worse than quietly giving it a week."""
    try:
        n = int(float(raw))
    except (TypeError, ValueError):
        return 3
    return max(1, min(7, n))


def _fetch(params: dict) -> str:
    lat, lon = _env("WEATHER_LAT"), _env("WEATHER_LON")
    if not lat or not lon:
        return json.dumps(
            {
                "ok": False,
                "message": "WEATHER_LAT and WEATHER_LON are not set — this profile has no configured location",
            }
        )

    query = {"latitude": lat, "longitude": lon, "wind_speed_unit": "kmh", **params}
    url = BASE + "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        return json.dumps(
            {"ok": False, "message": f"open-meteo HTTP {e.code}: {e.read().decode()[:300]}"}
        )
    except Exception as e:  # noqa: BLE001 — surface it to the agent, never crash the turn
        # NAME THE URL, minus nothing — there is no secret in it.
        return json.dumps(
            {"ok": False, "message": f"open-meteo unreachable at {url}: {e}"}
        )


def _current(args: dict, session_id: str = None, **kwargs) -> str:
    return _fetch({"current": CURRENT_FIELDS})


def _forecast(args: dict, session_id: str = None, **kwargs) -> str:
    days = _clamp_days((args or {}).get("days", 3))
    return _fetch({"daily": DAILY_FIELDS, "forecast_days": days})


def _n(d):
    return {"type": "number", "description": d}


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


TOOLS = [
    (
        "weather_current",
        "Get current weather conditions (temperature, humidity, wind, visibility) for the configured location.",
        _schema({}),
        _current,
    ),
    (
        "weather_forecast",
        "Get daily weather forecast for the configured location. days defaults to 3, max 7.",
        _schema({"days": _n("Number of forecast days (1–7, default 3)")}),
        _forecast,
    ),
]


def _fn_schema(name: str, description: str, params: dict) -> dict:
    """hermes registers `schema` VERBATIM as the OpenAI `function` object, so
    name and description must live INSIDE it and the argument schema must sit
    under `parameters`. Registering a bare {"type":"object","properties":...}
    leaves `function.parameters` absent; the schema sanitizer then substitutes
    an empty {"type":"object","properties":{}} and the model sees a tool with
    no arguments and no description. See _template/tool_schema.py."""
    return {"name": name, "description": description, "parameters": params}


def register(ctx) -> None:
    for name, description, schema, handler in TOOLS:
        ctx.register_tool(
            name=name,
            toolset="weather",
            schema=_fn_schema(name, description, schema),
            handler=handler,
            description=description,
        )
    lat, lon = _env("WEATHER_LAT"), _env("WEATHER_LON")
    where = f"{lat},{lon}" if lat and lon else "(no location configured)"
    print(
        f"[weather] registered {len(TOOLS)} tools (v{PLUGIN_VERSION}) -> open-meteo @ {where}",
        flush=True,
    )
