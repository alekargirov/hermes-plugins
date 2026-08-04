"""Tool handlers — what runs when the LLM calls each tickets tool.

Every handler delegates to ``_http.execute`` with its spec. Generated from the
legacy MCP YAML; do not edit by hand.
"""
from __future__ import annotations

from ._http import execute


_SPECS = {
    "tickets_create": {
        "method": "POST",
        "url": "{env.TICKETS_URL}/api/tickets/create",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "tickets_mine": {
        "method": "GET",
        "url": "{env.TICKETS_URL}/api/tickets/mine",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "tickets_get": {
        "method": "GET",
        "url": "{env.TICKETS_URL}/api/tickets/get?id={arg.id}",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "tickets_update": {
        "method": "POST",
        "url": "{env.TICKETS_URL}/api/tickets/update",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "tickets_comment": {
        "method": "POST",
        "url": "{env.TICKETS_URL}/api/tickets/comment",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "tickets_list": {
        "method": "GET",
        "url": "{env.TICKETS_URL}/api/tickets/list?status={arg.status}",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "tickets_assign": {
        "method": "POST",
        "url": "{env.TICKETS_URL}/api/tickets/assign",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "tickets_close": {
        "method": "POST",
        "url": "{env.TICKETS_URL}/api/tickets/close",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "tickets_reopen": {
        "method": "POST",
        "url": "{env.TICKETS_URL}/api/tickets/reopen",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    }
}


def tickets_create(args: dict, **kwargs) -> str:
    return execute(_SPECS["tickets_create"], args)


def tickets_mine(args: dict, **kwargs) -> str:
    return execute(_SPECS["tickets_mine"], args)


def tickets_get(args: dict, **kwargs) -> str:
    return execute(_SPECS["tickets_get"], args)


def tickets_update(args: dict, **kwargs) -> str:
    return execute(_SPECS["tickets_update"], args)


def tickets_comment(args: dict, **kwargs) -> str:
    return execute(_SPECS["tickets_comment"], args)


def tickets_list(args: dict, **kwargs) -> str:
    return execute(_SPECS["tickets_list"], args)


def tickets_assign(args: dict, **kwargs) -> str:
    return execute(_SPECS["tickets_assign"], args)


def tickets_close(args: dict, **kwargs) -> str:
    return execute(_SPECS["tickets_close"], args)


def tickets_reopen(args: dict, **kwargs) -> str:
    return execute(_SPECS["tickets_reopen"], args)



