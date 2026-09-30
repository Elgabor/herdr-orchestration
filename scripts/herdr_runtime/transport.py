"""Bounded Herdr CLI transport; only explicit provisioning mutations are exposed."""

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

    def _execute(self, *args: str, timeout: int | None = 15) -> dict:
        try:
            process = subprocess.run(
                [self.binary, *args], capture_output=True, text=True,
                encoding="utf-8", errors="replace", check=False, timeout=timeout,
            )
        except subprocess.TimeoutExpired as error:
            raise HerdrError("Herdr command timed out; delivery state uncertain") from error
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

    def call(self, *args: str) -> dict:
        if args not in {("status", "--json"), ("pane", "current", "--current"), ("api", "snapshot")}:
            raise HerdrError("operation not in read-only transport allowlist")
        return self._execute(*args)

    def status(self) -> dict:
        return self.call("status", "--json")

    def current_pane(self) -> dict:
        return self.call("pane", "current", "--current")["result"]["pane"]

    def snapshot(self) -> dict:
        return self.call("api", "snapshot")["result"]["snapshot"]

    def pane_get(self, pane_id: str) -> dict:
        try:
            return self._execute("pane", "get", pane_id)["result"]["pane"]
        except (KeyError, TypeError) as error:
            raise HerdrError("Herdr pane response malformed") from error

    def process_info(self, pane_id: str) -> dict:
        try:
            return self._execute("pane", "process-info", "--pane", pane_id)["result"]["process_info"]
        except (KeyError, TypeError) as error:
            raise HerdrError("Herdr process response malformed") from error

    def split(self, parent_id: str, direction: str, ratio: float, cwd: str) -> dict:
        try:
            return self._execute("pane", "split", parent_id, "--direction", direction,
                                 "--ratio", str(ratio), "--cwd", cwd, "--no-focus")["result"]["pane"]
        except (KeyError, TypeError) as error:
            raise HerdrError("Herdr split response malformed; delivery state uncertain") from error

    def start_agent(self, name: str, kind: str, pane_id: str, argv: list[str]) -> dict:
        try:
            return self._execute("agent", "start", name, "--kind", kind,
                                 "--pane", pane_id, "--timeout", "30000", "--", *argv,
                                 timeout=45)["result"]["agent"]
        except (KeyError, TypeError) as error:
            raise HerdrError("Herdr start response malformed; delivery state uncertain") from error

    def agent_get(self, pane_id: str) -> dict:
        try:
            return self._execute("agent", "get", pane_id)["result"]["agent"]
        except (KeyError, TypeError) as error:
            raise HerdrError("Herdr agent response malformed") from error

    def agent_prompt(self, pane_id: str, prompt: str) -> dict:
        try:
            return self._execute("agent", "prompt", pane_id, prompt)["result"]["agent"]
        except (KeyError, TypeError) as error:
            raise HerdrError("Herdr prompt response malformed; delivery state uncertain") from error

    def agent_prompt_wait(self, pane_id: str, prompt: str) -> dict:
        try:
            return self._execute("agent", "prompt", pane_id, prompt, "--wait", timeout=None)["result"]["agent"]
        except (KeyError, TypeError) as error:
            raise HerdrError("Herdr waited prompt response malformed; delivery state uncertain") from error
