"""Tool schemas — what the LLM sees for each recipes tool.

Generated from the legacy MCP YAML; do not edit by hand.
"""


SCHEMAS = {
    "recipes_list": {
        "name": "recipes_list",
        "description": "List recipes (id, slug, title, image). Optionally filter by a tag slug.",
        "parameters": {
            "type": "object",
            "properties": {
                "tag": {
                    "type": "string",
                    "description": "Tag or cuisine slug to filter by (e.g. \"balkan\", \"soup\"). Omit for all."
                },
                "limit": {
                    "type": "number",
                    "description": "Max recipes (default 500)"
                }
            },
            "required": []
        }
    },
    "recipes_get": {
        "name": "recipes_get",
        "description": "Full recipe by slug — fields, ingredients (with parsed qty/unit/name and the raw line), steps, tags.",
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Recipe slug (from recipes_list / recipes_search)"
                }
            },
            "required": [
                "slug"
            ]
        }
    },
    "recipes_search": {
        "name": "recipes_search",
        "description": "Full-text search over titles, ingredients AND steps. \"star anise\" finds recipes where it is only an ingredient.",
        "parameters": {
            "type": "object",
            "properties": {
                "q": {
                    "type": "string",
                    "description": "Search query"
                },
                "limit": {
                    "type": "number",
                    "description": "Max results (default 50)"
                }
            },
            "required": [
                "q"
            ]
        }
    },
    "recipes_by_ingredients": {
        "name": "recipes_by_ingredients",
        "description": "The fridge query — \"what can I make with what I have\". Returns recipes that contain EVERY listed ingredient term (AND match over ingredient text).",
        "parameters": {
            "type": "object",
            "properties": {
                "have": {
                    "type": "string",
                    "description": "Comma-separated ingredients you have, e.g. \"chicken,ginger,star anise\""
                },
                "limit": {
                    "type": "number",
                    "description": "Max results (default 50)"
                }
            },
            "required": [
                "have"
            ]
        }
    },
    "recipes_unparsed": {
        "name": "recipes_unparsed",
        "description": "Ingredients the importer could not fully structure (empty name, or a line that starts with a number but no quantity was captured). The starting point for tidying free-form ingredients into fields. Returns ingredient id + recipe slug/title + the raw line.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "number",
                    "description": "Max rows (default 200)"
                }
            },
            "required": []
        }
    },
    "recipes_raw": {
        "name": "recipes_raw",
        "description": "The original Paprika JSON payload for a recipe, exactly as imported (nothing lost on import lives here).",
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Recipe slug"
                }
            },
            "required": [
                "slug"
            ]
        }
    },
    "recipes_tags": {
        "name": "recipes_tags",
        "description": "All tags and cuisines with recipe counts (name, slug, isCuisine, count).",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "recipes_scale": {
        "name": "recipes_scale",
        "description": "A recipe's ingredients rewritten for N servings (read-only — nothing is saved). Returns original + scaled lines.",
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Recipe slug"
                },
                "servings": {
                    "type": "number",
                    "description": "Target servings"
                }
            },
            "required": [
                "slug",
                "servings"
            ]
        }
    },
    "recipes_create": {
        "name": "recipes_create",
        "description": "Create a new (empty) recipe with a title. Returns the new recipe incl. its slug.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Recipe title"
                }
            },
            "required": [
                "title"
            ]
        }
    },
    "recipes_field_set": {
        "name": "recipes_field_set",
        "description": "Set recipe-level fields (only those provided change). Free-text prepText / cookText / servingsText re-derive their parsed numbers automatically.",
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Recipe slug"
                },
                "title": {
                    "type": "string"
                },
                "notes": {
                    "type": "string"
                },
                "sourceName": {
                    "type": "string"
                },
                "sourceUrl": {
                    "type": "string"
                },
                "difficulty": {
                    "type": "string"
                },
                "rating": {
                    "type": "number"
                },
                "nutritionalInfo": {
                    "type": "string"
                },
                "prepText": {
                    "type": "string",
                    "description": "e.g. \"20 minutes\""
                },
                "cookText": {
                    "type": "string"
                },
                "servingsText": {
                    "type": "string",
                    "description": "e.g. \"Serves 4 to 6\""
                },
                "servingsBase": {
                    "type": "number",
                    "description": "Explicit scaler base, overrides the parse"
                }
            },
            "required": [
                "slug"
            ]
        }
    },
    "recipes_delete": {
        "name": "recipes_delete",
        "description": "Soft-delete a recipe (moves it to trash). Returns the row.",
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Recipe slug"
                }
            },
            "required": [
                "slug"
            ]
        }
    },
    "recipes_restore": {
        "name": "recipes_restore",
        "description": "Restore a soft-deleted recipe from trash.",
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Recipe slug"
                }
            },
            "required": [
                "slug"
            ]
        }
    },
    "recipes_upload_image": {
        "name": "recipes_upload_image",
        "description": "Download an image from a public URL and set it as the recipe's cover. Returns the updated recipe.",
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Recipe slug"
                },
                "imageUrl": {
                    "type": "string",
                    "description": "Public image URL (jpg/png/gif/webp/avif)"
                }
            },
            "required": [
                "slug",
                "imageUrl"
            ]
        }
    },
    "recipes_ingredient_add": {
        "name": "recipes_ingredient_add",
        "description": "Add an ingredient to a recipe from a raw line (\"2 tbsp olive oil, warmed\"); qty/unit/name/prep are parsed out. Returns the new ingredient.",
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Recipe slug"
                },
                "rawText": {
                    "type": "string",
                    "description": "The ingredient line as written"
                },
                "groupName": {
                    "type": "string",
                    "description": "Optional group, e.g. \"For the sauce\""
                }
            },
            "required": [
                "slug",
                "rawText"
            ]
        }
    },
    "recipes_ingredient_set": {
        "name": "recipes_ingredient_set",
        "description": "Update one ingredient by id. Editing rawText re-derives qty/unit/name/prep; passing an explicit field (qty/unit/name/preparation/groupName/sort) sets just that. rawText is never overwritten except by an explicit rawText edit.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "number",
                    "description": "Ingredient id (from recipes_get / recipes_unparsed)"
                },
                "rawText": {
                    "type": "string"
                },
                "qty": {
                    "type": "string"
                },
                "unit": {
                    "type": "string"
                },
                "name": {
                    "type": "string"
                },
                "preparation": {
                    "type": "string"
                },
                "groupName": {
                    "type": "string"
                },
                "sort": {
                    "type": "number"
                }
            },
            "required": [
                "id"
            ]
        }
    },
    "recipes_ingredient_delete": {
        "name": "recipes_ingredient_delete",
        "description": "Delete an ingredient by id.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "number",
                    "description": "Ingredient id"
                }
            },
            "required": [
                "id"
            ]
        }
    },
    "recipes_ingredients_set_group": {
        "name": "recipes_ingredients_set_group",
        "description": "Assign a group name to several ingredients at once (bucket them under \"For the sauce\" etc.). Returns the updated rows.",
        "parameters": {
            "type": "object",
            "properties": {
                "ids": {
                    "type": "array",
                    "description": "Ingredient ids"
                },
                "groupName": {
                    "type": "string",
                    "description": "Group name to assign (empty string clears it)"
                }
            },
            "required": [
                "ids",
                "groupName"
            ]
        }
    },
    "recipes_step_add": {
        "name": "recipes_step_add",
        "description": "Add a method step to a recipe. Returns the new step.",
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Recipe slug"
                },
                "body": {
                    "type": "string",
                    "description": "Step text"
                },
                "groupName": {
                    "type": "string",
                    "description": "Optional section, e.g. \"For the sauce\""
                }
            },
            "required": [
                "slug",
                "body"
            ]
        }
    },
    "recipes_step_set": {
        "name": "recipes_step_set",
        "description": "Update a step by id (body / groupName / sort).",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "number",
                    "description": "Step id"
                },
                "body": {
                    "type": "string"
                },
                "groupName": {
                    "type": "string"
                },
                "sort": {
                    "type": "number"
                }
            },
            "required": [
                "id"
            ]
        }
    },
    "recipes_step_delete": {
        "name": "recipes_step_delete",
        "description": "Delete a step by id.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "number",
                    "description": "Step id"
                }
            },
            "required": [
                "id"
            ]
        }
    },
    "recipes_steps_reorder": {
        "name": "recipes_steps_reorder",
        "description": "Reorder a recipe's steps. Pass step ids in the new order; sort is renumbered.",
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Recipe slug"
                },
                "orderedIds": {
                    "type": "array",
                    "description": "Step ids in the desired order"
                }
            },
            "required": [
                "slug",
                "orderedIds"
            ]
        }
    },
    "recipes_tag_add": {
        "name": "recipes_tag_add",
        "description": "Add a tag (or cuisine) to a recipe. Creates the tag if new. Returns the tag.",
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Recipe slug"
                },
                "name": {
                    "type": "string",
                    "description": "Tag name"
                },
                "isCuisine": {
                    "type": "boolean",
                    "description": "Mark this tag as a cuisine (default false)"
                }
            },
            "required": [
                "slug",
                "name"
            ]
        }
    },
    "recipes_tag_remove": {
        "name": "recipes_tag_remove",
        "description": "Remove a tag from a recipe (by tag id, from recipes_get).",
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Recipe slug"
                },
                "tagId": {
                    "type": "number",
                    "description": "Tag id"
                }
            },
            "required": [
                "slug",
                "tagId"
            ]
        }
    },
    "recipes_tag_rename": {
        "name": "recipes_tag_rename",
        "description": "Rename a tag (all recipes carrying it are affected). Identify it by slug.",
        "parameters": {
            "type": "object",
            "properties": {
                "tagSlug": {
                    "type": "string",
                    "description": "Slug of the tag to rename"
                },
                "name": {
                    "type": "string",
                    "description": "New display name"
                }
            },
            "required": [
                "tagSlug",
                "name"
            ]
        }
    },
    "recipes_tag_merge": {
        "name": "recipes_tag_merge",
        "description": "Merge one tag into another — every recipe tagged `source` becomes tagged `target`, then `source` is deleted. Fixes duplicates like \"Desert\" -> \"Dessert\".",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Slug of the tag to merge away"
                },
                "target": {
                    "type": "string",
                    "description": "Slug of the tag to keep"
                }
            },
            "required": [
                "source",
                "target"
            ]
        }
    },
    "recipes_tag_set_cuisine": {
        "name": "recipes_tag_set_cuisine",
        "description": "Flag (or unflag) a tag as a cuisine, controlling whether it appears as a cuisine folder/facet.",
        "parameters": {
            "type": "object",
            "properties": {
                "tagSlug": {
                    "type": "string",
                    "description": "Slug of the tag"
                },
                "isCuisine": {
                    "type": "boolean",
                    "description": "true = cuisine",
                    "false = ordinary tag": None
                }
            },
            "required": [
                "tagSlug",
                "isCuisine"
            ]
        }
    }
}


def get(name: str) -> dict:
    return SCHEMAS[name]
