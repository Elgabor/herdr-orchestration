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

from herdr_runtime.context import inspect_team  # noqa: E402
from herdr_runtime.provision import bootstrap_run, prepare_team, ProvisioningError  # noqa: E402
from herdr_runtime.state import StateStore  # noqa: E402
from herdr_runtime.transport import HerdrError  # noqa: E402


class ProvisionClient:
    def __init__(self):
        data = json.loads((ROOT / "tests" / "fixtures" / "context.json").read_text())
        data["snapshot"]["agents"] = [data["snapshot"]["agents"][0]]
        data["snapshot"]["panes"] = [data["snapshot"]["panes"][0]]
        data["snapshot"]["focused_pane_id"] = "w1:p1"
        data["snapshot"]["layouts"] = [{"tab_id": "w1:t1", "workspace_id": "w1",
                                         "zoomed": False, "panes": [{"pane_id": "w1:p1",
                                         "rect": {"width": 180, "height": 50}}]}]
        self.data = data
        self.splits = 0
        self.starts = 0
        self.fail_start = False
        self.lose_split_response = False
        self.focus_on_split = False

    def status(self):
        return self.data["status"]

    def current_pane(self):
        return self.data["current"]

    def snapshot(self):
        return copy.deepcopy(self.data["snapshot"])

    def pane_get(self, pane_id):
        return next(copy.deepcopy(pane) for pane in self.data["snapshot"]["panes"] if pane["pane_id"] == pane_id)

    def process_info(self, pane_id):
        return {"shell_pid": 100, "foreground_processes": [{"pid": 100}]}

    def split(self, parent_id, direction, ratio, cwd):
        self.splits += 1
        pane = {"pane_id": "w1:p4", "workspace_id": "w1", "tab_id": "w1:t1",
                "terminal_id": "term_new", "cwd": cwd}
        self.data["snapshot"]["panes"].append(pane)
        self.data["snapshot"]["layouts"][0]["panes"].append(
            {"pane_id": "w1:p4", "rect": {"width": 90, "height": 50}})
        if self.focus_on_split:
            self.data["snapshot"]["focused_pane_id"] = "w1:p4"
        if self.lose_split_response:
            raise HerdrError("response lost")
        return copy.deepcopy(pane)

    def start_agent(self, name, kind, pane_id, argv):
        self.starts += 1
        if self.fail_start:
            raise HerdrError("start failed")
        agent = {"agent": kind, "name": name, "agent_status": "idle",
                 "pane_id": pane_id, "workspace_id": "w1", "tab_id": "w1:t1",
                 "terminal_id": "term_new", "revision": 1,
                 "agent_session": {"kind": "path", "value": "/test/new.jsonl"}}
        self.data["snapshot"]["agents"].append(agent)
        self.data["snapshot"]["panes"][-1]["agent"] = kind
        return copy.deepcopy(agent)


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = StateStore(self.root / "state")
        self.client = ProvisionClient()
        self.env = patch.dict(os.environ, {"HERDR_ENV": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def config(self, source="split"):
        step = {"member_id": "worker", "label": "Worker", "agent_alias": "worker",
                "harness": "pi", "cwd": str(self.root), "source": source,
                "argv": ["--model", "openai-codex/gpt-6-luna"]}
        if source == "split":
            step.update(parent_pane_id="w1:p1", direction="right", ratio=0.5)
        else:
            step["pane_id"] = "w1:p4"
        return {"mode": "bootstrap_team", "run_id": "setup-test", "mission": "Test",
                "bootstrap_authorized": True, "parallel_authorized": False,
                "execution_mode": "sequential", "setup_plan": [step]}

    def test_bootstrap_template_valid_after_explicit_binding(self):
        config = json.loads((ROOT / "templates" / "bootstrap.example.json").read_text())
        config["setup_plan"][0]["cwd"] = str(self.root)
        config["setup_plan"][0]["parent_pane_id"] = "w1:p1"
        _, private = inspect_team(self.client)
        run = bootstrap_run(config, private, self.store)
        self.assertEqual(run["setup_plan"][0]["agent_alias"], "worker-1")

    def init(self, config=None):
        _, private = inspect_team(self.client)
        return bootstrap_run(config or self.config(), private, self.store)

    def prepare(self):
        run = self.store.load_run("setup-test")
        return prepare_team(self.client, self.store, run["run_id"], run["generation"], run["owner_epoch"])

    def test_persist_plan_before_split_then_freeze_in_same_tab(self):
        self.init()
        self.assertEqual(self.client.splits, 0)
        self.assertEqual(self.store.load_run("setup-test")["setup_journal"][0]["state"], "planned")
        run = self.prepare()
        self.assertTrue(run["team_frozen"])
        self.assertEqual((self.client.splits, self.client.starts), (1, 1))
        self.assertEqual(run["members"][0]["pane_id"], "w1:p4")
        self.assertEqual(run["created_resources"], [{"type": "pane", "pane_id": "w1:p4"}])
        self.assertEqual(self.client.snapshot()["focused_pane_id"], "w1:p1")
        with self.assertRaisesRegex(ProvisioningError, "not authorized"):
            self.prepare()

    def test_existing_agent_refuses_bootstrap(self):
        self.client.data["snapshot"]["agents"].append({"pane_id": "w1:p4", "workspace_id": "w1", "tab_id": "w1:t1"})
        with self.assertRaisesRegex(ProvisioningError, "already exists"):
            self.init()
        self.assertEqual(self.client.splits, 0)

    def test_small_or_zoomed_layout_blocks_without_split(self):
        self.init()
        self.client.data["snapshot"]["layouts"][0]["panes"][0]["rect"]["width"] = 100
        with self.assertRaisesRegex(ProvisioningError, "insufficient width"):
            self.prepare()
        self.assertEqual(self.client.splits, 0)
        self.client.data["snapshot"]["layouts"][0]["zoomed"] = True
        with self.assertRaisesRegex(ProvisioningError, "zoomed"):
            self.prepare()
        self.assertEqual(self.client.splits, 0)

    def test_failed_start_retains_pane_and_retry_does_not_split(self):
        self.init()
        self.client.fail_start = True
        with self.assertRaisesRegex(ProvisioningError, "pane retained"):
            self.prepare()
        self.assertEqual(self.store.load_run("setup-test")["setup_journal"][0]["state"], "pane_created")
        self.assertEqual((self.client.splits, self.client.starts), (1, 1))
        self.client.fail_start = False
        self.assertTrue(self.prepare()["team_frozen"])
        self.assertEqual((self.client.splits, self.client.starts), (1, 2))

    def test_lost_split_response_reconciles_without_second_split(self):
        self.init()
        self.client.lose_split_response = True
        run = self.prepare()
        self.assertTrue(run["team_frozen"])
        self.assertEqual(self.client.splits, 1)

    def test_ambiguous_split_response_never_reissues_split(self):
        self.init()
        self.client.lose_split_response = True
        original = self.client.split

        def ambiguous(*args):
            self.client.lose_split_response = False
            original(*args)
            self.client.data["snapshot"]["panes"].append(
                {"pane_id": "w1:p5", "workspace_id": "w1", "tab_id": "w1:t1",
                 "terminal_id": "term_extra", "cwd": str(self.root)})
            raise HerdrError("response lost")

        self.client.split = ambiguous
        with self.assertRaisesRegex(ProvisioningError, "identity needs explicit reconciliation"):
            self.prepare()
        self.assertEqual(self.client.splits, 1)
        with self.assertRaisesRegex(ProvisioningError, "identity needs explicit reconciliation"):
            self.prepare()
        self.assertEqual(self.client.splits, 1)

    def test_focus_change_stops_after_recording_created_pane(self):
        self.init()
        self.client.focus_on_split = True
        with self.assertRaisesRegex(ProvisioningError, "focus changed"):
            self.prepare()
        self.assertEqual(self.client.splits, 1)
        self.assertEqual(self.client.starts, 0)
        self.assertEqual(self.store.load_run("setup-test")["setup_journal"][0]["pane_id"], "w1:p4")

    def test_existing_shell_claimed_without_split(self):
        pane = {"pane_id": "w1:p4", "workspace_id": "w1", "tab_id": "w1:t1",
                "terminal_id": "term_new", "cwd": str(self.root)}
        self.client.data["snapshot"]["panes"].append(pane)
        self.init(self.config("existing_shell"))
        run = self.prepare()
        self.assertEqual(self.client.splits, 0)
        self.assertFalse(run["members"][0]["created_by_run"])
        self.assertEqual(run["created_resources"], [])


if __name__ == "__main__":
    unittest.main()
