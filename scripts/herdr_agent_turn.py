#!/usr/bin/env python3
"""Compatibility entry point for the scoped Herdr orchestration CLI."""

from __future__ import annotations

import json
import sys

from herdr_orchestrate import main as orchestrate_main


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in {"doctor", "team", "run", "conversation", "quota", "assignment"}:
        return orchestrate_main()
    print(json.dumps({
        "schema_version": 1,
        "outcome": "migration_required",
        "retry_safe": False,
        "message": "Legacy --agent/--prompt cannot bind run, pane, native conversation or return channel. Use run init, then assignment dispatch with --config, --expected-generation, --owner-epoch and --state-dir. A distinct context first needs conversation reset.",
    }))
    return 20


if __name__ == "__main__":
    raise SystemExit(main())
