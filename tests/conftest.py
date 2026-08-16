import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The plugin dirs are not a package; add the repo root so `import notes` works.
sys.path.insert(0, str(ROOT))


def _install(dir_name: str, module_name: str):
    """Import a plugin directory as a PACKAGE under an importable name.

    Two reasons this exists:

    * A hyphen cannot appear in a module name, so `app-bridge` (and the two
      bridges it replaced) can never be `import`ed by name. That accident is
      why the bridges had no tests for months — not a judgement that they were
      safe. See tests/test_app_bridge.py.
    * `submodule_search_locations` plus `__path__` make the directory a
      package, so a plugin split across several files can import its own
      siblings. This mirrors hermes' real loader, which passes exactly the same
      argument and sets exactly the same attribute (hermes_cli/plugins.py).
      hermes derives the module name from the manifest `name`, hyphens
      translated to underscores — the same name used here.
    """
    d = ROOT / dir_name
    spec = importlib.util.spec_from_file_location(
        module_name, d / "__init__.py", submodule_search_locations=[str(d)]
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__path__ = [str(d)]
    mod.__package__ = module_name
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


_install("app-bridge", "app_bridge")
_install("pica-search", "pica_search")
