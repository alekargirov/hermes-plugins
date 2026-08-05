import json

import pytest

import weather


class FakeCtx:
    def __init__(self):
        self.registered = []

    def register_tool(self, name, toolset, schema, handler, description):
        self.registered.append({"name": name, "toolset": toolset, "schema": schema,
                                "handler": handler, "description": description})


class _Resp:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _registered():
    ctx = FakeCtx()
    weather.register(ctx)
    return ctx


def _handler_for(ctx, name):
    return next(t["handler"] for t in ctx.registered if t["name"] == name)


@pytest.fixture
def spy(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        return _Resp(b'{"current":{}}')

    monkeypatch.setattr(weather.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("WEATHER_LAT", "42.7")
    monkeypatch.setenv("WEATHER_LON", "23.3")
    return seen


def test_both_tools_register_under_the_weather_toolset():
    ctx = _registered()
    assert [t["name"] for t in ctx.registered] == ["weather_current", "weather_forecast"]
    assert {t["toolset"] for t in ctx.registered} == {"weather"}


def test_current_asks_for_the_fixed_field_set(spy):
    _handler_for(_registered(), "weather_current")({})
    assert "latitude=42.7" in spy["url"] and "longitude=23.3" in spy["url"]
    assert "current=temperature_2m" in spy["url"]
    assert "wind_speed_unit=kmh" in spy["url"]


@pytest.mark.parametrize(
    "given,expected",
    [(1, 1), (7, 7), (3, 3), (0, 1), (99, 7), (-4, 1), ("5", 5), ("nonsense", 3), (None, 3)],
)
def test_forecast_days_are_clamped_to_open_meteos_range(spy, given, expected):
    """Open-Meteo 400s outside 1-7, and a 400 the model can't read is worse
    than quietly giving it a week."""
    _handler_for(_registered(), "weather_forecast")({"days": given})
    assert f"forecast_days={expected}" in spy["url"]


def test_forecast_defaults_to_three_days_when_unspecified(spy):
    _handler_for(_registered(), "weather_forecast")({})
    assert "forecast_days=3" in spy["url"]


def test_no_location_is_a_readable_refusal_and_fires_no_request(monkeypatch):
    called = {"n": 0}

    def fake_urlopen(req, timeout=None):
        called["n"] += 1
        return _Resp(b"{}")

    monkeypatch.setattr(weather.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.delenv("WEATHER_LAT", raising=False)
    monkeypatch.delenv("WEATHER_LON", raising=False)

    out = json.loads(_handler_for(_registered(), "weather_current")({}))
    assert out["ok"] is False
    assert "WEATHER_LAT" in out["message"]
    assert called["n"] == 0


def test_the_model_cannot_choose_the_variables(spy):
    """Only `days` is the agent's to set — everything else is fixed."""
    props = {t[0]: t[2]["properties"] for t in weather.TOOLS}
    assert props["weather_current"] == {}
    assert list(props["weather_forecast"]) == ["days"]
