import json

import pytest

import recipes


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


def _registered():
    ctx = FakeCtx()
    recipes.register(ctx)
    return ctx


def test_every_tool_registers_under_the_recipes_toolset():
    ctx = _registered()
    assert len(ctx.registered) == len(recipes.TOOLS)
    assert {t["toolset"] for t in ctx.registered} == {"recipes"}


def test_tool_names_are_unique_and_prefixed():
    names = [t[0] for t in recipes.TOOLS]
    assert len(names) == len(set(names))
    assert all(n.startswith("recipes_") for n in names)


def test_every_tool_has_a_description_and_object_schema():
    """Descriptions are the agent's only guidance — an empty one is a bug."""
    for name, description, schema, *_ in recipes.TOOLS:
        assert description.strip(), f"{name} has no description"
        assert schema["type"] == "object", name
        assert isinstance(schema.get("required"), list), name


def test_required_args_are_declared_in_properties():
    for name, _d, schema, *_ in recipes.TOOLS:
        for req in schema["required"]:
            assert req in schema["properties"], f"{name}: required {req} not in properties"


@pytest.mark.parametrize(
    "tool,args,expected",
    [
        ("recipes_list", {"tag": "soup"}, "http://recipes:3019/api/v2/recipes?tag=soup"),
        ("recipes_list", {}, "http://recipes:3019/api/v2/recipes"),
        ("recipes_get", {"slug": "banitsa"},
         "http://recipes:3019/api/v2/recipes/get?slug=banitsa"),
        ("recipes_search", {"q": "star anise"},
         "http://recipes:3019/api/v2/recipes/search?q=star+anise"),
        ("recipes_tags", {}, "http://recipes:3019/api/v2/tags"),
    ],
)
def test_get_tools_build_the_right_url(monkeypatch, tool, args, expected):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        return _Resp(b"{}")

    monkeypatch.setattr(recipes.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("RECIPES_URL", "http://recipes:3019")

    _handler_for(_registered(), tool)(args)
    assert seen["url"] == expected
    assert seen["method"] == "GET"


def test_post_tools_send_their_args_as_a_json_body(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        seen["body"] = json.loads(req.data.decode())
        seen["ct"] = {k.lower(): v for k, v in req.header_items()}.get("content-type")
        return _Resp(b'{"ok":true}')

    monkeypatch.setattr(recipes.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("RECIPES_URL", "http://recipes:3019")

    _handler_for(_registered(), "recipes_tag_add")({"slug": "banitsa", "tag": "balkan"})
    assert seen["url"] == "http://recipes:3019/api/v2/tag/add"
    assert seen["method"] == "POST"
    assert seen["body"] == {"slug": "banitsa", "tag": "balkan"}
    assert seen["ct"] == "application/json"


def test_unreachable_names_the_url_and_the_env_var(monkeypatch):
    """A wrong RECIPES_URL must point at itself. See the vita3 night."""
    def fake_urlopen(req, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(recipes.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("RECIPES_URL", "http://recipes")  # port-less mistake

    out = json.loads(_handler_for(_registered(), "recipes_tags")({}))
    assert out["ok"] is False
    assert "http://recipes/api/v2/tags" in out["message"]
    assert "RECIPES_URL" in out["message"]


def test_http_error_becomes_a_refusal_not_an_exception(monkeypatch):
    import io
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 404, "Not Found", {}, io.BytesIO(b'{"error":"no such recipe"}')
        )

    monkeypatch.setattr(recipes.urllib.request, "urlopen", fake_urlopen)
    out = json.loads(_handler_for(_registered(), "recipes_get")({"slug": "nope"}))
    assert out["ok"] is False
    assert "404" in out["message"]
    assert "no such recipe" in out["message"]
