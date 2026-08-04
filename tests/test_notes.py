import json

import pytest

import notes


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


def test_register_puts_every_tool_in_the_notes_toolset():
    ctx = FakeCtx()
    notes.register(ctx)
    assert len(ctx.registered) == len(notes.TOOLS)
    assert {t["toolset"] for t in ctx.registered} == {"notes"}


def test_tree_is_a_get_against_api_v2(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        return _Resp(b'{"tree": []}')

    monkeypatch.setattr(notes.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("NOTES_URL", "http://notes:3000")
    monkeypatch.setenv("NOTES_API_KEY", "claude")

    ctx = FakeCtx()
    notes.register(ctx)
    out = _handler_for(ctx, "notes_tree")({})

    assert seen["url"] == "http://notes:3000/api/v2/tree"
    assert seen["method"] == "GET"
    assert json.loads(out) == {"tree": []}


@pytest.mark.parametrize(
    "tool,args,expected_url",
    [
        ("notes_list", {"path": "claude"},
         "http://notes:3000/api/v2/folders/list?path=claude"),
        ("notes_list", {},
         "http://notes:3000/api/v2/folders/list"),
        ("notes_read", {"path": "claude/overview"},
         "http://notes:3000/api/v2/notes/read?path=claude%2Foverview"),
        ("notes_search", {"q": "hermes"},
         "http://notes:3000/api/v2/notes/search?q=hermes"),
        ("notes_comments", {"path": "claude/overview"},
         "http://notes:3000/api/v2/notes/comments?path=claude%2Foverview"),
    ],
)
def test_read_tools_build_the_right_url(monkeypatch, tool, args, expected_url):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        return _Resp(b"{}")

    monkeypatch.setattr(notes.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("NOTES_URL", "http://notes:3000")
    monkeypatch.setenv("NOTES_API_KEY", "claude")

    ctx = FakeCtx()
    notes.register(ctx)
    _handler_for(ctx, tool)(args)

    assert seen["url"] == expected_url
    assert seen["method"] == "GET"


def test_empty_optional_args_are_dropped_not_sent_blank(monkeypatch):
    """notes_list with no path must hit the bare URL — `?path=` is a different
    request to notes-srv than no query at all (bare = vault root)."""
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        return _Resp(b"{}")

    monkeypatch.setattr(notes.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("NOTES_URL", "http://notes:3000")

    ctx = FakeCtx()
    notes.register(ctx)
    _handler_for(ctx, "notes_list")({"path": ""})

    assert seen["url"] == "http://notes:3000/api/v2/folders/list"


def test_trailing_slash_on_notes_url_does_not_double_up(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        return _Resp(b"{}")

    monkeypatch.setattr(notes.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("NOTES_URL", "https://notes.pica.win/")

    ctx = FakeCtx()
    notes.register(ctx)
    _handler_for(ctx, "notes_tree")({})

    assert seen["url"] == "https://notes.pica.win/api/v2/tree"
