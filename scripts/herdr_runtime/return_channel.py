"""Pi owner bridge binding for a single Herdr prompt-and-wait child."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import time

from .native_reset import _proof
from .transport import HerdrClient


class PiReturnChannel:
    def __init__(self, client: HerdrClient, bridge_dir: Path, nonce: str):
        self.client = client
        self.bridge_dir = Path(bridge_dir)
        self.nonce = nonce
        self.arm_proof: dict | None = None

    def supports(self, owner: dict, member: dict) -> bool:
        if owner["harness"] != "pi" or member["harness"] != "pi":
            return False
        if self.bridge_dir.is_symlink():
            return False
        try:
            info = self.bridge_dir.stat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                return False
            self.arm_proof = _proof(self.bridge_dir, self.nonce, "owner_arm", timeout=0)
        except (OSError, ValueError, RuntimeError):
            return False
        return True

    def arm(self, run: dict, assignment: dict, member: dict) -> dict:
        proof = self.arm_proof
        if not isinstance(proof, dict):
            raise ValueError("owner arm proof missing")
        expected = {
            "run_id": run["run_id"], "assignment_id": assignment["assignment_id"],
            "owner_session_file": run["owner"]["conversation_id"],
            "owner_pane_id": run["owner"]["pane_id"],
            "owner_epoch": run["owner_epoch"], "generation": run["generation"],
        }
        if any(proof.get(key) != value for key, value in expected.items()):
            raise ValueError("owner arm proof differs from run binding")
        pid = proof.get("owner_process_pid")
        if not isinstance(pid, int) or pid <= 0:
            raise ValueError("owner bridge process identity missing")
        try:
            os.kill(pid, 0)
        except OSError as error:
            raise ValueError("owner bridge process no longer running") from error
        stamp = (self.bridge_dir / f"{self.nonce}.json").stat().st_mtime
        if not 0 <= time.time() - stamp <= 30:
            raise ValueError("owner arm proof expired")
        return {"kind": "pi_extension", "nonce": self.nonce,
                "owner_session_file": expected["owner_session_file"],
                "owner_process_pid": pid,
                "listener_pid": os.getpid(), "listener_started_at_ns": time.time_ns(),
                "listener_version": 1}

    def send(self, pane_id: str, packet: str, handle: dict) -> dict:
        return self.client.agent_prompt_wait(pane_id, packet)

    def wait_existing(self, pane_id: str, handle: dict) -> dict:
        return self.client.agent_wait(pane_id)
