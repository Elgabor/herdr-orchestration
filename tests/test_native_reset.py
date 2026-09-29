import copy
import json
import os
from pathlib import Path
from unittest.mock import patch
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from herdr_runtime.context import adopt_existing, inspect_team  # noqa: E402
from herdr_runtime.native_reset import ResetError, new_conversation  # noqa: E402
from herdr_runtime.state import StateStore  # noqa: E402


class ResetClient:
    def __init__(self, proof_dir, cwd):
        self.data = json.loads((ROOT / "tests" / "fixtures" / "context.json").read_text())
        self.data["snapshot"]["agents"] = self.data["snapshot"]["agents"][:2]
        self.data["snapshot"]["panes"] = self.data["snapshot"]["panes"][:2]
        self.data["snapshot"]["agents"][1].update(cwd=str(cwd), interactive_ready=True)
        self.data["snapshot"]["panes"][1]["cwd"] = str(cwd)
        self.proof_dir = proof_dir
        self.cwd = str(cwd)
        self.sent = []
        self.change_model = False

    def status(self):
        return self.data["status"]

    def current_pane(self):
        return self.data["current"]

    def snapshot(self):
        return copy.deepcopy(self.data["snapshot"])

    def agent_get(self, pane_id):
        return copy.deepcopy(self.data["snapshot"]["agents"][1])

    def native(self):
        agent = self.data["snapshot"]["agents"][1]
        return {"cwd": self.cwd, "model": {"provider": "openai-codex",
                "id": "changed" if self.change_model else "gpt-6-luna"},
                "thinking": "low", "trusted": True, "tools": ["bash", "read"],
                "session_id": "native-id", "session_file": agent["agent_session"]["value"]}

    def agent_prompt(self, pane_id, prompt):
        self.sent.append(prompt)
        command, nonce = prompt.split()
        if command == "/herdrinspect":
            proof = {"operation": "inspect", "current": self.native()}
        elif command == "/herdrnew":
            before = self.native()
            agent = self.data["snapshot"]["agents"][1]
            agent["agent_session"]["value"] = "/test/fresh.jsonl"
            after = self.native()
            after["tools"] = None
            proof = {"operation": "new", "before": before, "after": after,
                     "cancelled": False, "error": None}
        else:
            raise AssertionError(prompt)
        (self.proof_dir / f"{nonce}.json").write_text(json.dumps({"nonce": nonce, **proof}))
        os.chmod(self.proof_dir / f"{nonce}.json", 0o600)
        return copy.deepcopy(self.data["snapshot"]["agents"][1])


class NativeResetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bridge = self.root / "bridge"
        self.bridge.mkdir(mode=0o700)
        self.store = StateStore(self.root / "state")
        self.client = ResetClient(self.bridge, self.root)
        self.env = patch.dict(os.environ, {"HERDR_ENV": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        _, private = inspect_team(self.client)
        config = json.loads((ROOT / "templates" / "adopt.example.json").read_text())
        adopt_existing(config, private, self.store)

    def reset(self):
        run = self.store.load_run("example-run")
        return new_conversation(self.client, self.store, "example-run", "worker-1",
                                run["generation"], 1, "new-task", self.bridge)

    def test_native_reset_changes_session_not_pane_or_config(self):
        run = self.reset()
        self.assertEqual(run["members"][0]["conversation_id"], "/test/fresh.jsonl")
        self.assertEqual(run["members"][0]["pane_id"], "w1:p2")
        self.assertEqual(run["members"][0]["context_key"], "new-task")
        self.assertTrue(run["team_frozen"])
        self.assertEqual([value.split()[0] for value in self.client.sent],
                         ["/herdrinspect", "/herdrnew", "/herdrinspect"])
        self.assertEqual(run["resets"]["worker-1"]["state"], "complete")

    def test_active_assignment_blocks_before_any_input(self):
        run = self.store.load_run("example-run")
        assignment = json.loads((ROOT / "templates" / "assignment.example.json").read_text())
        assignment.update(run_id="example-run", member_id="worker-1", state="active")
        run["assignments"][assignment["assignment_id"]] = assignment
        run["generation"] = 1
        self.store.update_run(run, expected_generation=0, owner_epoch=1)
        with self.assertRaisesRegex(ResetError, "not released"):
            self.reset()
        self.assertEqual(self.client.sent, [])

    def test_model_drift_blocks_and_no_second_reset(self):
        original = self.client.agent_prompt

        def drift(pane_id, prompt):
            if prompt.startswith("/herdrnew"):
                result = original(pane_id, prompt)
                self.client.change_model = True
                return result
            return original(pane_id, prompt)

        self.client.agent_prompt = drift
        with self.assertRaisesRegex(ResetError, "native model changed"):
            self.reset()
        self.assertEqual(self.store.load_run("example-run")["resets"]["worker-1"]["state"], "needs_reconcile")
        count = len(self.client.sent)
        with self.assertRaisesRegex(ResetError, "previous reset intent unresolved"):
            self.reset()
        self.assertEqual(len(self.client.sent), count)

    def test_busy_worker_blocks_before_any_input(self):
        self.client.data["snapshot"]["agents"][1]["agent_status"] = "working"
        with self.assertRaisesRegex(ResetError, "worker is active"):
            self.reset()
        self.assertEqual(self.client.sent, [])


if __name__ == "__main__":
    unittest.main()
