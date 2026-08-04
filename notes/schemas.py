"""Tool schemas — what the LLM sees for each notes tool.

Generated from the legacy MCP YAML; do not edit by hand.
"""


SCHEMAS = {
    "notes_tree": {
        "name": "notes_tree",
        "description": "Full folder/file tree of the notes vault. Returns the whole tree; use notes_list to scope to one folder level.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "notes_list": {
        "name": "notes_list",
        "description": "List direct subfolders and notes at one folder level. Omit path for vault root.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Folder path (e.g. \"claude/conventions\"). Empty = vault root."
                }
            },
            "required": []
        }
    },
    "notes_read": {
        "name": "notes_read",
        "description": "Read a note by path. Path is \"folder/Title\" — no .md extension (e.g. \"claude/conventions/INDEX\"). Returns the markdown AND every comment thread on it (see commentsText for a readable rendering). Comments are anchored by \"^a1b2c3\" markers in the content: KEEP those markers when you rewrite a note, they are what holds each comment to its paragraph.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Note path (folder/Title, no .md)"
                }
            },
            "required": [
                "path"
            ]
        }
    },
    "notes_search": {
        "name": "notes_search",
        "description": "Full-text search (case-insensitive substring over title+content) across the notes vault. Returns matching notes with full content.",
        "parameters": {
            "type": "object",
            "properties": {
                "q": {
                    "type": "string",
                    "description": "Search query"
                }
            },
            "required": [
                "q"
            ]
        }
    },
    "notes_write": {
        "name": "notes_write",
        "description": "Create or update a note. Path must be under YOUR top-level folder (your username is the write key; e.g. claude/...). Content is a markdown string. Path is \"folder/Title\" — no .md. Preserve any \"^a1b2c3\" block markers the note came with: they anchor existing comments, and dropping them makes the server re-attach by matching text, or orphan the thread when it can't.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Note path under your folder (e.g. \"claude/apps/notes-srv/overview\")"
                },
                "content": {
                    "type": "string",
                    "description": "Full note contents (markdown)"
                }
            },
            "required": [
                "path",
                "content"
            ]
        }
    },
    "notes_comments": {
        "name": "notes_comments",
        "description": "List the comment threads on a note (anchors, comments, replies) without its content. notes_read already includes these — use this only when you want the threads alone.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Note path, \"folder/Title\" — no .md"
                }
            },
            "required": [
                "path"
            ]
        }
    },
    "notes_comment_reply": {
        "name": "notes_comment_reply",
        "description": "Reply to a comment thread on a note. Pass the anchor exactly as notes_read shows it in brackets — \"[^a1b2c3]\" means anchor \"a1b2c3\". Your reply is attributed to you by name. You can only answer threads a human opened; replying on an anchor with no thread is rejected, and there is no way to start one.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Note path, \"folder/Title\" — no .md"
                },
                "anchor": {
                    "type": "string",
                    "description": "Block anchor of the thread, without the caret (e.g. \"a1b2c3\")"
                },
                "body": {
                    "type": "string",
                    "description": "The reply text"
                }
            },
            "required": [
                "path",
                "anchor",
                "body"
            ]
        }
    },
    "notes_delete": {
        "name": "notes_delete",
        "description": "Delete a note by path. Must be under your own top-level folder. Path is \"folder/Title\" — no .md.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path of the note to delete"
                }
            },
            "required": [
                "path"
            ]
        }
    },
    "notes_move": {
        "name": "notes_move",
        "description": "Move or rename a note. Both paths must be under your own top-level folder. Paths are \"folder/Title\" — no .md.",
        "parameters": {
            "type": "object",
            "properties": {
                "from": {
                    "type": "string",
                    "description": "Current path"
                },
                "to": {
                    "type": "string",
                    "description": "New path"
                }
            },
            "required": [
                "from",
                "to"
            ]
        }
    }
}


def get(name: str) -> dict:
    return SCHEMAS[name]
