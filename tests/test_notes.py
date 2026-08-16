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


def test_write_posts_json_body_with_the_api_key(monkeypatch):
    # notes_write makes TWO round trips now — the write, then the read-back
    # that verifies it (see the _write_verified tests at the end of this file).
    # Record every request and assert against the write specifically; taking
    # "the last call" would silently start testing the read.
    seen = []

    def fake_urlopen(req, timeout=None):
        seen.append({
            "url": req.full_url,
            "method": req.get_method(),
            "body": json.loads(req.data.decode()) if req.data else None,
            "headers": {k.lower(): v for k, v in req.header_items()},
        })
        return _Resp(b'{"content": "hello"}')

    monkeypatch.setattr(notes.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("NOTES_URL", "http://notes:3000")
    monkeypatch.setenv("NOTES_API_KEY", "claude")

    ctx = FakeCtx()
    notes.register(ctx)
    _handler_for(ctx, "notes_write")({"path": "claude/scratch", "content": "hello"})

    write = seen[0]
    assert write["url"] == "http://notes:3000/api/v2/notes/write"
    assert write["method"] == "POST"
    assert write["body"] == {"path": "claude/scratch", "content": "hello"}
    assert write["headers"]["x-api-key"] == "claude"
    assert write["headers"]["content-type"] == "application/json"

    # The read-back carries the same key — it must be the caller's own read,
    # not an unauthenticated one that could see a note they cannot write.
    read = seen[1]
    assert read["url"] == "http://notes:3000/api/v2/notes/read?path=claude%2Fscratch"
    assert read["headers"]["x-api-key"] == "claude"


@pytest.mark.parametrize(
    "tool,args,expected_path",
    [
        ("notes_comment_reply",
         {"path": "claude/x", "anchor": "a1b2c3", "body": "ack"},
         "/api/v2/notes/comments/reply"),
        ("notes_move", {"from": "claude/a", "to": "claude/b"}, "/api/v2/notes/move"),
        ("notes_delete", {"path": "claude/a"}, "/api/v2/notes/delete"),
    ],
)
def test_write_tools_post_their_args_as_the_body(monkeypatch, tool, args, expected_path):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        seen["body"] = json.loads(req.data.decode())
        return _Resp(b'{"ok": true}')

    monkeypatch.setattr(notes.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("NOTES_URL", "http://notes:3000")
    monkeypatch.setenv("NOTES_API_KEY", "claude")

    ctx = FakeCtx()
    notes.register(ctx)
    _handler_for(ctx, tool)(args)

    assert seen["url"] == "http://notes:3000" + expected_path
    assert seen["method"] == "POST"
    assert seen["body"] == args


def test_http_error_becomes_a_refusal_not_an_exception(monkeypatch):
    """A 403 from vault.ts (writing outside your folder) must reach the model as
    a readable {ok:false}, so it can correct itself instead of the turn dying."""
    import io
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 403, "Forbidden", {},
            io.BytesIO(b'{"error":"key `claude` may not write `fin/x`"}'),
        )

    monkeypatch.setattr(notes.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("NOTES_URL", "http://notes:3000")
    monkeypatch.setenv("NOTES_API_KEY", "claude")

    ctx = FakeCtx()
    notes.register(ctx)
    out = json.loads(_handler_for(ctx, "notes_write")({"path": "fin/x", "content": "nope"}))

    assert out["ok"] is False
    assert "403" in out["message"]
    assert "may not write" in out["message"]


def test_unreachable_host_becomes_a_refusal_not_an_exception(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(notes.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("NOTES_URL", "http://notes")  # the port-less mistake

    ctx = FakeCtx()
    notes.register(ctx)
    out = json.loads(_handler_for(ctx, "notes_tree")({}))

    assert out["ok"] is False
    assert "unreachable" in out["message"]
    # The URL must be IN the message. Without it, a wrong NOTES_URL reads as a
    # broken plugin rather than a typo — which is exactly what a port-less
    # VITA3_URL did to vita3-bridge on prod for hours.
    assert "http://notes/api/v2/tree" in out["message"]
    assert "NOTES_URL" in out["message"]


def test_every_tool_name_is_unique_and_prefixed():
    names = [t[0] for t in notes.TOOLS]
    assert len(names) == len(set(names))
    assert all(n.startswith("notes_") for n in names)


# ─── notes_write verifies itself (2026-08-16) ────────────────────────────────
#
# Context: the kosh agent reported saving five notes that did not exist, then
# filed a ticket blaming a read-only API key that was in fact correct. It was
# fabricating both the successes and the errors. A prompt cannot fix that —
# "verify your writes" is one more thing a model can claim to have done. So
# notes_write reads the note back itself and the model only sees the verdict.


def _fake_call(monkeypatch, write_resp, read_resp):
    """Drive _write_verified by faking the two _call round trips."""
    calls = []

    def fake(method, path, args, arg_style):
        calls.append((method, path, dict(args or {})))
        if path.endswith("/write"):
            return write_resp
        return read_resp

    monkeypatch.setattr(notes, "_call", fake)
    return calls


_WROTE = json.dumps({"action": "created", "id": 1, "path": "claude/x", "content": "hello"})
_READ_OK = json.dumps({"id": 1, "path": "claude/x", "content": "hello"})


def test_write_reads_the_note_back_before_reporting_success(monkeypatch):
    calls = _fake_call(monkeypatch, _WROTE, _READ_OK)

    out = json.loads(notes._write_verified({"path": "claude/x", "content": "hello"}))

    assert out["verified"] is True
    assert out["verified_bytes"] == len("hello")
    # It must actually have gone back to the server — a verified flag the tool
    # sets without reading is the same lie in a different place.
    assert [c[1] for c in calls] == ["/api/v2/notes/write", "/api/v2/notes/read"]
    assert calls[1][2]["path"] == "claude/x"


def test_write_that_cannot_be_read_back_is_a_failure(monkeypatch):
    _fake_call(monkeypatch, _WROTE, json.dumps({"ok": False, "message": "notes HTTP 404: nope"}))

    out = json.loads(notes._write_verified({"path": "claude/x", "content": "hello"}))

    assert out["ok"] is False
    assert out["verified"] is False
    assert "did NOT persist" in out["message"]


def test_stored_content_differing_from_sent_is_a_failure(monkeypatch):
    _fake_call(monkeypatch, _WROTE, json.dumps({"content": "hello, but mangled"}))

    out = json.loads(notes._write_verified({"path": "claude/x", "content": "hello"}))

    assert out["ok"] is False
    assert out["verified"] is False
    assert out["sent_bytes"] == 5
    assert out["stored_bytes"] == len("hello, but mangled")


def test_a_trailing_newline_from_the_server_is_not_a_mismatch(monkeypatch):
    _fake_call(monkeypatch, _WROTE, json.dumps({"content": "hello\n"}))

    out = json.loads(notes._write_verified({"path": "claude/x", "content": "hello"}))

    assert out["verified"] is True


def test_a_failed_write_is_passed_through_unverified(monkeypatch):
    _fake_call(monkeypatch, json.dumps({"ok": False, "message": "notes HTTP 403: nope"}), _READ_OK)

    out = json.loads(notes._write_verified({"path": "kosh/x", "content": "hello"}))

    assert out["ok"] is False
    assert out["verified"] is False
    assert "403" in out["message"]


def test_notes_write_is_registered_with_the_verifying_handler():
    ctx = FakeCtx()
    notes.register(ctx)
    assert _handler_for(ctx, "notes_write") is notes._write_verified
    # and nothing else is
    others = [t for t in ctx.registered if t["name"] != "notes_write"]
    assert all(t["handler"] is not notes._write_verified for t in others)


def test_the_description_tells_the_model_what_verified_means():
    desc = next(t[1] for t in notes.TOOLS if t[0] == "notes_write")
    assert '"verified": true' in desc
    assert "never describe a note as saved" in desc
