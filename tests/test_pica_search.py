"""The contract for pica-search.

This plugin exists for its tool DESCRIPTIONS as much as its behaviour — the
plugins repo is the only surface shared by every agent, so the descriptions are
the fleet's prompt. Several tests below assert on wording. That is deliberate:
if someone softens "do NOT use web_extract" into a suggestion, the failure it
prevents (prod, 2026-08-16: the model tried web_extract, failed, then shelled
out to curl) comes straight back and nothing else would catch it.
"""

import json

import pytest

import pica_search


class FakeCtx:
    def __init__(self):
        self.registered = []

    def register_tool(self, name, toolset, schema, handler, description):
        self.registered.append(
            {"name": name, "toolset": toolset, "schema": schema,
             "handler": handler, "description": description}
        )


def _handler_for(ctx, name):
    return next(t["handler"] for t in ctx.registered if t["name"] == name)


def _fake_post(monkeypatch, responses):
    """Replace _post with a scripted responder keyed by endpoint path."""
    seen = []

    def fake(path, payload):
        seen.append((path, payload))
        r = responses[path]
        return r(payload) if callable(r) else r

    monkeypatch.setattr(pica_search, "_post", fake)
    return seen


# ─── read_page ───────────────────────────────────────────────────────────────

def test_read_page_returns_markdown(monkeypatch):
    seen = _fake_post(monkeypatch, {"/md": {"markdown": "# Hello\ntext"}})

    out = json.loads(pica_search._tool_read_page({"url": "https://example.com"}))

    assert out["ok"] is True
    assert out["markdown"] == "# Hello\ntext"
    # f=fit, always. raw is the whole DOM and llm is silently broken on this
    # deployment (ticket #207) as well as being a metered call.
    assert seen[0] == ("/md", {"url": "https://example.com", "f": "fit"})


def test_read_page_treats_empty_markdown_as_failure(monkeypatch):
    _fake_post(monkeypatch, {"/md": {"markdown": "\n"}})

    out = json.loads(pica_search._tool_read_page({"url": "https://example.com"}))

    # crawl4ai answers success:true with an empty string in several cases.
    # Passing that through as a successful read is how an agent ends up
    # confidently summarising nothing.
    assert out["ok"] is False
    assert "empty markdown" in out["message"]


def test_read_page_requires_a_url():
    out = json.loads(pica_search._tool_read_page({}))
    assert out["ok"] is False


def test_transport_failure_reaches_the_model(monkeypatch):
    _fake_post(monkeypatch, {"/md": {"ok": False, "message": "crawl4ai HTTP 401 ..."}})

    out = json.loads(pica_search._tool_read_page({"url": "https://example.com"}))

    assert out["ok"] is False
    assert "401" in out["message"]


# ─── read_pages ──────────────────────────────────────────────────────────────

def test_read_pages_batches_and_reports_per_url(monkeypatch):
    def md(payload):
        if payload["url"].endswith("/bad"):
            return {"ok": False, "message": "crawl4ai HTTP 404 ..."}
        return {"markdown": "ok"}

    _fake_post(monkeypatch, {"/md": md})

    out = json.loads(pica_search._tool_read_pages(
        {"urls": ["https://a.com", "https://b.com/bad", "https://c.com"]}
    ))

    assert out["requested"] == 3
    assert out["succeeded"] == 2
    # One dead URL must not cost you the other two.
    assert [r["ok"] for r in out["results"]] == [True, False, True]


def test_read_pages_caps_the_batch(monkeypatch):
    _fake_post(monkeypatch, {"/md": {"markdown": "ok"}})
    urls = [f"https://e.com/{i}" for i in range(pica_search.MAX_PAGES + 5)]

    out = json.loads(pica_search._tool_read_pages({"urls": urls}))

    # The model chooses the URLs; it does not get to choose how much of the
    # internet arrives in one turn.
    assert out["requested"] == pica_search.MAX_PAGES


def test_read_pages_accepts_a_json_string(monkeypatch):
    _fake_post(monkeypatch, {"/md": {"markdown": "ok"}})

    out = json.loads(pica_search._tool_read_pages({"urls": '["https://a.com"]'}))

    assert out["succeeded"] == 1


def test_read_pages_rejects_an_empty_list():
    out = json.loads(pica_search._tool_read_pages({"urls": []}))
    assert out["ok"] is False


# ─── list_urls ───────────────────────────────────────────────────────────────

_CRAWL = {
    "results": [{
        "links": {
            "internal": [
                {"href": "https://e.com/a", "text": "  A  "},
                {"href": "https://e.com/a", "text": "dupe"},
                {"href": "https://e.com/b", "text": "B"},
            ],
            "external": [{"href": "https://other.com/x"}],
        }
    }]
}


def test_list_urls_splits_and_dedupes(monkeypatch):
    _fake_post(monkeypatch, {"/crawl": _CRAWL})

    out = json.loads(pica_search._tool_list_urls({"url": "https://e.com"}))

    assert out["ok"] is True
    assert [i["url"] for i in out["internal"]] == ["https://e.com/a", "https://e.com/b"]
    assert out["internal"][0]["text"] == "A"
    assert out["external"] == ["https://other.com/x"]


def test_list_urls_handles_an_empty_crawl(monkeypatch):
    _fake_post(monkeypatch, {"/crawl": {"results": []}})

    out = json.loads(pica_search._tool_list_urls({"url": "https://e.com"}))

    assert out["ok"] is False


# ─── registration and the descriptions themselves ────────────────────────────

def test_every_tool_lands_in_the_pica_search_toolset():
    ctx = FakeCtx()
    pica_search.register(ctx)

    assert len(ctx.registered) == len(pica_search.TOOLS) == 3
    # Underscore, not the hyphenated plugin/dir name: the repo's cross-plugin
    # invariant is that every tool name is prefixed by its toolset, and
    # `pica-search_read_page` is not a legal tool name. See test_schema_shape.
    assert {t["toolset"] for t in ctx.registered} == {"pica_search"}


def test_schema_is_a_full_openai_function_object():
    ctx = FakeCtx()
    pica_search.register(ctx)

    for t in ctx.registered:
        # A bare properties dict makes hermes' sanitizer drop the arguments AND
        # the description — the model then sees a nameless no-arg tool.
        assert set(t["schema"]) == {"name", "description", "parameters"}
        assert t["schema"]["name"] == t["name"]
        assert t["schema"]["parameters"]["type"] == "object"
        assert t["schema"]["description"] == t["description"]


def test_tool_names_are_unique_and_prefixed():
    names = [t[0] for t in pica_search.TOOLS]
    assert len(names) == len(set(names))
    assert all(n.startswith("pica_search_") for n in names)


def test_the_read_description_steers_away_from_web_extract_and_curl():
    desc = next(t[1] for t in pica_search.TOOLS if t[0] == "pica_search_read_page")
    # This wording is the entire fix for the prod failure. Keep it imperative.
    assert "web_extract" in desc
    assert "terminal/curl" in desc
    assert "SearXNG" in desc


def test_the_list_description_positions_it_before_reading():
    desc = next(t[1] for t in pica_search.TOOLS if t[0] == "pica_search_list_urls")
    assert "BEFORE reading" in desc
