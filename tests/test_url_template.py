import datetime as dt
import importlib.util
import json
import pathlib

import pytest

_spec = importlib.util.spec_from_file_location(
    "url_template",
    pathlib.Path(__file__).resolve().parent.parent / "_template" / "url_template.py",
)
ut = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ut)


ENV = {"RADARR_URL": "http://radarr:7878", "RADARR_API_KEY": "k"}.get


def r(t, args=None, quote=True):
    return ut.render(t, args or {}, lambda n: ENV(n) or "", quote=quote)


def test_env_substitution():
    assert r("{env.RADARR_URL}/api/v3/movie") == "http://radarr:7878/api/v3/movie"


def test_arg_substitution_is_url_quoted_in_a_url():
    assert r("/lookup?term={arg.query}", {"query": "star wars"}) == "/lookup?term=star%20wars"
    assert r("/lookup?term={arg.query}", {"query": "a&b=c"}) == "/lookup?term=a%26b%3Dc"


def test_arg_substitution_is_not_quoted_in_a_body():
    assert r('{"title":"{arg.t}"}', {"t": "a b"}, quote=False) == '{"title":"a b"}'


def test_default_is_used_when_the_arg_is_absent_or_empty():
    tpl = "/movie/{arg.id}?deleteFiles={arg.deleteFiles|false}"
    assert r(tpl, {"id": 7}) == "/movie/7?deleteFiles=false"
    assert r(tpl, {"id": 7, "deleteFiles": ""}) == "/movie/7?deleteFiles=false"
    assert r(tpl, {"id": 7, "deleteFiles": True}) == "/movie/7?deleteFiles=true"


def test_booleans_render_lowercase():
    """These apps compare against the string "true"; Python renders True as
    "True", which fails silently. Cost us a real bug in home_view."""
    assert r("?x={arg.b}", {"b": True}) == "?x=true"
    assert r("?x={arg.b}", {"b": False}) == "?x=false"


def test_path_args_are_substituted():
    assert r("{env.RADARR_URL}/api/v3/movie/{arg.id}", {"id": 42}) == (
        "http://radarr:7878/api/v3/movie/42"
    )


def test_now_macros():
    today = dt.date.today()
    assert r("{now}") == today.isoformat()
    assert r("{now+14d}") == (today + dt.timedelta(days=14)).isoformat()
    assert r("{now-3d}") == (today - dt.timedelta(days=3)).isoformat()


def test_now_macro_nested_inside_a_default():
    """sonarr's calendar is `start={arg.start|{now}}`. A single pass whose token
    regex stops at the first `}` swallows `{arg.start|{now}` and leaves a stray
    brace, so the URL carried a literal `%7Bnow}` and Sonarr got a garbage
    range. Date macros must resolve first, over the whole template."""
    today = dt.date.today()
    tpl = "/api/v3/calendar?start={arg.start|{now}}&end={arg.end|{now+14d}}&includeSeries=true"

    assert r(tpl) == (
        f"/api/v3/calendar?start={today.isoformat()}"
        f"&end={(today + dt.timedelta(days=14)).isoformat()}&includeSeries=true"
    )
    assert r(tpl, {"start": "2026-01-01", "end": "2026-01-05"}) == (
        "/api/v3/calendar?start=2026-01-01&end=2026-01-05&includeSeries=true"
    )
    assert "{" not in r(tpl) and "}" not in r(tpl)


def test_missing_env_becomes_empty_not_a_crash():
    assert ut.render("{env.NOPE}/x", {}, lambda n: "", quote=True) == "/x"


# ── shape ────────────────────────────────────────────────────────────────────

def test_shape_is_a_noop_without_select_or_limit():
    assert ut.shape('[{"a":1}]') == '[{"a":1}]'


def test_shape_projects_selected_fields():
    body = json.dumps([{"id": 1, "title": "A", "huge": "x" * 100}])
    assert json.loads(ut.shape(body, select=["id", "title"])) == [{"id": 1, "title": "A"}]


def test_shape_applies_limit():
    body = json.dumps([{"id": i} for i in range(10)])
    assert len(json.loads(ut.shape(body, limit=3))) == 3


def test_shape_leaves_non_arrays_alone():
    """Radarr returns an object for some endpoints; shaping must not eat it."""
    assert ut.shape('{"page":1}', select=["id"]) == '{"page":1}'


def test_shape_leaves_unparseable_text_alone():
    assert ut.shape("not json", select=["id"]) == "not json"


def test_shape_keeps_missing_fields_as_null():
    body = json.dumps([{"id": 1}])
    assert json.loads(ut.shape(body, select=["id", "year"])) == [{"id": 1, "year": None}]
