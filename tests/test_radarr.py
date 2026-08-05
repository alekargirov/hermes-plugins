import json

import pytest

import radarr


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
    radarr.register(ctx)
    return ctx


def _handler_for(ctx, name):
    return next(t["handler"] for t in ctx.registered if t["name"] == name)


@pytest.fixture
def spy(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        seen["body"] = req.data.decode() if req.data else None
        return _Resp(seen.get("respond", b"[]"))

    monkeypatch.setattr(radarr.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("RADARR_URL", "http://radarr:7878")
    monkeypatch.setenv("RADARR_API_KEY", "secret")
    return seen


def test_all_tools_register_under_the_radarr_toolset():
    ctx = _registered()
    assert len(ctx.registered) == 8
    assert {t["toolset"] for t in ctx.registered} == {"radarr"}
    assert all(t["description"].strip() for t in ctx.registered)


def test_every_call_sends_the_api_key(spy):
    _handler_for(_registered(), "radarr_library")({})
    assert spy["headers"]["x-api-key"] == "secret"
    assert spy["url"] == "http://radarr:7878/api/v3/movie"


def test_search_url_quotes_the_query(spy):
    _handler_for(_registered(), "radarr_search")({"query": "star wars"})
    assert spy["url"] == "http://radarr:7878/api/v3/movie/lookup?term=star%20wars"


def test_delete_puts_the_id_in_the_path_and_defaults_deletefiles(spy):
    _handler_for(_registered(), "radarr_delete")({"id": 42})
    assert spy["url"] == "http://radarr:7878/api/v3/movie/42?deleteFiles=false"
    assert spy["method"] == "DELETE"


def test_delete_files_true_renders_lowercase(spy):
    _handler_for(_registered(), "radarr_delete")({"id": 42, "deleteFiles": True})
    assert spy["url"].endswith("deleteFiles=true")


def test_library_projects_rows_down_to_the_selected_fields(spy):
    """A full Radarr movie object is enormous and there are thousands. Without
    the projection the model gets a truncated wall of JSON."""
    spy["respond"] = json.dumps(
        [{"id": 1, "title": "Dune", "year": 2021, "tmdbId": 9, "hasFile": True,
          "monitored": True, "overview": "x" * 5000, "images": [1, 2, 3]}]
    ).encode()
    out = json.loads(_handler_for(_registered(), "radarr_library")({}))
    assert out == [{"id": 1, "title": "Dune", "year": 2021, "tmdbId": 9,
                    "hasFile": True, "monitored": True}]
    assert "overview" not in out[0]


def test_shaping_leaves_a_non_array_response_alone(spy):
    spy["respond"] = b'{"message":"not a list"}'
    out = json.loads(_handler_for(_registered(), "radarr_library")({}))
    assert out == {"message": "not a list"}


def test_missing_url_is_a_refusal_and_fires_no_request(monkeypatch):
    called = {"n": 0}

    def fake_urlopen(req, timeout=None):
        called["n"] += 1
        return _Resp(b"[]")

    monkeypatch.setattr(radarr.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.delenv("RADARR_URL", raising=False)
    out = json.loads(_handler_for(_registered(), "radarr_library")({}))
    assert out["ok"] is False and "RADARR_URL" in out["message"]
    assert called["n"] == 0


def test_unreachable_names_the_url_and_the_env_var(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(radarr.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("RADARR_URL", "http://radarr")
    monkeypatch.setenv("RADARR_API_KEY", "k")  # else the key guard refuses first
    out = json.loads(_handler_for(_registered(), "radarr_library")({}))
    assert out["ok"] is False
    assert "http://radarr/api/v3/movie" in out["message"]
    assert "RADARR_URL" in out["message"]


def test_no_secret_leaks_into_the_unreachable_message(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise OSError("boom")

    monkeypatch.setattr(radarr.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("RADARR_URL", "http://radarr:7878")
    monkeypatch.setenv("RADARR_API_KEY", "SUPERSECRET")
    out = json.loads(_handler_for(_registered(), "radarr_library")({}))
    assert "SUPERSECRET" not in out["message"]
