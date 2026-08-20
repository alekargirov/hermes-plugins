#!/usr/bin/env python3
"""Silent entry point for ``hermes cron --script ... --no-agent``.

The cron runner invokes scripts as ``python3 <path>`` with no arguments, so
``--quiet`` cannot be passed on a job's command line. This wrapper exists so
the no-LLM watchdog pattern works: it prints nothing unless an alert fires,
and with ``--no-agent`` empty stdout means no message is delivered.

Keep it next to check_alerts.py — it imports it from the same directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_alerts  # noqa: E402

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--quiet"]
    raise SystemExit(check_alerts.main())
