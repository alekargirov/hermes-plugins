"""Shared contract for every DIRECT plugin.

These call third-party endpoints whose credentials live only on prod, so this
suite proves everything that does NOT need a live service: registration, auth,
URL construction, response shaping, and — most importantly — that no secret
escapes into a message the model will see.
"""
import json

import pytest

import cal
import media
import minimax
import tickets
from media import _core as _media_core


class _MediaService:
    """One service inside the merged `media` plugin, wearing the surface this
    suite walks.

    radarr, sonarr, lidarr, plex, nzb and tmdb were six plugin directories
    until 2026-08-15; now they are six Service descriptors inside one. The
    contract below is per-SERVICE, not per-directory, so each is presented with
    the same five attributes the standalone modules had.

    The facade exists so this file stays the SINGLE contract every direct
    plugin is held to. Forking it into a media suite and a not-media suite
    would let the two drift, and this is the file that stops someone shipping a
    plugin that leaks a key.
    """

    urllib = _media_core.urllib

    def __init__(self, svc):
        self._svc = svc
        self.__name__ = svc.name
        self.TOOLS = svc.tools
        self._redact = svc.redact

    def _call(self, tool, args):
        return _media_core._call(self._svc, tool, args)

    def register(self, ctx):
        _media_core.register_service(ctx, self._svc)


_MEDIA = {s.name: _MediaService(s) for s in media.SERVICES}
radarr, sonarr, lidarr, plex, nzb, tmdb = (
    _MEDIA[n] for n in ("radarr", "sonarr", "lidarr", "plex", "nzb", "tmdb")
)

# tickets and cal are OUR apps, not third-party, but they are built the same way
# and the contract below is about the shape and the failure paths, which apply
# equally. They are here so nobody adds a plugin that leaks a key.
DIRECT = [radarr, sonarr, lidarr, plex, tmdb, nzb, minimax, tickets, cal]
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
    neighbour's schema and refused a change the tool supported.

    For the media services this is weak — the facade takes both its name and
    its toolset from the same Service field, so it cannot fail. The test that
    actually holds that line after the merge is
    test_the_merge_did_not_collapse_the_six_toolsets below.
    """
    ctx = _reg(mod)
    assert {t["toolset"] for t in ctx.registered} == {mod.__name__}


def test_the_merge_did_not_collapse_the_six_toolsets():
    """One plugin, six toolsets — the whole point of how media is built.

    Six directories became one on 2026-08-15 to share a core. The toolsets did
    NOT merge with them, and must not: 42 tools under a flat `media` toolset
    re-creates the fin3/`todo` failure above, where the model read a
    neighbour's schema and refused a change the tool supported.

    If someone "simplifies" media by passing a single toolset to
    register_service, this is the test that catches it.
    """
    ctx = FakeCtx()
    media.register(ctx)

    by_toolset = {}
    for t in ctx.registered:
        by_toolset.setdefault(t["toolset"], []).append(t["name"])

    assert set(by_toolset) == {"radarr", "sonarr", "lidarr", "plex", "nzb", "tmdb"}
    assert len(ctx.registered) == 42, "media lost or gained a tool"
    assert len({t["name"] for t in ctx.registered}) == 42, "a tool name collides"

    # Each tool sits under the toolset its name claims. A tool answering
    # `sonarr_queue` from the radarr toolset would route to the wrong library.
    for toolset, names in by_toolset.items():
        assert all(n.startswith(f"{toolset}_") for n in names), toolset


@pytest.mark.parametrize("mod", DIRECT, ids=NAMES)
def test_every_tool_has_a_description_and_an_object_schema(mod):
    for t in _reg(mod).registered:
        assert t["description"].strip(), f"{t['name']} has no description"
        # `schema` IS the function object; the arguments live under
        # `parameters`. This test asserted the bare shape until 2026-08-05, so
        # it passed all the way through the defect it was meant to catch.
        # tests/test_schema_shape.py now proves the shape against hermes' own
        # pipeline rather than a hand-written expectation.
        params = t["schema"]["parameters"]
        assert params["type"] == "object"
        for req in params["required"]:
            assert req in params["properties"], f"{t['name']}: {req} not declared"


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
    "tickets": {"TICKETS_URL": "http://tickets:4200", "TICKETS_API_KEY": "SUPERSECRET"},
    "cal": {"CAL_URL": "http://cal:3020", "CAL_API_KEY": "SUPERSECRET"},
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


# Plugins whose credential is a header the service checks: URL set, key absent.
# nzb's credentials are in the URL path and tmdb's/minimax's only config IS the
# key, so their missing-config case above already covers this.
KEYED = {
    "radarr": "RADARR_API_KEY",
    "sonarr": "SONARR_API_KEY",
    "lidarr": "LIDARR_API_KEY",
    "plex": "PLEX_TOKEN",
    "tickets": "TICKETS_API_KEY",
    "cal": "CAL_API_KEY",
}


@pytest.mark.parametrize("mod", [m for m in DIRECT if m.__name__ in KEYED],
                         ids=[n for n in NAMES if n in KEYED])
def test_a_missing_key_is_named_not_left_as_a_bare_401(monkeypatch, mod):
    """URL set, key missing. Without a guard the request goes out with an empty
    auth header, the service answers 401, and the agent reports the backend as
    broken — alek lost a testing session to exactly that on tickets. The
    refusal must name the variable, and must not fire a request."""
    called = {"n": 0}

    def count(req, timeout=None):
        called["n"] += 1
        return _Resp(b"[]")

    monkeypatch.setattr(mod.urllib.request, "urlopen", count)
    for k, v in SECRETS[mod.__name__].items():
        monkeypatch.setenv(k, v)
    var = KEYED[mod.__name__]
    monkeypatch.delenv(var, raising=False)

    out = json.loads(mod._call(mod.TOOLS[0], {}))
    assert out["ok"] is False
    assert var in out["message"], f"{mod.__name__}: refusal does not name {var}"
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


@pytest.mark.parametrize("mod", [tickets, cal], ids=["tickets", "cal"])
def test_our_user_scoped_apps_never_send_a_user_id(monkeypatch, mod):
    """Identity is the KEY, pinned per profile. If a user id were sent as well,
    a model that could influence it could act as someone else — and these two
    apps used to accept exactly that header with no key at all."""
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        return _Resp(b"{}")

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    for k, v in SECRETS[mod.__name__].items():
        monkeypatch.setenv(k, v)

    for tool in mod.TOOLS:
        mod._call(tool, {"user_id": "1", "userId": "1", "tg": "1"})
        assert "x-user-id" not in seen["headers"], f"{tool.name} sent a user id"
        assert seen["headers"]["x-api-key"] == "SUPERSECRET"


def test_music_gets_a_longer_timeout_than_the_rest_of_minimax():
    """MiniMax composes the whole track before replying. At the shared 60s a
    full set of lyrics timed out while three short lines got through, so the
    tool looked fine until someone wrote a real song (#178)."""
    by_name = {t.name: t for t in minimax.TOOLS}
    assert by_name["minimax_generate_music"].timeout >= 180
    for name in ("minimax_web_search", "minimax_understand_image",
                 "minimax_generate_image"):
        assert by_name[name].timeout == 60


@pytest.mark.parametrize("mod", [minimax, tmdb], ids=["minimax", "tmdb"])
def test_a_connection_failure_does_not_blame_the_api_key(monkeypatch, mod):
    """Both used to answer every failure with "check <PLUGIN>_API_KEY". A read
    timeout on a long music generation therefore told alek to rotate a key that
    was working. A bad key arrives as an HTTP 401 on the other branch, where it
    cannot be mistaken for anything else."""
    def boom(req, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(mod.urllib.request, "urlopen", boom)
    for k, v in SECRETS[mod.__name__].items():
        monkeypatch.setenv(k, v)

    msg = json.loads(mod._call(mod.TOOLS[0], {"query": "x", "id": 1}))["message"]
    assert "API_KEY" not in msg, f"{mod.__name__}: blames the key for a connection failure"


def test_minimax_names_a_timeout_as_a_timeout(monkeypatch):
    def slow(req, timeout=None):
        raise TimeoutError("The read operation timed out")

    monkeypatch.setattr(minimax.urllib.request, "urlopen", slow)
    monkeypatch.setenv("MINIMAX_API_KEY", "SUPERSECRET")
    music = [t for t in minimax.TOOLS if t.name == "minimax_generate_music"][0]

    out = json.loads(minimax._call(music, {"style": "s", "lyrics": "l"}))
    assert out["ok"] is False
    assert "timed out after 300s" in out["message"]
    assert "not an auth problem" in out["message"]
    assert "SUPERSECRET" not in out["message"]
