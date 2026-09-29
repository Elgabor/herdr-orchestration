"""Read-only Herdr CLI transport; mutating commands are not exposed here."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess


class HerdrError(RuntimeError):
    pass


class HerdrClient:
    def __init__(self, binary: str | None = None):
        candidate = binary or os.environ.get("HERDR_BIN_PATH") or shutil.which("herdr")
        if not candidate:
            raise HerdrError("herdr executable unavailable")
        path = Path(candidate).expanduser().resolve()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise HerdrError("resolved herdr path is not executable")
        self.binary = str(path)

    def call(self, *args: str) -> dict:
        if args not in {("status", "--json"), ("pane", "current", "--current"), ("api", "snapshot")}:
            raise HerdrError("operation not in read-only transport allowlist")
        process = subprocess.run(
            [self.binary, *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False, timeout=15,
        )
        if process.returncode:
            try:
                error = json.loads(process.stderr).get("error", {})
                detail = f"{error.get('code', 'error')}: {error.get('message', '')}"
            except json.JSONDecodeError:
                detail = "Herdr command failed without a structured error"
            raise HerdrError(detail[:400])
        try:
            response = json.loads(process.stdout)
        except json.JSONDecodeError as error:
            raise HerdrError("Herdr returned invalid JSON") from error
        if not isinstance(response, dict):
            raise HerdrError("Herdr returned a non-object")
        return response

    def status(self) -> dict:
        return self.call("status", "--json")

    def current_pane(self) -> dict:
        return self.call("pane", "current", "--current")["result"]["pane"]

    def snapshot(self) -> dict:
        return self.call("api", "snapshot")["result"]["snapshot"]
