"""Tool handlers — what runs when the LLM calls each weather tool.

Every handler delegates to ``_http.execute`` with its spec. Generated from the
legacy MCP YAML; do not edit by hand.
"""
from __future__ import annotations

from ._http import execute


_SPECS = {
    "weather_current": {
        "method": "GET",
        "url": "https://api.open-meteo.com/v1/forecast?latitude={env.WEATHER_LAT}&longitude={env.WEATHER_LON}&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,visibility&wind_speed_unit=kmh",
        "headers": {
            "Accept": "application/json"
        }
    },
    "weather_forecast": {
        "method": "GET",
        "url": "https://api.open-meteo.com/v1/forecast?latitude={env.WEATHER_LAT}&longitude={env.WEATHER_LON}&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum&forecast_days={arg.days|3}&wind_speed_unit=kmh",
        "headers": {
            "Accept": "application/json"
        }
    }
}


def weather_current(args: dict, **kwargs) -> str:
    return execute(_SPECS["weather_current"], args)


def weather_forecast(args: dict, **kwargs) -> str:
    return execute(_SPECS["weather_forecast"], args)



