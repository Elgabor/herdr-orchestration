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

from herdr_runtime.assignment import (AssignmentError, collect_event, dispatch,
                                      pending_events, publish_result,
                                      validate_dispatch_config)  # noqa: E402
from herdr_runtime.context import adopt_existing, inspect_team  # noqa: E402
from herdr_runtime.state import StateStore  # noqa: E402


class Client:
    def __init__(self):
        self.data = json.loads((ROOT / "tests" / "fixtures" / "context.json").read_text())
        self.data["snapshot"]["agents"] = self.data["snapshot"]["agents"][:2]
        self.data["snapshot"]["panes"] = self.data["snapshot"]["panes"][:2]
        self.data["snapshot"]["agents"][1]["interactive_ready"] = True

    def status(self):
        return self.data["status"]

    def current_pane(self):
        return self.data["current"]

    def snapshot(self):
        return copy.deepcopy(self.data["snapshot"])


class Channel:
    def __init__(self, store):
        self.store = store
        self.sends = []
        self.fail = False
        self.completion = None

    def supports(self, owner, member):
        return owner["harness"] == member["harness"] == "pi"

    def arm(self, run, assignment, member):
        return "test-return-handle"

    def send(self, pane_id, packet, handle):
        saved = self.store.load_run("example-run")["assignments"]["example-assignment"]
        assert saved["state"] == "dispatching"
        self.sends.append((pane_id, packet, handle))
        if self.fail:
            raise RuntimeError("transport response lost")
        return self.completion


class AssignmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = StateStore(self.root / "state")
        self.client = Client()
        self.env = patch.dict(os.environ, {"HERDR_ENV": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        _, private = inspect_team(self.client)
        config = json.loads((ROOT / "templates" / "adopt.example.json").read_text())
        run = adopt_existing(config, private, self.store)
        run["members"][0]["context_key"] = "example-work"
        run["generation"] = 1
        self.store.update_run(run, expected_generation=0, owner_epoch=1)
        assignment = json.loads((ROOT / "templates" / "assignment.example.json").read_text())
        assignment["conversation_id"] = "/test/worker.jsonl"
        self.config = {"assignment": assignment, "instructions": ["Inspect the assigned files"],
                       "acceptance": ["Report exact findings"], "entry_points": [],
                       "write_scope": [], "result_root": str(self.root),
                       "result_path": "result.json", "continuation_of": None}
        self.channel = Channel(self.store)

    def send(self, channel=None):
        run = self.store.load_run("example-run")
        return dispatch(self.client, self.store, self.config, run["generation"], 1,
                        channel=self.channel if channel is None else channel)

    def test_dispatch_template_valid_after_explicit_binding(self):
        template = json.loads((ROOT / "templates" / "dispatch.example.json").read_text())
        template["result_root"] = str(self.root)
        template["assignment"]["conversation_id"] = "/test/worker.jsonl"
        self.assertEqual(validate_dispatch_config(template)["assignment"]["member_id"], "worker-1")

    def test_unarmed_return_blocks_before_state_or_prompt(self):
        run = self.store.load_run("example-run")
        with self.assertRaisesRegex(AssignmentError, "return channel"):
            dispatch(self.client, self.store, self.config, run["generation"], 1)
        self.assertEqual(self.store.load_run("example-run")["assignments"], {})
        self.assertEqual(self.channel.sends, [])

    def test_intent_precedes_single_send_and_duplicate_fails(self):
        run = self.send()
        self.assertEqual(run["assignments"]["example-assignment"]["state"], "active")
        self.assertEqual(len(self.channel.sends), 1)
        self.assertEqual(self.channel.sends[0][0], "w1:p2")
        self.assertIn("Herdr assignment contract", self.channel.sends[0][1])
        with self.assertRaisesRegex(AssignmentError, "already exists"):
            self.send()
        self.assertEqual(len(self.channel.sends), 1)

    def test_busy_or_wrong_conversation_sends_nothing(self):
        self.client.data["snapshot"]["agents"][1]["agent_status"] = "working"
        with self.assertRaisesRegex(AssignmentError, "not ready"):
            self.send()
        self.client.data["snapshot"]["agents"][1]["agent_status"] = "idle"
        self.config["assignment"]["conversation_id"] = "wrong-thread"
        with self.assertRaisesRegex(AssignmentError, "conversation/context"):
            self.send()
        self.assertEqual(self.channel.sends, [])

    def test_lost_send_response_is_uncertain_and_not_retried(self):
        self.channel.fail = True
        with self.assertRaisesRegex(AssignmentError, "do not resend"):
            self.send()
        self.assertEqual(self.store.load_run("example-run")["assignments"]["example-assignment"]["state"],
                         "delivery_uncertain")
        with self.assertRaisesRegex(AssignmentError, "already exists"):
            self.send()
        self.assertEqual(len(self.channel.sends), 1)

    def test_result_published_from_worker_and_deduplicated(self):
        self.send()
        self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][1])
        result = json.loads((ROOT / "templates" / "result.example.json").read_text())
        result["conversation_id"] = "/test/worker.jsonl"
        (self.root / "result.json").write_text(json.dumps(result))
        first, value = publish_result(self.client, self.store, "example-run", "example-assignment",
                                      self.root, "result.json")
        self.assertEqual(value["status"], "done")
        self.assertEqual(first["assignments"]["example-assignment"]["state"], "result_received")
        self.assertEqual(len(first["outbox"]), 1)
        second, _ = publish_result(self.client, self.store, "example-run", "example-assignment",
                                   self.root, "result.json")
        self.assertEqual(second["generation"], first["generation"])
        self.assertEqual(len(second["outbox"]), 1)

    def test_result_wrong_revision_and_wrong_pane_rejected(self):
        self.send()
        result = json.loads((ROOT / "templates" / "result.example.json").read_text())
        result["conversation_id"] = "/test/worker.jsonl"
        result["revision"] = 1
        (self.root / "result.json").write_text(json.dumps(result))
        with self.assertRaisesRegex(AssignmentError, "worker pane"):
            publish_result(self.client, self.store, "example-run", "example-assignment",
                           self.root, "result.json")
        self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][1])
        with self.assertRaisesRegex(AssignmentError, "revision"):
            publish_result(self.client, self.store, "example-run", "example-assignment",
                           self.root, "result.json")
        self.assertEqual(self.store.load_run("example-run")["assignments"]["example-assignment"]["state"], "active")

    def test_blocked_result_is_recorded_as_blocked_not_success(self):
        self.send()
        self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][1])
        result = json.loads((ROOT / "templates" / "result.example.json").read_text())
        result["conversation_id"] = "/test/worker.jsonl"
        result["status"] = "blocked"
        result["summary"] = "Input required"
        (self.root / "result.json").write_text(json.dumps(result))
        run, _ = publish_result(self.client, self.store, "example-run", "example-assignment",
                                self.root, "result.json")
        self.assertEqual(run["assignments"]["example-assignment"]["result_status"], "blocked")
        self.assertFalse(next(iter(run["outbox"].values()))["received"])

    def test_waited_completion_without_result_records_protocol_error(self):
        self.channel.completion = {"agent_status": "done"}
        run = self.send()
        self.assertEqual(run["assignments"]["example-assignment"]["state"], "protocol_error")
        key, event = next(iter(run["outbox"].items()))
        self.assertEqual(event["event"]["type"], "protocol_error")
        self.assertEqual(len(pending_events(self.client, self.store, "example-run", 1)), 1)
        collected, result, released = collect_event(self.client, self.store, "example-run",
                                                     "example-assignment", key, 1)
        self.assertIsNone(result)
        self.assertTrue(released)
        self.assertTrue(collected["outbox"][key]["received"])

    def test_unknown_worker_completion_needs_reconcile_without_resend(self):
        self.channel.completion = {"agent_status": "unknown"}
        run = self.send()
        self.assertEqual(run["assignments"]["example-assignment"]["state"], "needs_reconcile")
        self.assertEqual(run["outbox"], {})
        with self.assertRaisesRegex(AssignmentError, "already exists"):
            self.send()
        self.assertEqual(len(self.channel.sends), 1)

    def test_owner_collects_result_once_and_checks_digest(self):
        self.send()
        self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][1])
        result = json.loads((ROOT / "templates" / "result.example.json").read_text())
        result["conversation_id"] = "/test/worker.jsonl"
        (self.root / "result.json").write_text(json.dumps(result))
        run, _ = publish_result(self.client, self.store, "example-run", "example-assignment",
                                self.root, "result.json")
        key = next(iter(run["outbox"]))
        self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][0])
        self.assertEqual(len(pending_events(self.client, self.store, "example-run", 1)), 1)
        first, value, released = collect_event(self.client, self.store, "example-run",
                                                "example-assignment", key, 1)
        self.assertEqual(value["status"], "done")
        self.assertTrue(released)
        self.assertEqual(first["assignments"]["example-assignment"]["state"], "collected")
        second, _, _ = collect_event(self.client, self.store, "example-run", "example-assignment", key, 1)
        self.assertEqual(second["generation"], first["generation"])
        self.assertEqual(pending_events(self.client, self.store, "example-run", 1), [])

    def test_repo_dispatch_blocks_until_snapshot_is_verifiable(self):
        self.config["assignment"].update(repo=str(self.root), base_head="a" * 40,
                                          work_snapshot="unverified")
        self.config["write_scope"] = ["src"]
        with self.assertRaisesRegex(AssignmentError, "snapshot verification"):
            self.send()
        self.assertEqual(self.channel.sends, [])

    def test_read_only_packet_has_explicit_output_path_and_no_project_write(self):
        self.send()
        packet = self.channel.sends[0][1]
        self.assertIn('"project_write_allowed":false', packet)
        self.assertIn('"output_allowlist"', packet)
        self.assertIn(str(self.root / "result.json"), packet)

    def test_route_grant_cannot_target_unplanned_member(self):
        self.config["route_grant"] = {"grant_id": "g1", "route": "direct",
                                      "target_member_id": "surprise", "max_hops": 1}
        with self.assertRaisesRegex(ValueError, "frozen roster"):
            self.send()
        self.assertEqual(self.channel.sends, [])


if __name__ == "__main__":
    unittest.main()
