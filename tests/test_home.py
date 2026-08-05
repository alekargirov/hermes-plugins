import json

import pytest

import home


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


def _registered():
    ctx = FakeCtx()
    home.register(ctx)
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
        seen["body"] = json.loads(req.data.decode()) if req.data else None
        return _Resp(b'{"ok":true}')

    monkeypatch.setattr(home.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("HOME_URL", "http://home2:3021")
    monkeypatch.setenv("HOME_API_KEY", "k")
    monkeypatch.setenv("HOME_USER_ID", "2")
    return seen


def test_home_api_key_is_the_name_and_home_key_still_works(monkeypatch):
    """HOME_API_KEY is what home-srv-v2's .env.secrets and the gate's home.yaml
    already call it. This plugin invented HOME_KEY, which would have made an
    operator copy an existing secret under a second name. HOME_KEY is kept as a
    fallback rather than a break."""
    monkeypatch.delenv("HOME_API_KEY", raising=False)
    monkeypatch.delenv("HOME_KEY", raising=False)
    assert home._home_key() == ""

    monkeypatch.setenv("HOME_KEY", "old")
    assert home._home_key() == "old"

    monkeypatch.setenv("HOME_API_KEY", "new")
    assert home._home_key() == "new"


def test_a_missing_home_key_refuses_without_firing_a_request(monkeypatch):
    called = {"n": 0}

    def count(req, timeout=None):
        called["n"] += 1
        return _Resp(b"{}")

    monkeypatch.setattr(home.urllib.request, "urlopen", count)
    monkeypatch.setenv("HOME_URL", "http://home2:3021")
    monkeypatch.delenv("HOME_API_KEY", raising=False)
    monkeypatch.delenv("HOME_KEY", raising=False)

    out = json.loads(_handler_for(_registered(), "home_view")({}))
    assert out["ok"] is False
    assert "HOME_API_KEY" in out["message"]
    assert called["n"] == 0


def test_all_four_tools_register_under_the_home_toolset():
    ctx = _registered()
    assert [t["name"] for t in ctx.registered] == [
        "home_view", "home_update", "home_hide", "home_unhide"
    ]
    assert {t["toolset"] for t in ctx.registered} == {"home"}


def test_view_is_a_query_get(spy):
    _handler_for(_registered(), "home_view")({})
    assert spy["url"] == "http://home2:3021/api/v2/view"
    assert spy["method"] == "GET"


@pytest.mark.parametrize(
    "value,expected", [(True, "true"), (False, "false")]
)
def test_query_booleans_go_over_the_wire_lowercase(spy, value, expected):
    """The app does `query("includeHidden") === "true"`. Python's urlencode
    renders True as "True", which fails that comparison SILENTLY — the call
    returns the ordinary page and the hidden tiles are just absent."""
    _handler_for(_registered(), "home_view")({"includeHidden": value})
    assert spy["url"] == f"http://home2:3021/api/v2/view?includeHidden={expected}"


def test_every_call_carries_both_the_key_and_the_user_id(spy):
    """Both, never either — the app requires them together."""
    _handler_for(_registered(), "home_view")({})
    assert spy["headers"]["x-home-key"] == "k"
    assert spy["headers"]["x-user-id"] == "2"


def test_the_user_id_comes_from_env_and_cannot_be_set_by_the_model(spy):
    """An arg called user_id must not reach the header — identity is the
    operator's, not the model's."""
    _handler_for(_registered(), "home_view")({"user_id": "999", "userId": "999"})
    assert spy["headers"]["x-user-id"] == "2"


def test_id_goes_in_the_path_and_not_the_body(spy):
    _handler_for(_registered(), "home_update")({"id": 7, "title": "New"})
    assert spy["url"] == "http://home2:3021/api/v2/items/7"
    assert spy["method"] == "PATCH"
    assert spy["body"] == {"title": "New"}, "id must not travel in the body too"


def test_update_omits_fields_the_model_did_not_set(spy):
    """The gate's string template sent '' for unset fields and once wiped a
    tile's url, icon and description. Real JSON just leaves the key out."""
    _handler_for(_registered(), "home_update")(
        {"id": 7, "title": "New", "description": "", "icon": None}
    )
    assert spy["body"] == {"title": "New"}


def test_hide_and_unhide_post_no_body(spy):
    _handler_for(_registered(), "home_hide")({"id": 3})
    assert spy["url"] == "http://home2:3021/api/v2/items/3/hide"
    assert spy["method"] == "POST"
    assert spy["body"] is None


def test_missing_id_is_a_readable_refusal_not_a_broken_url(monkeypatch):
    called = {"n": 0}

    def fake_urlopen(req, timeout=None):
        called["n"] += 1
        return _Resp(b"{}")

    monkeypatch.setattr(home.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("HOME_API_KEY", "k")  # else the key guard refuses first
    out = json.loads(_handler_for(_registered(), "home_hide")({}))
    assert out["ok"] is False
    assert "id is required" in out["message"]
    assert called["n"] == 0, "must not fire a request at /items//hide"


def test_unreachable_names_the_url_and_the_env_var(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(home.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("HOME_URL", "http://home2")  # port-less mistake
    monkeypatch.setenv("HOME_API_KEY", "k")  # else the key guard refuses first

    out = json.loads(_handler_for(_registered(), "home_view")({}))
    assert out["ok"] is False
    assert "http://home2/api/v2/view" in out["message"]
    assert "HOME_URL" in out["message"]
