"""Tool handlers — what runs when the LLM calls each minimax tool.

Every handler delegates to ``_http.execute`` with its spec. Generated from the
legacy MCP YAML; do not edit by hand.
"""
from __future__ import annotations

from ._http import execute


_SPECS = {
    "web_search": {
        "method": "POST",
        "url": "https://api.minimax.io/v1/coding_plan/search",
        "headers": {
            "Authorization": "Bearer {env.MINIMAX_API_KEY}",
            "MM-API-Source": "Minimax-MCP"
        },
        "body": "{\"q\":\"{arg.query}\"}"
    },
    "understand_image": {
        "method": "POST",
        "url": "https://api.minimax.io/v1/chat/completions",
        "headers": {
            "Authorization": "Bearer {env.MINIMAX_API_KEY}"
        },
        "body": "{\"model\":\"MiniMax-M3\",\"messages\":[{\"role\":\"user\",\"content\":[{\"type\":\"image_url\",\"image_url\":{\"url\":\"{arg.image_url}\"}},{\"type\":\"text\",\"text\":\"{arg.prompt}\"}]}],\"max_tokens\":2048}"
    },
    "generate_image": {
        "method": "POST",
        "url": "https://api.minimax.io/v1/image_generation",
        "headers": {
            "Authorization": "Bearer {env.MINIMAX_API_KEY}"
        },
        "body": "{\"model\":\"image-01\",\"prompt\":\"{arg.prompt}\",\"aspect_ratio\":\"{arg.aspect_ratio|1:1}\",\"response_format\":\"url\",\"n\":1}"
    },
    "generate_music": {
        "method": "POST",
        "url": "https://api.minimax.io/v1/music_generation",
        "headers": {
            "Authorization": "Bearer {env.MINIMAX_API_KEY}"
        },
        "body": "{\"model\":\"music-2.6\",\"prompt\":\"{arg.style}\",\"lyrics\":\"{arg.lyrics}\",\"audio_setting\":{\"sample_rate\":44100,\"bitrate\":256000,\"format\":\"mp3\"},\"output_format\":\"url\"}"
    }
}


def web_search(args: dict, **kwargs) -> str:
    return execute(_SPECS["web_search"], args)


def understand_image(args: dict, **kwargs) -> str:
    return execute(_SPECS["understand_image"], args)


def generate_image(args: dict, **kwargs) -> str:
    return execute(_SPECS["generate_image"], args)


def generate_music(args: dict, **kwargs) -> str:
    return execute(_SPECS["generate_music"], args)



