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

from herdr_runtime.assignment import AssignmentError, dispatch, publish_result  # noqa: E402
from herdr_runtime.context import adopt_existing, inspect_team  # noqa: E402
from herdr_runtime.control import apply_control  # noqa: E402
from herdr_runtime.recovery import confirm_resume, inspect_resume  # noqa: E402
from herdr_runtime.state import StateStore  # noqa: E402


class Client:
    def __init__(self):
        self.data = json.loads((ROOT / "tests" / "fixtures" / "context.json").read_text())
        self.data["snapshot"]["agents"] = self.data["snapshot"]["agents"][:2]
        self.data["snapshot"]["panes"] = self.data["snapshot"]["panes"][:2]
        self.data["snapshot"]["agents"][0]["agent_status"] = "done"
        self.data["snapshot"]["agents"][1]["interactive_ready"] = True
        self.prompts = []

    def status(self):
        return self.data["status"]

    def current_pane(self):
        return self.data["current"]

    def snapshot(self):
        return copy.deepcopy(self.data["snapshot"])

    def agent_prompt(self, pane, packet):
        self.prompts.append((pane, packet))
        return {"agent_status": "working"}


class Channel:
    def __init__(self):
        self.sends = []

    def supports(self, owner, member):
        return True

    def arm(self, run, assignment, member):
        return "armed"

    def send(self, pane, packet, handle):
        self.sends.append((pane, packet))
        return None


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = StateStore(self.root / "state")
        self.client = Client()
        self.channel = Channel()
        self.env = patch.dict(os.environ, {"HERDR_ENV": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        _, private = inspect_team(self.client)
        run = adopt_existing(json.loads((ROOT / "templates" / "adopt.example.json").read_text()), private, self.store)
        run["members"][0]["context_key"] = "example-work"
        run["generation"] = 1
        self.store.update_run(run, expected_generation=0, owner_epoch=1)
        assignment = json.loads((ROOT / "templates" / "assignment.example.json").read_text())
        assignment["conversation_id"] = "/test/worker.jsonl"
        self.dispatch_config = {"assignment": assignment, "instructions": ["Initial task"],
                                "acceptance": ["Structured result"], "entry_points": [], "write_scope": [],
                                "result_root": str(self.root), "result_path": "result.json"}

    def control(self, config):
        run = self.store.load_run("example-run")
        return apply_control(self.client, self.store, {"run_id": "example-run", **config},
                             run["generation"], 1)

    def dispatch(self):
        run = self.store.load_run("example-run")
        return dispatch(self.client, self.store, self.dispatch_config, run["generation"], 1, self.channel)

    def test_future_instruction_applies_once_to_next_packet_without_worker_prompt(self):
        self.control({"type": "future_instruction", "instruction_id": "f1", "instruction": "Use Italian"})
        self.assertEqual(self.client.prompts, [])
        run = self.dispatch()
        self.assertEqual(len(self.channel.sends), 1)
        self.assertIn("Use Italian", self.channel.sends[0][1])
        self.assertEqual(run["future_instructions"], [])
        self.assertEqual(run["assignments"]["example-assignment"]["future_instruction_ids"], ["f1"])

    def test_pause_blocks_new_dispatch_without_cancelling_active_work(self):
        run = self.control({"type": "pause_dispatch", "paused": True})
        self.assertTrue(run["pause_dispatch"])
        with self.assertRaisesRegex(AssignmentError, "paused"):
            self.dispatch()
        self.assertEqual(self.channel.sends, [])
        self.control({"type": "pause_dispatch", "paused": False})
        self.assertEqual(len(self.dispatch()["assignments"]), 1)

    def test_amendment_is_queued_in_same_pane_and_old_result_cannot_close_it(self):
        self.dispatch()
        self.client.data["snapshot"]["agents"][1]["agent_status"] = "working"
        run = self.control({"type": "amend_assignment", "assignment_id": "example-assignment",
                            "expected_revision": 0, "amendment_id": "a1", "instruction": "Add the new finding"})
        task = run["assignments"]["example-assignment"]
        self.assertEqual(task["revision"], 1)
        self.assertEqual(task["amendments"][0]["delivery"], "queued")
        self.assertFalse(task["amendments"][0]["worker_ack"])
        self.assertEqual([pane for pane, _ in self.client.prompts], ["w1:p2"])
        with self.assertRaisesRegex(AssignmentError, "revision"):
            self.control({"type": "amend_assignment", "assignment_id": "example-assignment",
                          "expected_revision": 0, "amendment_id": "a2", "instruction": "Duplicate"})
        result = json.loads((ROOT / "templates" / "result.example.json").read_text())
        result["conversation_id"] = "/test/worker.jsonl"
        (self.root / "result.json").write_text(json.dumps(result))
        self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][1])
        with self.assertRaisesRegex(AssignmentError, "revision"):
            publish_result(self.client, self.store, "example-run", "example-assignment", self.root, "result.json")
        result["revision"] = 1
        (self.root / "result.json").write_text(json.dumps(result))
        with self.assertRaisesRegex(AssignmentError, "acknowledged_amendments"):
            publish_result(self.client, self.store, "example-run", "example-assignment", self.root, "result.json")
        result["acknowledged_amendments"] = ["a1"]
        (self.root / "result.json").write_text(json.dumps(result))
        published, _ = publish_result(self.client, self.store, "example-run", "example-assignment", self.root, "result.json")
        self.assertTrue(published["assignments"]["example-assignment"]["amendments"][0]["worker_ack"])

    def test_uncertified_cancel_and_goal_do_not_mutate_run(self):
        before = self.store.load_run("example-run")
        for operation in ({"type": "cancel_assignment", "assignment_id": "example-assignment"},
                          {"type": "change_goal"}):
            with self.assertRaisesRegex(AssignmentError, "not certified"):
                self.control(operation)
        self.assertEqual(self.store.load_run("example-run"), before)
        self.assertEqual(self.client.prompts, [])

    def test_resume_requires_explicit_confirmation_and_does_not_prompt(self):
        observed = inspect_resume(self.client, self.store, "example-run", 1, 1)
        self.assertTrue(observed["awaiting_user_resume"])
        self.assertLessEqual(len(observed["summary"].split()), 80)
        with self.assertRaisesRegex(AssignmentError, "owner confirmation"):
            self.dispatch()
        run = confirm_resume(self.client, self.store, "example-run", observed["generation"], 1)
        self.assertFalse(run["awaiting_user_resume"])
        self.assertEqual(self.channel.sends, [])
        self.assertEqual(self.client.prompts, [])

    def test_resume_collects_result_before_confirming(self):
        self.dispatch()
        self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][1])
        result = json.loads((ROOT / "templates" / "result.example.json").read_text())
        result["conversation_id"] = "/test/worker.jsonl"
        (self.root / "result.json").write_text(json.dumps(result))
        publish_result(self.client, self.store, "example-run", "example-assignment", self.root, "result.json")
        self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][0])
        generation = self.store.load_run("example-run")["generation"]
        observed = inspect_resume(self.client, self.store, "example-run", generation, 1)
        self.assertEqual(len(observed["pending_events"]), 1)
        with self.assertRaisesRegex(AssignmentError, "collect pending"):
            confirm_resume(self.client, self.store, "example-run", observed["generation"], 1)
        self.assertEqual(len(self.channel.sends), 1)

    def test_resume_active_worker_never_redispatches(self):
        self.dispatch()
        generation = self.store.load_run("example-run")["generation"]
        observed = inspect_resume(self.client, self.store, "example-run", generation, 1)
        self.assertEqual(observed["reattach"], "not_certified")
        with self.assertRaisesRegex(AssignmentError, "listener reattach"):
            confirm_resume(self.client, self.store, "example-run", observed["generation"], 1)
        self.assertEqual(len(self.channel.sends), 1)

    def test_resume_changed_worker_reports_missing_and_refuses_confirm(self):
        self.client.data["snapshot"]["agents"][1]["terminal_id"] = "reused-terminal"
        observed = inspect_resume(self.client, self.store, "example-run", 1, 1)
        self.assertEqual(observed["members"][0]["condition"], "missing_or_changed")
        with self.assertRaisesRegex(AssignmentError, "member binding changed"):
            confirm_resume(self.client, self.store, "example-run", observed["generation"], 1)
        self.assertEqual(self.client.prompts, [])


if __name__ == "__main__":
    unittest.main()
