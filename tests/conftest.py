import sys
from pathlib import Path

# The plugin dirs are not a package; add the repo root so `import notes` works.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
