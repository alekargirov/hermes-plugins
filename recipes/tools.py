"""Tool handlers — what runs when the LLM calls each recipes tool.

Every handler delegates to ``_http.execute`` with its spec. Generated from the
legacy MCP YAML; do not edit by hand.
"""
from __future__ import annotations

from ._http import execute


_SPECS = {
    "recipes_list": {
        "method": "GET",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/recipes?tag={arg.tag}&limit={arg.limit}",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_get": {
        "method": "GET",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/recipes/get?slug={arg.slug}",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_search": {
        "method": "GET",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/recipes/search?q={arg.q}&limit={arg.limit}",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_by_ingredients": {
        "method": "GET",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/recipes/by-ingredients?have={arg.have}&limit={arg.limit}",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_unparsed": {
        "method": "GET",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/recipes/unparsed?limit={arg.limit}",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_raw": {
        "method": "GET",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/recipes/raw?slug={arg.slug}",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_tags": {
        "method": "GET",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/tags",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_scale": {
        "method": "GET",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/recipes/scale?slug={arg.slug}&servings={arg.servings}",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_create": {
        "method": "POST",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/recipes/create",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_field_set": {
        "method": "POST",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/recipes/field-set",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_delete": {
        "method": "POST",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/recipes/delete",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_restore": {
        "method": "POST",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/recipes/restore",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_upload_image": {
        "method": "POST",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/recipes/upload-image",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_ingredient_add": {
        "method": "POST",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/ingredient/add",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_ingredient_set": {
        "method": "POST",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/ingredient/set",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_ingredient_delete": {
        "method": "POST",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/ingredient/delete",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_ingredients_set_group": {
        "method": "POST",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/ingredient/set-group",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_step_add": {
        "method": "POST",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/step/add",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_step_set": {
        "method": "POST",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/step/set",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_step_delete": {
        "method": "POST",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/step/delete",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_steps_reorder": {
        "method": "POST",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/step/reorder",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_tag_add": {
        "method": "POST",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/tag/add",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_tag_remove": {
        "method": "POST",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/tag/remove",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_tag_rename": {
        "method": "POST",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/tag/rename",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_tag_merge": {
        "method": "POST",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/tag/merge",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    },
    "recipes_tag_set_cuisine": {
        "method": "POST",
        "url": "{env.RECIPES_URL|http://recipes:3019}/api/v2/tag/set-cuisine",
        "headers": {
            "X-User-Id": "{env.USER_ID}"
        }
    }
}


def recipes_list(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_list"], args)


def recipes_get(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_get"], args)


def recipes_search(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_search"], args)


def recipes_by_ingredients(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_by_ingredients"], args)


def recipes_unparsed(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_unparsed"], args)


def recipes_raw(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_raw"], args)


def recipes_tags(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_tags"], args)


def recipes_scale(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_scale"], args)


def recipes_create(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_create"], args)


def recipes_field_set(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_field_set"], args)


def recipes_delete(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_delete"], args)


def recipes_restore(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_restore"], args)


def recipes_upload_image(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_upload_image"], args)


def recipes_ingredient_add(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_ingredient_add"], args)


def recipes_ingredient_set(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_ingredient_set"], args)


def recipes_ingredient_delete(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_ingredient_delete"], args)


def recipes_ingredients_set_group(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_ingredients_set_group"], args)


def recipes_step_add(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_step_add"], args)


def recipes_step_set(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_step_set"], args)


def recipes_step_delete(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_step_delete"], args)


def recipes_steps_reorder(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_steps_reorder"], args)


def recipes_tag_add(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_tag_add"], args)


def recipes_tag_remove(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_tag_remove"], args)


def recipes_tag_rename(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_tag_rename"], args)


def recipes_tag_merge(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_tag_merge"], args)


def recipes_tag_set_cuisine(args: dict, **kwargs) -> str:
    return execute(_SPECS["recipes_tag_set_cuisine"], args)



