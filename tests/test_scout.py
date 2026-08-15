import json

import pytest

import scout


class FakeCtx:
    def __init__(self):
        self.registered = []

    def register_tool(self, name, toolset, schema, handler, description):
        self.registered.append(
            {"name": name, "toolset": toolset, "schema": schema,
             "handler": handler, "description": description}
        )


class _Resp:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _handler_for(ctx, name):
    return next(t["handler"] for t in ctx.registered if t["name"] == name)


def test_register_puts_every_tool_in_the_scout_toolset():
    """The count is deliberate: it catches a tool silently dropping out of
    registration. Bump it in the same commit that adds or removes a tool —
    it sat at 9 while scout grew to 21, so the suite was red for long enough
    that a red suite stopped meaning anything."""
    ctx = FakeCtx()
    scout.register(ctx)
    assert len(ctx.registered) == len(scout.TOOLS) == 21
    assert {t["toolset"] for t in ctx.registered} == {"scout"}


def test_every_tool_name_is_unique_and_prefixed():
    names = [t["name"] for t in scout.TOOLS]
    assert len(names) == len(set(names))
    assert all(n.startswith("scout_") for n in names)


def test_missing_key_refuses_by_name_before_any_request(monkeypatch):
    """No env at all — the refusal must happen before urlopen is ever called."""

    def fake_urlopen(req, timeout=None):
        raise AssertionError("must not make a request when SCOUT_API_KEY is unset")

    monkeypatch.setattr(scout.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.delenv("SCOUT_API_KEY", raising=False)
    monkeypatch.setenv("SCOUT_URL", "http://scout:3026")

    ctx = FakeCtx()
    scout.register(ctx)
    out = _handler_for(ctx, "scout_mission_list")({})

    assert out == "SCOUT_API_KEY is not set in this agent's .env — cannot call scout."


def test_mission_list_is_a_get_against_api_v1(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        return _Resp(b'{"missions": []}')

    monkeypatch.setattr(scout.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("SCOUT_URL", "http://scout:3026")
    monkeypatch.setenv("SCOUT_API_KEY", "sekrit")

    ctx = FakeCtx()
    scout.register(ctx)
    out = _handler_for(ctx, "scout_mission_list")({})

    assert seen["url"] == "http://scout:3026/api/v1/missions"
    assert seen["method"] == "GET"
    assert seen["headers"]["x-api-key"] == "sekrit"
    assert json.loads(out) == {"missions": []}


def test_mission_list_root_id_is_client_only_and_filters_after_the_fact(monkeypatch):
    """rootId must NOT reach the REST call (GET /missions takes no query at
    all), and must instead scope the already-returned tree client-side,
    mirroring mcp.ts's findSubtree/postProcess."""
    seen = {}
    tree = {
        "missions": [
            {"id": 1, "children": [{"id": 2, "children": []}, {"id": 3, "children": []}]},
            {"id": 4, "children": []},
        ]
    }

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        return _Resp(json.dumps(tree).encode())

    monkeypatch.setattr(scout.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("SCOUT_URL", "http://scout:3026")
    monkeypatch.setenv("SCOUT_API_KEY", "sekrit")

    ctx = FakeCtx()
    scout.register(ctx)
    out = json.loads(_handler_for(ctx, "scout_mission_list")({"rootId": 2}))

    assert seen["url"] == "http://scout:3026/api/v1/missions"  # rootId never sent
    assert out == {"missions": [{"id": 2, "children": []}]}


def test_nearby_folds_lat_lon_into_a_single_near_param(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        return _Resp(b'{"subjects": []}')

    monkeypatch.setattr(scout.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("SCOUT_URL", "http://scout:3026")
    monkeypatch.setenv("SCOUT_API_KEY", "sekrit")

    ctx = FakeCtx()
    scout.register(ctx)
    _handler_for(ctx, "scout_nearby")({"lat": 42.5, "lon": 23.3, "radiusM": 500})

    url = seen["url"]
    assert url.startswith("http://scout:3026/api/v1/search?")
    assert "near=42.5%2C23.3" in url
    assert "lat=" not in url and "lon=" not in url
    assert "radiusM=500" in url


def test_fact_add_substitutes_the_path_param_and_posts_the_rest_as_body(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        seen["body"] = json.loads(req.data.decode())
        return _Resp(b'{"ok": true}')

    monkeypatch.setattr(scout.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("SCOUT_URL", "http://scout:3026")
    monkeypatch.setenv("SCOUT_API_KEY", "sekrit")

    ctx = FakeCtx()
    scout.register(ctx)
    _handler_for(ctx, "scout_fact_add")(
        {"subjectId": 7, "key": "price_usd", "kind": "researched", "sourceUrl": "https://x"}
    )

    assert seen["url"] == "http://scout:3026/api/v1/subjects/7/facts"
    assert seen["method"] == "POST"
    # subjectId is consumed by the path, not repeated in the body
    assert "subjectId" not in seen["body"]
    assert seen["body"]["key"] == "price_usd"


def test_score_substitutes_mission_id_in_the_path(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        return _Resp(b'{"missionId": 9}')

    monkeypatch.setattr(scout.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("SCOUT_URL", "http://scout:3026")
    monkeypatch.setenv("SCOUT_API_KEY", "sekrit")

    ctx = FakeCtx()
    scout.register(ctx)
    _handler_for(ctx, "scout_score")({"missionId": 9})

    assert seen["url"] == "http://scout:3026/api/v1/missions/9/score"


def test_subject_upsert_posts_json_body_with_the_api_key(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        seen["body"] = json.loads(req.data.decode())
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        return _Resp(b'{"id": 1, "slug": "x", "geomVerified": false}')

    monkeypatch.setattr(scout.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("SCOUT_URL", "http://scout:3026")
    monkeypatch.setenv("SCOUT_API_KEY", "sekrit")

    ctx = FakeCtx()
    scout.register(ctx)
    _handler_for(ctx, "scout_subject_upsert")({"slug": "x", "name": "X", "kind": "place"})

    assert seen["url"] == "http://scout:3026/api/v1/subjects"
    assert seen["method"] == "POST"
    assert seen["body"] == {"slug": "x", "name": "X", "kind": "place"}
    assert seen["headers"]["x-api-key"] == "sekrit"
    assert seen["headers"]["content-type"] == "application/json"


def test_empty_optional_args_are_dropped_not_sent_blank(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        return _Resp(b'{"facts": []}')

    monkeypatch.setattr(scout.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("SCOUT_URL", "http://scout:3026")
    monkeypatch.setenv("SCOUT_API_KEY", "sekrit")

    ctx = FakeCtx()
    scout.register(ctx)
    _handler_for(ctx, "scout_stale")({"limit": ""})

    assert seen["url"] == "http://scout:3026/api/v1/stale"


def test_trailing_slash_on_scout_url_does_not_double_up(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        return _Resp(b'{"missions": []}')

    monkeypatch.setattr(scout.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("SCOUT_URL", "https://scout.dev.pica.win/")
    monkeypatch.setenv("SCOUT_API_KEY", "sekrit")

    ctx = FakeCtx()
    scout.register(ctx)
    _handler_for(ctx, "scout_mission_list")({})

    assert seen["url"] == "https://scout.dev.pica.win/api/v1/missions"


def test_http_error_becomes_a_named_refusal_not_an_exception(monkeypatch):
    import io
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 422, "Unprocessable", {},
            io.BytesIO(b'{"error":"rejected by scope","rejectedBy":"price_usd"}'),
        )

    monkeypatch.setattr(scout.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("SCOUT_URL", "http://scout:3026")
    monkeypatch.setenv("SCOUT_API_KEY", "sekrit")

    ctx = FakeCtx()
    scout.register(ctx)
    out = _handler_for(ctx, "scout_subject_upsert")(
        {"slug": "x", "name": "X", "kind": "place", "missionId": 1}
    )

    assert out.startswith("scout 422 at http://scout:3026/api/v1/subjects:")
    assert "rejected by scope" in out


def test_unreachable_host_names_the_url_and_the_env_var(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(scout.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("SCOUT_URL", "http://scout")  # the port-less mistake
    monkeypatch.setenv("SCOUT_API_KEY", "sekrit")

    ctx = FakeCtx()
    scout.register(ctx)
    out = _handler_for(ctx, "scout_mission_list")({})

    assert "scout unreachable at http://scout/api/v1/missions" in out
    assert "SCOUT_URL" in out
