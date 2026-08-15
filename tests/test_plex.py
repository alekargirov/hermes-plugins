"""plex's own behaviour: the collection URLs, the machine-id guard, the reads.

The URL shapes asserted below are not invented from the docs — Plex's
collection endpoints are undocumented. Each was run against a live Plex
(1.43.2) on 2026-08-15 before the tools were written: create with one key,
create with two comma-separated keys, add, remove one child, delete the
collection. The test collections were removed afterwards. What these tests
guard is that the tools keep emitting the calls that were observed to work.
"""
import json

import pytest

from media import _core
from media import plex as _plex_mod

MID = "63aa58a423e370d66bbedd42bd99b3e071c9d18a"
URI = f"server://{MID}/com.plexapp.plugins.library/library/metadata"


class FakeCtx:
    def __init__(self):
        self.registered = []

    def register_tool(self, name, toolset, schema, handler, description):
        self.registered.append({"name": name, "toolset": toolset, "schema": schema,
                                "handler": handler, "description": description})


class _Resp:
    """urllib's HTTPResponse carries .status, and _core reads it when the body
    is empty. A fake without it would not be a fake of the real thing."""

    status = 200

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
    _core.register_service(ctx, _plex_mod.SERVICE)
    return ctx


def _handler_for(name):
    return next(t["handler"] for t in _registered().registered if t["name"] == name)


@pytest.fixture
def spy(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        seen["body"] = req.data.decode() if req.data else None
        return _Resp(seen.get("respond", b"{}"))

    monkeypatch.setattr(_core.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("PLEX_URL", "http://plex:32400")
    monkeypatch.setenv("PLEX_TOKEN", "secret")
    monkeypatch.setenv("PLEX_MACHINE_ID", MID)
    return seen


def test_all_tools_register_under_the_plex_toolset():
    ctx = _registered()
    assert len(ctx.registered) == 11
    assert {t["toolset"] for t in ctx.registered} == {"plex"}
    assert all(t["description"].strip() for t in ctx.registered)


def test_every_call_sends_the_token_as_a_header_never_the_query(spy):
    _handler_for("plex_sections")({})
    assert spy["headers"]["x-plex-token"] == "secret"
    assert "secret" not in spy["url"]


def test_reads_do_not_need_the_machine_id(spy, monkeypatch):
    """The four original tools and the three collection reads must keep working
    on a profile that never sets PLEX_MACHINE_ID."""
    monkeypatch.delenv("PLEX_MACHINE_ID")
    out = _handler_for("plex_collections")({"section_id": 1})
    assert spy["url"] == "http://plex:32400/library/sections/1/collections"
    assert "PLEX_MACHINE_ID" not in out


def test_create_emits_the_verified_url(spy):
    _handler_for("plex_collection_create")(
        {"title": "Heist Films", "section_id": 1, "rating_keys": "721,1378"}
    )
    assert spy["method"] == "POST"
    assert spy["url"] == (
        "http://plex:32400/library/collections"
        "?type=1&smart=0&title=Heist%20Films&sectionId=1"
        f"&uri={URI}/721%2C1378"
    )


def test_create_sends_no_body(spy):
    """Everything travels in the query string. The default for a POST is
    json.dumps(args), which would put the title and the keys in a body Plex
    ignores — harmless until someone reads the log and believes it."""
    _handler_for("plex_collection_create")(
        {"title": "x", "section_id": 1, "rating_keys": "721"}
    )
    assert spy["body"] is None


def test_create_takes_a_list_of_keys_as_well_as_a_string(spy):
    """A model answering a 'comma-separated' schema with a JSON array is common
    enough that the repr must never reach the wire."""
    _handler_for("plex_collection_create")(
        {"title": "x", "section_id": 1, "rating_keys": ["721", 1378]}
    )
    assert spy["url"].endswith(f"&uri={URI}/721%2C1378")


def test_item_type_defaults_to_movie_and_can_be_overridden(spy):
    _handler_for("plex_collection_create")(
        {"title": "x", "section_id": 2, "rating_keys": "9", "item_type": 2}
    )
    assert "?type=2&smart=0" in spy["url"]


def test_add_puts_the_collection_in_the_path_and_the_items_in_the_uri(spy):
    _handler_for("plex_collection_add")(
        {"collection_key": 9060, "rating_keys": "1378"}
    )
    assert spy["method"] == "PUT"
    assert spy["url"] == (
        f"http://plex:32400/library/collections/9060/items?uri={URI}/1378"
    )


def test_remove_deletes_one_child_not_the_collection(spy):
    _handler_for("plex_collection_remove")(
        {"collection_key": 9060, "rating_key": 721}
    )
    assert spy["method"] == "DELETE"
    assert spy["url"] == "http://plex:32400/library/collections/9060/children/721"


def test_delete_targets_the_collections_own_metadata(spy):
    _handler_for("plex_collection_delete")({"collection_key": 9060})
    assert spy["method"] == "DELETE"
    assert spy["url"] == "http://plex:32400/library/metadata/9060"


def test_the_writes_refuse_by_name_without_the_machine_id(monkeypatch):
    """Unset, the uri renders as server:///com.plexapp... — a well-formed
    request that creates an EMPTY collection and reports success. Nothing
    downstream can tell you why, so it has to stop here."""
    monkeypatch.setenv("PLEX_URL", "http://plex:32400")
    monkeypatch.setenv("PLEX_TOKEN", "secret")
    monkeypatch.delenv("PLEX_MACHINE_ID", raising=False)

    def explode(req, timeout=None):
        raise AssertionError("the request must not go out")

    monkeypatch.setattr(_core.urllib.request, "urlopen", explode)

    for name in ("plex_collection_create", "plex_collection_add"):
        out = json.loads(_handler_for(name)({"title": "x", "section_id": 1,
                                             "collection_key": 1,
                                             "rating_keys": "721"}))
        assert out["ok"] is False
        assert "PLEX_MACHINE_ID" in out["message"]
        assert name in out["message"]


def test_a_missing_token_still_refuses_by_name(monkeypatch):
    monkeypatch.setenv("PLEX_URL", "http://plex:32400")
    monkeypatch.delenv("PLEX_TOKEN", raising=False)
    out = json.loads(_handler_for("plex_collection_create")(
        {"title": "x", "section_id": 1, "rating_keys": "721"}
    ))
    assert out["ok"] is False
    assert "PLEX_TOKEN" in out["message"]


def test_an_empty_200_reports_success_instead_of_an_empty_string(spy):
    """Plex answers a successful DELETE with 200 and no body. Returned raw,
    "" is indistinguishable from a tool that did nothing, and the model has to
    guess whether the collection is gone. Verified live: delete returns empty,
    remove-a-child returns XML."""
    spy["respond"] = b""
    out = json.loads(_handler_for("plex_collection_delete")({"collection_key": 9060}))
    assert out["ok"] is True
    assert "plex_collection_delete" in out["message"]
