import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from herdr_runtime.return_channel import PiReturnChannel  # noqa: E402


class FakeClient:
    def __init__(self):
        self.calls = []

    def agent_prompt_wait(self, pane, packet):
        self.calls.append((pane, packet))
        return {"agent_status": "done"}


class ReturnChannelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        os.chmod(self.root, 0o700)
        self.nonce = "a" * 32
        self.run = {"run_id": "run-1", "owner_epoch": 2, "generation": 7,
                    "owner": {"harness": "pi", "pane_id": "w1:p1", "conversation_id": "/test/owner.jsonl"}}
        self.assignment = {"assignment_id": "task-1"}
        self.member = {"harness": "pi"}
        self.client = FakeClient()
        self.proof = {"nonce": self.nonce, "operation": "owner_arm", "run_id": "run-1",
                      "assignment_id": "task-1", "owner_session_file": "/test/owner.jsonl",
                      "owner_pane_id": "w1:p1", "owner_epoch": 2, "generation": 7,
                      "owner_process_pid": os.getpid()}

    def write_proof(self):
        path = self.root / f"{self.nonce}.json"
        path.write_text(json.dumps(self.proof))
        os.chmod(path, 0o600)
        return path

    def test_exact_private_arm_then_one_waited_send(self):
        self.write_proof()
        channel = PiReturnChannel(self.client, self.root, self.nonce)
        self.assertTrue(channel.supports(self.run["owner"], self.member))
        handle = channel.arm(self.run, self.assignment, self.member)
        self.assertEqual(handle["owner_process_pid"], os.getpid())
        self.assertEqual(channel.send("w1:p2", "bounded packet", handle)["agent_status"], "done")
        self.assertEqual(self.client.calls, [("w1:p2", "bounded packet")])

    def test_wrong_epoch_or_expired_arm_never_sends(self):
        path = self.write_proof()
        channel = PiReturnChannel(self.client, self.root, self.nonce)
        self.assertTrue(channel.supports(self.run["owner"], self.member))
        self.proof["owner_epoch"] = 3
        self.write_proof()
        channel.supports(self.run["owner"], self.member)
        with self.assertRaisesRegex(ValueError, "differs"):
            channel.arm(self.run, self.assignment, self.member)
        self.proof["owner_epoch"] = 2
        self.write_proof()
        os.utime(path, (time.time() - 60, time.time() - 60))
        channel.supports(self.run["owner"], self.member)
        with self.assertRaisesRegex(ValueError, "expired"):
            channel.arm(self.run, self.assignment, self.member)
        self.assertEqual(self.client.calls, [])

    def test_nonprivate_or_non_pi_bridge_is_unsupported(self):
        self.write_proof()
        os.chmod(self.root, 0o755)
        channel = PiReturnChannel(self.client, self.root, self.nonce)
        self.assertFalse(channel.supports(self.run["owner"], self.member))
        os.chmod(self.root, 0o700)
        self.member["harness"] = "codex"
        self.assertFalse(channel.supports(self.run["owner"], self.member))
        self.assertEqual(self.client.calls, [])


if __name__ == "__main__":
    unittest.main()
