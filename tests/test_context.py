import copy
import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from herdr_runtime.context import adopt_existing, inspect_team, verify_binding  # noqa: E402
from herdr_runtime.contracts import ContractError  # noqa: E402
from herdr_runtime.state import StateConflict, StateStore  # noqa: E402
from herdr_runtime.transport import HerdrError  # noqa: E402


def fixture():
    return json.loads((ROOT / "tests" / "fixtures" / "context.json").read_text())


class FakeClient:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def status(self):
        self.calls.append("status")
        return self.data["status"]

    def current_pane(self):
        self.calls.append("current")
        return self.data["current"]

    def snapshot(self):
        self.calls.append("snapshot")
        return self.data["snapshot"]


class ContextTests(unittest.TestCase):
    def test_no_herdr_env_calls_no_session_api(self):
        client = FakeClient(fixture())
        with self.assertRaisesRegex(HerdrError, "HERDR_ENV"):
            inspect_team(client, environ={})
        self.assertEqual(client.calls, [])

    def test_owner_tab_ignores_global_focus_and_other_agents(self):
        client = FakeClient(fixture())
        public, private = inspect_team(client, environ={"HERDR_ENV": "1"})
        self.assertEqual(client.calls, ["status", "current", "snapshot"])
        self.assertEqual(public["scope"]["tab_id"], "w1:t1")
        self.assertEqual([item["pane_id"] for item in public["candidates"]], ["w1:p2"])
        self.assertNotIn("/test/other.jsonl", json.dumps(public))
        self.assertNotIn("Worker 1", json.dumps(public))
        self.assertEqual(private["owner"]["pane_id"], "w1:p1")

    def test_adoption_requires_exact_pane_not_human_label(self):
        public, private = inspect_team(FakeClient(fixture()), environ={"HERDR_ENV": "1"})
        config = json.loads((ROOT / "templates" / "adopt.example.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "private")
            missing = copy.deepcopy(config)
            del missing["members"][0]["pane_id"]
            with self.assertRaisesRegex(ContractError, "pane_id"):
                adopt_existing(missing, private, store)
            run = adopt_existing(config, private, store)
            self.assertTrue(run["team_frozen"])
            self.assertEqual(run["members"][0]["label"], "Worker 1")
            self.assertEqual(run["members"][0]["agent_alias"], "worker-a")
            self.assertEqual(run["members"][0]["conversation_id"], "/test/worker.jsonl")
            self.assertEqual(run["owner"]["conversation_id"], "/test/owner.jsonl")
            self.assertEqual(store.load_run("example-run")["scope"], public["scope"])
            other = copy.deepcopy(config)
            other["run_id"] = "another-run"
            with self.assertRaises(StateConflict):
                adopt_existing(other, private, store)

    def test_changed_occupant_rejected(self):
        _, private = inspect_team(FakeClient(fixture()), environ={"HERDR_ENV": "1"})
        config = json.loads((ROOT / "templates" / "adopt.example.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            member = adopt_existing(config, private, StateStore(Path(directory) / "state"))["members"][0]
        agent = private["agents"][0]
        pane = private["panes"]["w1:p2"]
        verify_binding(member, agent, pane, private["scope"])
        for key, value in (("terminal_id", "term_replaced"), ("revision", 3), ("agent_session", {"value": "/test/other.jsonl"})):
            changed = copy.deepcopy(agent)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(HerdrError):
                verify_binding(member, changed, pane, private["scope"])

    def test_version_drift_blocks_inspection(self):
        data = fixture()
        data["status"]["server"]["protocol"] = 23
        with self.assertRaisesRegex(HerdrError, "version or protocol"):
            inspect_team(FakeClient(data), environ={"HERDR_ENV": "1"})

    def test_cli_team_inspect_fails_outside_herdr(self):
        env = dict(os.environ)
        env.pop("HERDR_ENV", None)
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / "herdr_orchestrate.py"), "team", "inspect"],
                           env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 20)
        self.assertEqual(json.loads(p.stdout)["outcome"], "capability_blocked")

    def test_legacy_dispatch_fails_closed(self):
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / "herdr_agent_turn.py"),
                            "--agent", "worker", "--prompt", "task"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 20)
        self.assertEqual(json.loads(p.stdout)["outcome"], "migration_required")


if __name__ == "__main__":
    unittest.main()
