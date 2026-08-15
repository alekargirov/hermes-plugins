"""The contract for app-bridge — vita3 and fin3.

These are BRIDGES to our own apps, not direct plugins, so they get their own
suite rather than joining tests/test_direct_plugins.py: there is no URL
template, no response shaping and no per-service auth scheme to hold them to.
What there IS: a credential on the wire, a refusal path, and two identity
fields that must behave exactly as documented.

The bridges had no tests at all before 2026-08-15 — they were left out of the
direct-plugin suite because hyphens in `vita3-bridge` and `fin3-bridge` made
them un-importable by name. That was a mechanicality, not a judgement that they
were safe, and it hid a real defect: see
test_an_unset_url_is_a_refusal_not_an_exception.
"""
import io
import json
import urllib.error

import pytest

import app_bridge
from app_bridge import _core

BRIDGES = list(app_bridge.BRIDGES)
NAMES = [b.name for b in BRIDGES]

ENV = {
    "vita3": {
        "VITA3_URL": "http://vita:3023",
        "VITA3_TOOL_KEY": "TOPSECRET",
        "VITA3_USER_ID": "216",
    },
    "fin3": {
        "FIN3_URL": "http://fin:3022",
        "FIN3_TOOL_KEY": "TOPSECRET",
        "FIN3_USER_ID": "7",
    },
}


class FakeCtx:
    def __init__(self):
        self.registered = []

    def register_tool(self, name, toolset, schema, handler, description, **kw):
        self.registered.append(
            {"name": name, "toolset": toolset, "schema": schema,
             "handler": handler, "description": description}
        )


class _Resp:
    def __init__(self, body=b"{}"):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _configured(monkeypatch, bridge):
    for k, v in ENV[bridge.name].items():
        monkeypatch.setenv(k, v)


def _handler(bridge, tool=None):
    return _core._make_handler(bridge, tool or bridge.tools[0][0])


@pytest.fixture
def spy(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        seen["payload"] = json.loads(req.data.decode())
        return _Resp(seen.get("respond", b'{"ok":true}'))

    monkeypatch.setattr(_core.urllib.request, "urlopen", fake_urlopen)
    return seen


# ── shape ────────────────────────────────────────────────────────────────────

def test_the_merge_did_not_collapse_the_two_toolsets():
    """One plugin, two toolsets. fin3 registered under `todo` once and hermes'
    own todo schema bled into ours — the model told alek fin3_update_category
    "only supports target and content" and refused a change it supports."""
    ctx = FakeCtx()
    app_bridge.register(ctx)

    by_toolset = {}
    for t in ctx.registered:
        by_toolset.setdefault(t["toolset"], []).append(t["name"])

    assert set(by_toolset) == {"vita3", "fin3"}
    assert len(ctx.registered) == 60
    assert len({t["name"] for t in ctx.registered}) == 60, "a tool name collides"
    for toolset, names in by_toolset.items():
        assert all(n.startswith(f"{toolset}_") for n in names), toolset


def test_each_app_keeps_its_own_plugin_version():
    """Each app compares the stamp against its own PLUGIN_VERSION and reports a
    mismatch to the model. One shared number would break both handshakes."""
    versions = {b.name: b.version for b in BRIDGES}
    assert len(set(versions.values())) == 2, versions


@pytest.mark.parametrize("bridge", BRIDGES, ids=NAMES)
def test_every_tool_has_a_description_and_a_function_shaped_schema(bridge):
    ctx = FakeCtx()
    _core.register_bridge(ctx, bridge)
    for t in ctx.registered:
        assert t["description"].strip(), f"{t['name']} has no description"
        s = t["schema"]
        assert s["name"] == t["name"]
        assert s["description"].strip()
        params = s["parameters"]
        assert params["type"] == "object"
        for req in params["required"]:
            assert req in params["properties"], f"{t['name']}: {req} not declared"


# ── the forward ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bridge", BRIDGES, ids=NAMES)
def test_the_key_travels_in_the_apps_own_header(monkeypatch, spy, bridge):
    _configured(monkeypatch, bridge)
    _handler(bridge)({})
    assert spy["headers"][bridge.key_header] == "TOPSECRET"
    assert spy["url"] == f"{ENV[bridge.name][bridge.url_env]}/api/agent/tools"
    assert spy["method"] == "POST"


@pytest.mark.parametrize("bridge", BRIDGES, ids=NAMES)
def test_identity_comes_from_the_profile_and_the_dispatch_never_the_model(
    monkeypatch, spy, bridge
):
    """user_id is read from the profile .env and session_id is handed to the
    handler in code. A model that could set either could act as someone else,
    so arguments carrying those names must land in `args` and nowhere else."""
    _configured(monkeypatch, bridge)
    handler = _handler(bridge)
    handler({"user_id": "999", "session_id": "forged"}, session_id="real-turn")

    assert spy["payload"]["user_id"] == ENV[bridge.name][bridge.user_env]
    assert spy["payload"]["session_id"] == "real-turn"
    assert spy["payload"]["args"] == {"user_id": "999", "session_id": "forged"}


@pytest.mark.parametrize("bridge", BRIDGES, ids=NAMES)
def test_the_version_stamp_rides_on_every_call(monkeypatch, spy, bridge):
    _configured(monkeypatch, bridge)
    _handler(bridge)({})
    assert spy["payload"]["plugin_version"] == bridge.version


# ── refusals ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bridge", BRIDGES, ids=NAMES)
def test_an_unset_url_is_a_refusal_not_an_exception(monkeypatch, bridge):
    """THE REGRESSION THIS SUITE EXISTS FOR.

    Before the merge both bridges built the URL as `_env(URL).rstrip("/") +
    "/api/agent/tools"` and passed it to urllib.request.Request OUTSIDE the
    try block. With the variable unset that is the relative string
    "/api/agent/tools", and Request raises ValueError straight out of the tool
    handler — despite the comment on the except clause promising to "surface
    the failure to the agent, never crash the turn".

    A port-less VITA3_URL therefore read as a broken plugin rather than a typo
    and cost alek hours on prod. notes was fixed after that incident (see
    tests/test_notes.py); the bridges were not, until now.
    """
    called = {"n": 0}

    def count(req, timeout=None):
        called["n"] += 1
        return _Resp()

    monkeypatch.setattr(_core.urllib.request, "urlopen", count)
    for k in ENV[bridge.name]:
        monkeypatch.delenv(k, raising=False)

    out = json.loads(_handler(bridge)({}))  # must not raise
    assert out["ok"] is False
    assert bridge.url_env in out["message"], "the refusal must name the variable"
    assert called["n"] == 0, "refused, but still fired a request"


@pytest.mark.parametrize("bridge", BRIDGES, ids=NAMES)
def test_a_missing_key_is_named_not_left_as_a_bare_401(monkeypatch, bridge):
    """URL set, key missing. Without the guard the request goes out with an
    empty auth header, the app answers 401, and the agent reports the backend
    as broken rather than one missing line in the profile .env."""
    called = {"n": 0}

    def count(req, timeout=None):
        called["n"] += 1
        return _Resp()

    monkeypatch.setattr(_core.urllib.request, "urlopen", count)
    _configured(monkeypatch, bridge)
    monkeypatch.delenv(bridge.key_env, raising=False)

    out = json.loads(_handler(bridge)({}))
    assert out["ok"] is False
    assert bridge.key_env in out["message"]
    assert called["n"] == 0


@pytest.mark.parametrize("bridge", BRIDGES, ids=NAMES)
def test_an_absent_user_id_is_allowed_and_still_forwards(monkeypatch, spy, bridge):
    """<APP>_USER_ID is OPTIONAL and must NOT be guarded. One shared container
    for the household leaves it unset and the turn alone decides identity;
    fin3's default profile has none on purpose and can act for nobody. A guard
    here would break both arrangements."""
    _configured(monkeypatch, bridge)
    monkeypatch.delenv(bridge.user_env, raising=False)

    out = _handler(bridge)({}, session_id="real-turn")
    assert json.loads(out) == {"ok": True}
    assert spy["payload"]["user_id"] == ""
    assert spy["payload"]["session_id"] == "real-turn"


@pytest.mark.parametrize("bridge", BRIDGES, ids=NAMES)
def test_an_unreachable_app_names_the_url_and_the_variable(monkeypatch, bridge):
    """Without the URL in the message a wrong host reads as a broken plugin
    rather than a typo — the whole lesson of the VITA3_URL incident."""
    def boom(req, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(_core.urllib.request, "urlopen", boom)
    _configured(monkeypatch, bridge)

    out = json.loads(_handler(bridge)({}))
    assert out["ok"] is False
    assert f"{ENV[bridge.name][bridge.url_env]}/api/agent/tools" in out["message"]
    assert bridge.url_env in out["message"]


# ── secrets ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bridge", BRIDGES, ids=NAMES)
def test_no_key_reaches_the_model_when_the_app_is_unreachable(monkeypatch, bridge):
    def boom(req, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(_core.urllib.request, "urlopen", boom)
    _configured(monkeypatch, bridge)

    for name, _d, _s in bridge.tools:
        out = _core._make_handler(bridge, name)({})
        assert "TOPSECRET" not in out, f"{bridge.name}.{name} leaked the key"
        assert json.loads(out)["ok"] is False


@pytest.mark.parametrize("bridge", BRIDGES, ids=NAMES)
def test_no_key_reaches_the_model_on_an_http_error(monkeypatch, bridge):
    def fail(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 500, "err", {}, io.BytesIO(b"upstream boom")
        )

    monkeypatch.setattr(_core.urllib.request, "urlopen", fail)
    _configured(monkeypatch, bridge)

    for name, _d, _s in bridge.tools:
        out = _core._make_handler(bridge, name)({})
        assert "TOPSECRET" not in out, f"{bridge.name}.{name} leaked the key"


@pytest.mark.parametrize("bridge", BRIDGES, ids=NAMES)
def test_the_startup_log_line_never_prints_a_secret(monkeypatch, capsys, bridge):
    """register() prints where the bridge points. The URL belongs there; the
    tool key never does."""
    _configured(monkeypatch, bridge)
    _core.register_bridge(FakeCtx(), bridge)

    out = capsys.readouterr().out
    assert "TOPSECRET" not in out, f"{bridge.name} printed its key at registration"
    # The operational check after any change is this substring.
    assert f"registered {len(bridge.tools)} tools" in out
