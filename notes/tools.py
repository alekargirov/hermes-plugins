"""Tool handlers — what runs when the LLM calls each notes tool.

Every handler delegates to ``_http.execute`` with its spec. Generated from the
legacy MCP YAML; do not edit by hand.
"""
from __future__ import annotations

from ._http import execute


_SPECS = {
    "notes_tree": {
        "method": "GET",
        "url": "{env.NOTES_URL|http://notes:3000}/api/v2/tree"
    },
    "notes_list": {
        "method": "GET",
        "url": "{env.NOTES_URL|http://notes:3000}/api/v2/folders/list?path={arg.path|}"
    },
    "notes_read": {
        "method": "GET",
        "url": "{env.NOTES_URL|http://notes:3000}/api/v2/notes/read?path={arg.path}"
    },
    "notes_search": {
        "method": "GET",
        "url": "{env.NOTES_URL|http://notes:3000}/api/v2/notes/search?q={arg.q}"
    },
    "notes_write": {
        "method": "POST",
        "url": "{env.NOTES_URL|http://notes:3000}/api/v2/notes/write",
        "headers": {
            "X-API-Key": "{env.USER_NAME}",
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "notes_comments": {
        "method": "GET",
        "url": "{env.NOTES_URL|http://notes:3000}/api/v2/notes/comments?path={arg.path}"
    },
    "notes_comment_reply": {
        "method": "POST",
        "url": "{env.NOTES_URL|http://notes:3000}/api/v2/notes/comments/reply",
        "headers": {
            "X-API-Key": "{env.USER_NAME}",
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "notes_delete": {
        "method": "POST",
        "url": "{env.NOTES_URL|http://notes:3000}/api/v2/notes/delete",
        "headers": {
            "X-API-Key": "{env.USER_NAME}",
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "notes_move": {
        "method": "POST",
        "url": "{env.NOTES_URL|http://notes:3000}/api/v2/notes/move",
        "headers": {
            "X-API-Key": "{env.USER_NAME}",
            "X-User-Id": "{env.USER_ID}"
        }
    }
}


def notes_tree(args: dict, **kwargs) -> str:
    return execute(_SPECS["notes_tree"], args)


def notes_list(args: dict, **kwargs) -> str:
    return execute(_SPECS["notes_list"], args)


def notes_read(args: dict, **kwargs) -> str:
    return execute(_SPECS["notes_read"], args)


def notes_search(args: dict, **kwargs) -> str:
    return execute(_SPECS["notes_search"], args)


def notes_write(args: dict, **kwargs) -> str:
    return execute(_SPECS["notes_write"], args)


def notes_comments(args: dict, **kwargs) -> str:
    return execute(_SPECS["notes_comments"], args)


def notes_comment_reply(args: dict, **kwargs) -> str:
    return execute(_SPECS["notes_comment_reply"], args)


def notes_delete(args: dict, **kwargs) -> str:
    return execute(_SPECS["notes_delete"], args)


def notes_move(args: dict, **kwargs) -> str:
    return execute(_SPECS["notes_move"], args)



