"""weather — Open-Meteo current conditions and daily forecast.

Two GETs against api.open-meteo.com. Holds no logic beyond URL templating
and response shaping.

Env (profile .env): WEATHER_LAT, WEATHER_LON. No auth — Open-Meteo is free.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request


def _env(name: str) -> str:
    """Profile-scoped credential read. Falls through to os.environ on a
    single-profile gateway (one container per user); honours the per-turn
    secret scope on the multiplexed gateway so two profiles' values never
    cross."""
    try:
        from agent.secret_scope import get_secret

        val = get_secret(name, "")
    except Exception:
        val = os.environ.get(name, "")
    return val or ""


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        return json.dumps({"ok": False, "message": f"open-meteo HTTP {e.code}: {e.read().decode()[:300]}"})
    except Exception as e:  # noqa: BLE001 — surface the failure, never crash the turn
        return json.dumps({"ok": False, "message": f"open-meteo unreachable: {e}"})


def _s(d):
    return {"type": "string", "description": d}


def _n(d):
    return {"type": "number", "description": d}


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


def _weather_current(_args: dict, **kwargs) -> str:
    lat = _env("WEATHER_LAT")
    lon = _env("WEATHER_LON")
    qs = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,visibility",
        "wind_speed_unit": "kmh",
    })
    return _get(f"https://api.open-meteo.com/v1/forecast?{qs}")


def _weather_forecast(args: dict, **kwargs) -> str:
    days = args.get("days", 3)
    lat = _env("WEATHER_LAT")
    lon = _env("WEATHER_LON")
    qs = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum",
        "forecast_days": days,
        "wind_speed_unit": "kmh",
    })
    return _get(f"https://api.open-meteo.com/v1/forecast?{qs}")


TOOLS = [
    (
        "weather_current",
        "Get current weather conditions (temperature, humidity, wind, visibility) for the configured location.",
        _schema({}),
        _weather_current,
    ),
    (
        "weather_forecast",
        "Get daily weather forecast for the configured location. days defaults to 3, max 7.",
        _schema({"days": _n("Number of forecast days (1-7, default 3)")}),
        _weather_forecast,
    ),
]


def register(ctx) -> None:
    for name, description, schema, handler in TOOLS:
        ctx.register_tool(
            name=name,
            toolset="weather",
            schema=schema,
            handler=handler,
            description=description,
        )
    print(
        f"[weather] registered {len(TOOLS)} tools "
        f"-> ({_env('WEATHER_LAT')}, {_env('WEATHER_LON')})",
        flush=True,
    )