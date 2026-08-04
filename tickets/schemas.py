"""Tool schemas — what the LLM sees for each tickets tool.

Generated from the legacy MCP YAML; do not edit by hand.
"""


SCHEMAS = {
    "tickets_create": {
        "name": "tickets_create",
        "description": "File a ticket for the admin's attention. The admin gets a Telegram alert\nand reviews via the pica UI. Use this when you hit a bug, need a tool\ncapability you don't have, or want a human decision before proceeding.",
        "parameters": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "Short, specific subject line"
                },
                "body": {
                    "type": "string",
                    "description": "Detailed description (markdown OK; include what you tried, what failed, what you'd like)"
                },
                "category": {
                    "type": "string",
                    "description": "One of: tool, bug, other (default 'other')"
                }
            },
            "required": [
                "subject"
            ]
        }
    },
    "tickets_mine": {
        "name": "tickets_mine",
        "description": "List tickets currently assigned to you (the calling agent). Use this to\npick up work the admin has routed your way. Returns only open tickets\nwhere the latest assign event names your user id.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "tickets_get": {
        "name": "tickets_get",
        "description": "Read a ticket by id, including its event timeline (comments, assignments,\nclose/reopen). Accessible to admin, the reporter, or the current assignee.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "number"
                }
            },
            "required": [
                "id"
            ]
        }
    },
    "tickets_update": {
        "name": "tickets_update",
        "description": "Edit an existing ticket's subject, body, or category. Admin, the reporter,\nand the current assignee may update. Use this when a ticket needs new\nfindings added or its subject sharpened — preserves the event timeline\ninstead of closing and re-filing.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "number"
                },
                "subject": {
                    "type": "string",
                    "description": "New subject line"
                },
                "body": {
                    "type": "string",
                    "description": "New body (markdown OK)"
                },
                "category": {
                    "type": "string",
                    "description": "One of: tool, bug, other"
                }
            },
            "required": [
                "id"
            ]
        }
    },
    "tickets_comment": {
        "name": "tickets_comment",
        "description": "Add a comment to a ticket. The admin, the reporter, and the current\nassignee may comment. Use this to provide updates, ask questions, or\nrecord resolution notes.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "number"
                },
                "body": {
                    "type": "string",
                    "description": "Comment body"
                }
            },
            "required": [
                "id",
                "body"
            ]
        }
    },
    "tickets_list": {
        "name": "tickets_list",
        "description": "List all tickets (admin only). Filter by status. Returns each ticket's\nlatest assignee + reporter username for context.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "One of: open (default), closed, all"
                }
            },
            "required": []
        }
    },
    "tickets_assign": {
        "name": "tickets_assign",
        "description": "Assign a ticket to an agent (admin only). Pass either `agent` (username)\nor `assigneeId` (numeric user id). The agent will see this ticket in\ntickets_mine. Optional `note` is recorded in the timeline.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "number"
                },
                "agent": {
                    "type": "string",
                    "description": "Agent username (preferred)"
                },
                "assigneeId": {
                    "type": "number",
                    "description": "Numeric user id (alternative)"
                },
                "note": {
                    "type": "string"
                }
            },
            "required": [
                "id"
            ]
        }
    },
    "tickets_close": {
        "name": "tickets_close",
        "description": "Close an open ticket (admin only). Records optional note in the timeline.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "number"
                },
                "note": {
                    "type": "string"
                }
            },
            "required": [
                "id"
            ]
        }
    },
    "tickets_reopen": {
        "name": "tickets_reopen",
        "description": "Reopen a closed ticket (admin only).",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "number"
                },
                "note": {
                    "type": "string"
                }
            },
            "required": [
                "id"
            ]
        }
    }
}


def get(name: str) -> dict:
    return SCHEMAS[name]
