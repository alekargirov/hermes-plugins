"""Shared contract for every DIRECT plugin.

These call third-party endpoints whose credentials live only on prod, so this
suite proves everything that does NOT need a live service: registration, auth,
URL construction, response shaping, and — most importantly — that no secret
escapes into a message the model will see.
"""
import json

import pytest

import lidarr
import minimax
import nzb
import plex
import radarr
import sonarr
import tmdb

DIRECT = [radarr, sonarr, lidarr, plex, tmdb, nzb, minimax]
NAMES = [m.__name__ for m in DIRECT]


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


def _reg(mod):
    ctx = FakeCtx()
    mod.register(ctx)
    return ctx


@pytest.mark.parametrize("mod", DIRECT, ids=NAMES)
def test_each_plugin_uses_its_own_toolset(mod):
    """Never a shared toolset: when fin3 shared `todo` the model read a
    neighbour's schema and refused a change the tool supported."""
    ctx = _reg(mod)
    assert {t["toolset"] for t in ctx.registered} == {mod.__name__}


@pytest.mark.parametrize("mod", DIRECT, ids=NAMES)
def test_every_tool_has_a_description_and_an_object_schema(mod):
    for t in _reg(mod).registered:
        assert t["description"].strip(), f"{t['name']} has no description"
        assert t["schema"]["type"] == "object"
        for req in t["schema"]["required"]:
            assert req in t["schema"]["properties"], f"{t['name']}: {req} not declared"


@pytest.mark.parametrize("mod", DIRECT, ids=NAMES)
def test_tool_names_are_unique(mod):
    names = [t.name for t in mod.TOOLS]
    assert len(names) == len(set(names))


SECRETS = {
    "radarr": {"RADARR_URL": "http://radarr:7878", "RADARR_API_KEY": "SUPERSECRET"},
    "sonarr": {"SONARR_URL": "http://sonarr:8989", "SONARR_API_KEY": "SUPERSECRET"},
    "lidarr": {"LIDARR_URL": "http://lidarr:8686", "LIDARR_API_KEY": "SUPERSECRET"},
    "plex": {"PLEX_URL": "http://plex:32400", "PLEX_TOKEN": "SUPERSECRET"},
    "tmdb": {"TMDB_API_KEY": "SUPERSECRET"},
    "nzb": {"NZB_URL": "http://nzb:6789/", "NZB_USER": "u", "NZB_PASSWORD": "SUPERSECRET"},
    "minimax": {"MINIMAX_API_KEY": "SUPERSECRET"},
}


@pytest.mark.parametrize("mod", DIRECT, ids=NAMES)
def test_no_secret_reaches_the_model_when_the_host_is_unreachable(monkeypatch, mod):
    """The failure path is the dangerous one: tmdb puts its key in the query
    string and nzb puts its password in the URL path, so a message that names
    the URL would put the secret in the transcript."""
    def boom(req, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(mod.urllib.request, "urlopen", boom)
    for k, v in SECRETS[mod.__name__].items():
        monkeypatch.setenv(k, v)

    for tool in mod.TOOLS:
        out = mod._call(tool, {})
        assert "SUPERSECRET" not in out, f"{mod.__name__}.{tool.name} leaked a secret"
        assert json.loads(out)["ok"] is False


@pytest.mark.parametrize("mod", DIRECT, ids=NAMES)
def test_no_secret_reaches_the_model_on_an_http_error(monkeypatch, mod):
    import io
    import urllib.error

    def fail(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 500, "err", {}, io.BytesIO(b"upstream boom"))

    monkeypatch.setattr(mod.urllib.request, "urlopen", fail)
    for k, v in SECRETS[mod.__name__].items():
        monkeypatch.setenv(k, v)

    for tool in mod.TOOLS:
        out = mod._call(tool, {})
        assert "SUPERSECRET" not in out, f"{mod.__name__}.{tool.name} leaked a secret"


@pytest.mark.parametrize("mod", DIRECT, ids=NAMES)
def test_missing_config_refuses_without_firing_a_request(monkeypatch, mod):
    called = {"n": 0}

    def count(req, timeout=None):
        called["n"] += 1
        return _Resp(b"[]")

    monkeypatch.setattr(mod.urllib.request, "urlopen", count)
    for k in SECRETS[mod.__name__]:
        monkeypatch.delenv(k, raising=False)

    out = json.loads(mod._call(mod.TOOLS[0], {}))
    assert out["ok"] is False
    assert called["n"] == 0


def test_nzb_bakes_the_rpc_method_in_and_never_takes_it_from_the_model():
    """The agent must not be able to invoke arbitrary NZBGet RPCs."""
    for tool in nzb.TOOLS:
        assert tool.body and '"method"' in tool.body
        assert "method" not in tool.schema["properties"]


def test_minimax_json_escapes_body_arguments():
    out = minimax._render('{"q":"{arg.query}"}', {"query": 'say "hi"\nnow'},
                          quote=False, json_escape=True)
    assert json.loads(out) == {"q": 'say "hi"\nnow'}


def test_tmdb_redacts_its_key_and_nzb_redacts_its_password():
    assert "SECRET" not in tmdb._redact("https://x/3/y?api_key=SECRET&q=1")
    assert "PASS" not in nzb._redact("http://nzb:6789/user:PASS/jsonrpc")


@pytest.mark.parametrize("mod", DIRECT, ids=NAMES)
def test_the_startup_log_line_never_prints_a_secret(monkeypatch, capsys, mod):
    """register() prints a line naming where the plugin points. For most
    plugins that is a URL, but tmdb's and minimax's only config IS the key —
    and the first version of both printed it straight into the container log,
    where docker keeps it. Error paths were covered; this line was not."""
    for k, v in SECRETS[mod.__name__].items():
        monkeypatch.setenv(k, v)
    _reg(mod)
    assert "SUPERSECRET" not in capsys.readouterr().out, (
        f"{mod.__name__} printed a secret at registration"
    )
