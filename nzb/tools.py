"""Tool handlers — what runs when the LLM calls each nzb tool.

Every handler delegates to ``_http.execute`` with its spec. Generated from the
legacy MCP YAML; do not edit by hand.
"""
from __future__ import annotations

from ._http import execute


_SPECS = {
    "nzb_status": {
        "method": "POST",
        "url": "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        "body": "{\"method\":\"status\"}"
    },
    "nzb_queue": {
        "method": "POST",
        "url": "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        "body": "{\"method\":\"listgroups\"}"
    },
    "nzb_history": {
        "method": "POST",
        "url": "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        "body": "{\"method\":\"history\",\"params\":[false]}"
    },
    "nzb_add": {
        "method": "POST",
        "url": "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        "body": "{\"method\":\"append\",\"params\":[\"{arg.name|}\",\"{arg.url}\",\"{arg.category|}\",0,false,false,\"\",0,\"SCORE\"]}"
    },
    "nzb_delete": {
        "method": "POST",
        "url": "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        "body": "{\"method\":\"editqueue\",\"params\":[\"GroupDelete\",0,\"\",[{arg.id}]]}"
    },
    "nzb_pause": {
        "method": "POST",
        "url": "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        "body": "{\"method\":\"pausedownload\"}"
    },
    "nzb_resume": {
        "method": "POST",
        "url": "{env.NZB_URL}{env.NZB_USER}:{env.NZB_PASSWORD}/jsonrpc",
        "body": "{\"method\":\"resumedownload\"}"
    }
}


def nzb_status(args: dict, **kwargs) -> str:
    return execute(_SPECS["nzb_status"], args)


def nzb_queue(args: dict, **kwargs) -> str:
    return execute(_SPECS["nzb_queue"], args)


def nzb_history(args: dict, **kwargs) -> str:
    return execute(_SPECS["nzb_history"], args)


def nzb_add(args: dict, **kwargs) -> str:
    return execute(_SPECS["nzb_add"], args)


def nzb_delete(args: dict, **kwargs) -> str:
    return execute(_SPECS["nzb_delete"], args)


def nzb_pause(args: dict, **kwargs) -> str:
    return execute(_SPECS["nzb_pause"], args)


def nzb_resume(args: dict, **kwargs) -> str:
    return execute(_SPECS["nzb_resume"], args)



