"""Tool schemas — what the LLM sees for each minimax tool.

Generated from the legacy MCP YAML; do not edit by hand.
"""


SCHEMAS = {
    "web_search": {
        "name": "web_search",
        "description": "Search the web using MiniMax's real-time search. Returns organic results with titles, URLs, snippets, and dates. Use for current events, facts, prices, or anything that needs live information.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query. Aim for 3–5 keywords. Include dates for time-sensitive topics (e.g. \"MiniMax M3 release 2026\")."
                }
            },
            "required": [
                "query"
            ]
        }
    },
    "understand_image": {
        "name": "understand_image",
        "description": "Analyse an image from a URL using MiniMax M3 vision. Describe, extract text, identify objects, or answer questions about image content. The reply may start with a <think>…</think> reasoning block — ignore it and use the text after it. JPEG/PNG/GIF/WebP up to 20MB; the URL must be publicly fetchable (hosts that block hotlinking, e.g. Wikimedia, fail with \"remote returned status 403\").",
        "parameters": {
            "type": "object",
            "properties": {
                "image_url": {
                    "type": "string",
                    "description": "HTTPS URL to a JPEG, PNG, GIF, or WebP image (publicly fetchable)."
                },
                "prompt": {
                    "type": "string",
                    "description": "What to do with the image — describe it, extract text, identify objects, answer a question about it, etc."
                }
            },
            "required": [
                "image_url",
                "prompt"
            ]
        }
    },
    "generate_image": {
        "name": "generate_image",
        "description": "Generate an image from a text prompt using MiniMax image-01. Returns a temporary download URL (expires after ~24h — fetch/save it promptly). Describe subject, style, lighting, and composition in the prompt for best results.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed description of the desired image — subject, style, lighting, composition."
                },
                "aspect_ratio": {
                    "type": "string",
                    "description": "Aspect ratio: 1:1 (default), 16:9, 9:16, 4:3, 3:4, 3:2, 2:3, or 21:9."
                }
            },
            "required": [
                "prompt"
            ]
        }
    },
    "generate_music": {
        "name": "generate_music",
        "description": "Generate a song (vocals + instruments) from a style prompt and lyrics using MiniMax music-2.6. Returns a temporary MP3 URL (expires after ~24h — fetch/save it promptly). Songs run roughly 1–3 minutes.",
        "parameters": {
            "type": "object",
            "properties": {
                "style": {
                    "type": "string",
                    "description": "Style/mood description, comma-separated works well (e.g. \"Soulful Blues, Rainy Night, Melancholy, Male Vocals, Slow Tempo\")."
                },
                "lyrics": {
                    "type": "string",
                    "description": "Song lyrics, 10–1000 characters. Use newlines between lines and section tags like [Verse], [Chorus], [Bridge] for structure."
                }
            },
            "required": [
                "style",
                "lyrics"
            ]
        }
    }
}


def get(name: str) -> dict:
    return SCHEMAS[name]
