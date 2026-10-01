import copy
import fcntl
import json
import os
from pathlib import Path
from unittest.mock import patch
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from herdr_runtime.assignment import (AssignmentError, _finish_wait, collect_event, dispatch,
                                      pending_events, publish_result, reattach_wait,
                                      validate_dispatch_config)  # noqa: E402
from herdr_runtime.context import adopt_existing, inspect_team  # noqa: E402
from herdr_runtime.control import apply_control  # noqa: E402
from herdr_runtime.state import StateConflict, StateStore  # noqa: E402
from herdr_runtime.transport import HerdrError  # noqa: E402


class Client:
    def __init__(self):
        self.data = json.loads((ROOT / "tests" / "fixtures" / "context.json").read_text())
        self.data["snapshot"]["agents"] = self.data["snapshot"]["agents"][:2]
        self.data["snapshot"]["panes"] = self.data["snapshot"]["panes"][:2]
        self.data["snapshot"]["agents"][0]["agent_status"] = "done"
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
        self.on_send = None

    def supports(self, owner, member):
        return owner["harness"] == member["harness"] == "pi"

    def arm(self, run, assignment, member):
        return "test-return-handle"

    def send(self, pane_id, packet, handle):
        saved = self.store.load_run("example-run")["assignments"]["example-assignment"]
        assert saved["state"] == "dispatching"
        self.sends.append((pane_id, packet, handle))
        if self.on_send:
            self.on_send()
        if self.fail:
            raise RuntimeError("transport response lost")
        return self.completion


class ReattachChannel:
    def __init__(self):
        self.waits = []
        self.completion = {"agent_status": "done"}
        self.on_wait = None
        self.owner_pid = os.getpid()

    def supports(self, owner, member):
        return owner["harness"] == member["harness"] == "pi"

    def arm(self, run, assignment, member):
        return {"kind": "pi_extension", "owner_process_pid": self.owner_pid,
                "owner_session_file": run["owner"]["conversation_id"],
                "listener_pid": os.getpid(), "listener_version": 1}

    def wait_existing(self, pane, handle):
        self.waits.append((pane, handle))
        if self.on_wait:
            self.on_wait()
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

    def test_fixed_worker_contract_has_bounded_context(self):
        from herdr_runtime.assignment import _packet
        config = copy.deepcopy(self.config)
        config.update(instructions=[], acceptance=[], entry_points=[], write_scope=[])
        self.assertLessEqual(len(_packet(config, self.store.root).encode()), 1500)
        config["result_path"] = "x" * 1100
        with self.assertRaisesRegex(ValueError, "1,500 bytes"):
            _packet(config, self.store.root)

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

    def test_busy_owner_sends_nothing(self):
        self.client.data["snapshot"]["agents"][0]["agent_status"] = "working"
        with self.assertRaisesRegex(AssignmentError, "owner is not idle"):
            self.send()
        self.assertEqual(self.channel.sends, [])
        self.assertEqual(self.store.load_run("example-run")["assignments"], {})

    def test_lost_send_response_is_uncertain_and_not_retried(self):
        self.channel.fail = True
        with self.assertRaisesRegex(AssignmentError, "do not resend"):
            self.send()
        self.assertEqual(self.store.load_run("example-run")["assignments"]["example-assignment"]["state"],
                         "delivery_uncertain")
        with self.assertRaisesRegex(AssignmentError, "already exists"):
            self.send()
        self.assertEqual(len(self.channel.sends), 1)

    def test_result_racing_wait_completion_is_not_overwritten(self):
        def publish_during_wait():
            self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][1])
            result = json.loads((ROOT / "templates" / "result.example.json").read_text())
            result["conversation_id"] = "/test/worker.jsonl"
            (self.root / "result.json").write_text(json.dumps(result))
            publish_result(self.client, self.store, "example-run", "example-assignment",
                           self.root, "result.json")
            self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][0])

        self.channel.on_send = publish_during_wait
        self.channel.completion = {"agent_status": "done"}
        run = self.send()
        self.assertEqual(run["assignments"]["example-assignment"]["state"], "result_received")
        self.assertEqual(len(run["outbox"]), 1)
        self.assertEqual(len(self.channel.sends), 1)

    def test_result_racing_lost_transport_response_is_preserved(self):
        def publish_during_wait():
            self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][1])
            result = json.loads((ROOT / "templates" / "result.example.json").read_text())
            result["conversation_id"] = "/test/worker.jsonl"
            (self.root / "result.json").write_text(json.dumps(result))
            publish_result(self.client, self.store, "example-run", "example-assignment",
                           self.root, "result.json")
            self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][0])

        self.channel.on_send = publish_during_wait
        self.channel.fail = True
        run = self.send()
        self.assertEqual(run["assignments"]["example-assignment"]["state"], "result_received")
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

    def test_result_recorded_while_worker_working_does_not_release_member(self):
        self.send()
        self.client.data["snapshot"]["agents"][1]["agent_status"] = "working"
        self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][1])
        result = json.loads((ROOT / "templates" / "result.example.json").read_text())
        result["conversation_id"] = "/test/worker.jsonl"
        (self.root / "result.json").write_text(json.dumps(result))
        run, _ = publish_result(self.client, self.store, "example-run", "example-assignment",
                                self.root, "result.json")
        key = next(iter(run["outbox"]))
        self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][0])
        _, value, released = collect_event(self.client, self.store, "example-run",
                                           "example-assignment", key, 1)
        self.assertEqual(value["status"], "done")
        self.assertFalse(released)

    def test_repo_dispatch_blocks_until_snapshot_is_verifiable(self):
        self.config["assignment"].update(repo=str(self.root), base_head="a" * 40,
                                          work_snapshot="unverified")
        self.config["write_scope"] = ["src"]
        # A temporary directory may be outside a repo or nested inside one.
        # Both must block dispatch with the same public outcome.
        with self.assertRaises(AssignmentError) as raised:
            self.send()
        self.assertEqual(raised.exception.outcome, "needs_reconcile")
        self.assertEqual(self.channel.sends, [])

    def test_clean_repo_assignment_dispatches_and_changed_base_blocks(self):
        from test_snapshot import make_repo
        from herdr_runtime.snapshot import clean_snapshot
        repo = make_repo(self.root)
        observed = clean_snapshot(repo)
        self.config["assignment"].update(repo=observed["repo"],
                                          base_head=observed["base_head"],
                                          work_snapshot=observed["work_snapshot"])
        self.config["write_scope"] = ["README.md"]
        run = self.send()
        self.assertEqual(run["assignments"]["example-assignment"]["state"], "active")
        self.assertEqual(len(self.channel.sends), 1)

    def _repo_result(self, result_root=None):
        from test_snapshot import make_repo
        from herdr_runtime.snapshot import clean_snapshot
        repo = make_repo(self.root)
        observed = clean_snapshot(repo)
        self.config["assignment"].update(repo=observed["repo"],
                                          base_head=observed["base_head"],
                                          work_snapshot=observed["work_snapshot"])
        self.config["write_scope"] = ["README.md"]
        if result_root is not None:
            self.config["result_root"] = str(result_root)
        self.send()
        self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][1])
        result = json.loads((ROOT / "templates" / "result.example.json").read_text())
        result.update(conversation_id="/test/worker.jsonl", repo=observed["repo"],
                      base_head=observed["base_head"], work_snapshot=observed["work_snapshot"])
        return repo, result

    def test_repo_result_matches_actual_git_changes(self):
        repo, result = self._repo_result()
        (repo / "README.md").write_text("changed\n")
        result["files_changed"] = ["README.md"]
        (self.root / "result.json").write_text(json.dumps(result))
        run, _ = publish_result(self.client, self.store, "example-run", "example-assignment",
                                self.root, "result.json")
        self.assertEqual(run["assignments"]["example-assignment"]["state"], "result_received")

    def test_repo_result_cannot_omit_or_invent_changes(self):
        repo, result = self._repo_result()
        (repo / "README.md").write_text("changed\n")
        for reported in ([], ["README.md", "invented.txt"], ["README.md", "README.md"]):
            result["files_changed"] = reported
            (self.root / "result.json").write_text(json.dumps(result))
            with self.subTest(reported=reported), self.assertRaisesRegex(AssignmentError, "differ from Git"):
                publish_result(self.client, self.store, "example-run", "example-assignment",
                               self.root, "result.json")

    def test_repo_result_rejects_out_of_scope_change_even_if_reported(self):
        repo, result = self._repo_result()
        (repo / "other.txt").write_text("outside scope\n")
        result["files_changed"] = ["other.txt"]
        (self.root / "result.json").write_text(json.dumps(result))
        with self.assertRaisesRegex(AssignmentError, "outside assigned write_scope"):
            publish_result(self.client, self.store, "example-run", "example-assignment",
                           self.root, "result.json")

    def test_repo_result_rejects_cancelled_staged_change_outside_scope(self):
        from test_snapshot import git
        # The assigned TMPDIR can make dispatch's unrelated 1,500-byte packet
        # limit fail. Exercise publication with real Git and the offline client.
        with patch("herdr_runtime.assignment._packet", return_value="offline publication fixture"):
            repo, result = self._repo_result()
        outside = repo / "outside.txt"
        outside.write_text("staged outside scope\n")
        git(repo, "add", "--", outside.name)
        outside.unlink()
        for reported, message in (([], "differ from Git"),
                                  ([outside.name], "outside assigned write_scope")):
            result["files_changed"] = reported
            (self.root / "result.json").write_text(json.dumps(result))
            with self.subTest(reported=reported), self.assertRaisesRegex(AssignmentError, message):
                publish_result(self.client, self.store, "example-run", "example-assignment",
                               self.root, "result.json")
        saved = self.store.load_run("example-run")["assignments"]["example-assignment"]
        self.assertEqual(saved["state"], "active")

    def test_worker_artifact_cannot_exempt_project_change(self):
        repo, result = self._repo_result(result_root=self.root / "project")
        (repo / "other.txt").write_text("outside scope\n")
        result["artifacts"] = [{"path": "other.txt", "type": "text", "sha256": None}]
        (repo / "result.json").write_text(json.dumps(result))
        with self.assertRaisesRegex(AssignmentError, "differ from Git"):
            publish_result(self.client, self.store, "example-run", "example-assignment",
                           repo, "result.json")

    def _active_with_lost_listener(self):
        run = self.send()
        prior = run["generation"]
        run["assignments"]["example-assignment"]["return_handle"] = {
            "kind": "pi_extension", "owner_process_pid": os.getpid(),
            "owner_session_file": run["owner"]["conversation_id"],
            "listener_pid": 987654321, "listener_version": 1}
        run["generation"] += 1
        self.store.update_run(run, expected_generation=prior, owner_epoch=1)
        self.client.data["snapshot"]["agents"][1]["agent_status"] = "working"
        return ReattachChannel()

    def test_reattach_waits_existing_worker_and_preserves_result_race(self):
        channel = self._active_with_lost_listener()

        def publish_during_wait():
            self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][1])
            result = json.loads((ROOT / "templates" / "result.example.json").read_text())
            result["conversation_id"] = "/test/worker.jsonl"
            (self.root / "result.json").write_text(json.dumps(result))
            publish_result(self.client, self.store, "example-run", "example-assignment",
                           self.root, "result.json")
            self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][0])

        channel.on_wait = publish_during_wait
        with patch("herdr_runtime.assignment.os.kill", side_effect=ProcessLookupError):
            generation = self.store.load_run("example-run")["generation"]
            run = reattach_wait(self.client, self.store, "example-run", "example-assignment",
                                generation, 1, channel)
        self.assertEqual(run["assignments"]["example-assignment"]["state"], "result_received")
        self.assertEqual(run["assignments"]["example-assignment"]["return_handle"]["listener_version"], 2)
        self.assertEqual(len(self.channel.sends), 1)
        self.assertEqual(len(channel.waits), 1)
        self.assertEqual(len(run["outbox"]), 1)

    def test_reattach_refuses_live_listener_or_changed_owner_process(self):
        channel = self._active_with_lost_listener()
        generation = self.store.load_run("example-run")["generation"]
        with patch("herdr_runtime.assignment.os.kill", return_value=None):
            with self.assertRaisesRegex(AssignmentError, "still running"):
                reattach_wait(self.client, self.store, "example-run", "example-assignment",
                              generation, 1, channel)
        channel.owner_pid += 1
        with self.assertRaisesRegex(AssignmentError, "owner process or session changed"):
            reattach_wait(self.client, self.store, "example-run", "example-assignment",
                          generation, 1, channel)
        self.assertEqual(self.store.load_run("example-run")["generation"], generation)
        self.assertEqual(len(channel.waits), 0)
        self.assertEqual(len(self.channel.sends), 1)

    def test_reattach_missing_result_reports_protocol_error_once(self):
        channel = self._active_with_lost_listener()
        with patch("herdr_runtime.assignment.os.kill", side_effect=ProcessLookupError):
            generation = self.store.load_run("example-run")["generation"]
            run = reattach_wait(self.client, self.store, "example-run", "example-assignment",
                                generation, 1, channel)
        self.assertEqual(run["assignments"]["example-assignment"]["state"], "protocol_error")
        self.assertEqual(len(run["outbox"]), 1)
        self.assertEqual(len(channel.waits), 1)
        self.assertEqual(len(self.channel.sends), 1)

    def test_reattach_rejects_epoch_change_during_wait(self):
        channel = self._active_with_lost_listener()
        channel.on_wait = lambda: self.store.resume_owner("example-run", expected_epoch=1)
        with patch("herdr_runtime.assignment.os.kill", side_effect=ProcessLookupError):
            generation = self.store.load_run("example-run")["generation"]
            with self.assertRaisesRegex(AssignmentError, "listener changed during wait"):
                reattach_wait(self.client, self.store, "example-run", "example-assignment",
                              generation, 1, channel)
        self.assertEqual(self.store.load_run("example-run")["owner_epoch"], 2)
        self.assertEqual(len(channel.waits), 1)
        self.assertEqual(len(self.channel.sends), 1)

    def test_dirty_repo_blocks_before_prompt(self):
        from test_snapshot import make_repo
        from herdr_runtime.snapshot import clean_snapshot
        repo = make_repo(self.root)
        observed = clean_snapshot(repo)
        self.config["assignment"].update(repo=observed["repo"],
                                          base_head=observed["base_head"],
                                          work_snapshot=observed["work_snapshot"])
        self.config["write_scope"] = ["README.md"]
        (repo / "README.md").write_text("preexisting change\n")
        with self.assertRaisesRegex(AssignmentError, "existing tracked"):
            self.send()
        self.assertEqual(self.channel.sends, [])
        self.assertEqual(self.store.load_run("example-run")["assignments"], {})

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


class AssignmentRaceTests(unittest.TestCase):
    """Deterministic schedules at external-wait and local-CAS boundaries."""

    send = AssignmentTests.send
    _active_with_lost_listener = AssignmentTests._active_with_lost_listener

    def setUp(self):
        AssignmentTests.setUp(self)
        self.prompts = []

        def prompt(pane, packet):
            self.prompts.append((pane, packet))
            return {"agent_status": "working"}

        self.client.agent_prompt = prompt

    def mutate(self, change):
        run = self.store.load_run("example-run")
        generation = run["generation"]
        change(run)
        run["generation"] += 1
        return self.store.update_run(run, expected_generation=generation, owner_epoch=1)

    def publish(self, collect=False):
        run = self.store.load_run("example-run")
        task = run["assignments"]["example-assignment"]
        result = json.loads((ROOT / "templates" / "result.example.json").read_text())
        result.update(conversation_id=task["conversation_id"], revision=task["revision"],
                      attempt=task["attempt"])
        if task.get("amendments"):
            result["acknowledged_amendments"] = [a["amendment_id"] for a in task["amendments"]]
        (self.root / "result.json").write_text(json.dumps(result))
        self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][1])
        try:
            run, _ = publish_result(self.client, self.store, "example-run", "example-assignment",
                                    self.root, "result.json")
        finally:
            self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][0])
        if collect:
            key = next(key for key, item in run["outbox"].items()
                       if item["event"]["type"] == "result_ready")
            run, _, _ = collect_event(self.client, self.store, "example-run", "example-assignment", key, 1)
            self.store.plan_action("example-run", key, "review", owner_epoch=1)
            run = self.store.mark_applied("example-run", key, "review", owner_epoch=1)
        return run

    def amend(self):
        self.client.data["snapshot"]["agents"][1]["agent_status"] = "working"
        run = self.store.load_run("example-run")
        previous = self.client.data["current"]
        self.client.data["current"] = copy.deepcopy(self.client.data["snapshot"]["panes"][0])
        try:
            return apply_control(self.client, self.store, {
                "run_id": "example-run", "type": "amend_assignment",
                "assignment_id": "example-assignment", "expected_revision": 0,
                "amendment_id": "a1", "instruction": "Include the updated requirement"},
                run["generation"], 1)
        finally:
            self.client.data["current"] = previous

    def wait(self, mode, during_wait, error=None, completion=None):
        if mode == "dispatch":
            channel = self.channel
            channel.on_send = during_wait
            channel.completion = completion or {"agent_status": "done"}
            if error is None:
                return self.send()
            original = channel.send

            def fail(*args):
                original(*args)
                raise error

            with patch.object(channel, "send", side_effect=fail):
                return self.send()
        channel = self._active_with_lost_listener()
        channel.on_wait = during_wait
        channel.completion = completion or {"agent_status": "done"}
        original = channel.wait_existing

        def finish(*args):
            value = original(*args)
            if error is not None:
                raise error
            return value

        generation = self.store.load_run("example-run")["generation"]
        with patch("herdr_runtime.assignment.os.kill", side_effect=ProcessLookupError), \
                patch.object(channel, "wait_existing", side_effect=finish):
            return reattach_wait(self.client, self.store, "example-run", "example-assignment",
                                 generation, 1, channel)

    def test_terminal_result_precedes_late_success_or_transport_error(self):
        for mode in ("dispatch", "reattach"):
            for collected in (False, True):
                for error in (None, HerdrError("response lost"), RuntimeError("response lost")):
                    with self.subTest(mode=mode, collected=collected, error=error):
                        self.setUp()
                        winner = []
                        run = self.wait(mode, lambda: winner.append(self.publish(collected)),
                                        error)
                        self.assertEqual(run, winner[0])
                        self.assertEqual(len(self.channel.sends), 1)
                        self.assertEqual(len(run["outbox"]), 1)
                        self.assertEqual(run["assignments"]["example-assignment"]["state"],
                                         "collected" if collected else "result_received")

    def test_unexpected_errors_are_not_hidden_by_a_result(self):
        class ChannelImplementationError(RuntimeError):
            pass

        errors = (ChannelImplementationError("channel implementation bug"),
                  TypeError("channel programming error"), ValueError("invalid channel input"),
                  OSError("channel I/O error"), StateConflict("channel state conflict"),
                  AssignmentError("protocol_error", "channel assignment error"))
        for mode in ("dispatch", "reattach"):
            for collected in (False, True):
                for error in errors:
                    with self.subTest(mode=mode, collected=collected, error=error):
                        self.setUp()
                        with self.assertRaises(type(error)) as raised:
                            self.wait(mode, lambda: self.publish(collected), error)
                        self.assertIs(raised.exception, error)
                        self.assertEqual(self.store.load_run("example-run")["assignments"]
                                         ["example-assignment"]["state"],
                                         "collected" if collected else "result_received")
                        self.assertEqual(len(self.channel.sends), 1)

    def test_legacy_runtime_error_without_result_records_uncertainty_and_is_not_retried(self):
        for mode in ("dispatch", "reattach"):
            with self.subTest(mode=mode):
                self.setUp()
                error = RuntimeError("response lost")
                with self.assertRaises(AssignmentError) as raised:
                    self.wait(mode, lambda: None, error)
                self.assertEqual(raised.exception.outcome,
                                 "delivery_uncertain" if mode == "dispatch" else "needs_reconcile")
                self.assertIs(raised.exception.__cause__, error)
                run = self.store.load_run("example-run")
                self.assertEqual(run["assignments"]["example-assignment"]["state"], raised.exception.outcome)
                self.assertEqual(len(self.channel.sends), 1)

    def test_specific_channel_error_without_result_is_not_hidden_as_delivery_uncertainty(self):
        for mode in ("dispatch", "reattach"):
            with self.subTest(mode=mode):
                self.setUp()
                error = StateConflict("local state invariant")
                with self.assertRaises(StateConflict) as raised:
                    self.wait(mode, lambda: None, error)
                self.assertIs(raised.exception, error)
                run = self.store.load_run("example-run")
                self.assertEqual(run["assignments"]["example-assignment"]["state"],
                                 "dispatching" if mode == "dispatch" else "active")
                self.assertEqual(len(self.channel.sends), 1)

    def test_amendment_before_completion_uses_current_revision(self):
        for mode in ("dispatch", "reattach"):
            for lifecycle in ("done", "idle", "blocked"):
                with self.subTest(mode=mode, lifecycle=lifecycle):
                    self.setUp()
                    run = self.wait(mode, self.amend, completion={"agent_status": lifecycle})
                    task = run["assignments"]["example-assignment"]
                    self.assertEqual(task["revision"], 1)
                    self.assertEqual(task["amendments"][0]["delivery"], "queued")
                    event = next(iter(run["outbox"].values()))["event"]
                    self.assertEqual((event["revision"], event["attempt"]), (1, 1))
                    self.assertEqual(event["type"], "blocked" if lifecycle == "blocked" else "protocol_error")
                    self.assertEqual(len(self.prompts), 1)
                    self.assertEqual(len(self.channel.sends), 1)

    def test_result_of_updated_revision_can_be_collected_during_wait(self):
        for mode in ("dispatch", "reattach"):
            with self.subTest(mode=mode):
                self.setUp()

                def during_wait():
                    self.amend()
                    self.publish(True)

                run = self.wait(mode, during_wait)
                task = run["assignments"]["example-assignment"]
                self.assertEqual((task["revision"], task["state"]), (1, "collected"))
                self.assertTrue(task["amendments"][0]["worker_ack"])
                self.assertEqual(len(run["outbox"]), 1)

    def test_changed_bindings_are_checked_before_terminal_shortcut(self):
        changes = {
            "epoch": lambda run: self.store.resume_owner("example-run", expected_epoch=1),
            "attempt": lambda run: run["assignments"]["example-assignment"].update(attempt=2),
            "conversation": lambda run: run["assignments"]["example-assignment"].update(conversation_id="changed"),
            "context": lambda run: run["assignments"]["example-assignment"].update(context_key="changed"),
            "revision": lambda run: run["assignments"]["example-assignment"].update(revision=0),
            "listener": lambda run: run["assignments"]["example-assignment"].update(return_handle="replacement"),
            "missing": lambda run: run["assignments"].clear(),
        }
        for mode in ("dispatch", "reattach"):
            for name, change in changes.items():
                for failed in (False, True):
                    with self.subTest(mode=mode, binding=name, failed=failed):
                        self.setUp()
                        winner = []

                        def during_wait():
                            if name == "revision":
                                self.amend()
                            self.publish(True)
                            if name == "epoch":
                                change(None)
                            else:
                                self.mutate(change)
                            winner.append(self.store.load_run("example-run"))

                        with self.assertRaises(AssignmentError) as raised:
                            self.wait(mode, during_wait, HerdrError("lost") if failed else None)
                        self.assertEqual(raised.exception.outcome, "needs_reconcile")
                        self.assertEqual(self.store.load_run("example-run"), winner[0])
                        self.assertEqual(len(self.channel.sends), 1)

    def inject_update(self, predicate, concurrent):
        """Commit a competing transition just before the observed CAS write."""
        original = self.store.update_run
        fired = []

        def update(run, **kwargs):
            if not fired and predicate(run):
                fired.append(True)
                concurrent()
            return original(run, **kwargs)

        return patch.object(self.store, "update_run", side_effect=update), fired

    def test_result_wins_cas_race_against_completion_and_delivery_error(self):
        for mode in ("dispatch", "reattach"):
            for failed in (False, True):
                with self.subTest(mode=mode, failed=failed):
                    self.setUp()
                    winner = []
                    hook, fired = self.inject_update(
                        lambda run: run["assignments"]["example-assignment"]["state"] in
                        {"protocol_error", "delivery_uncertain", "needs_reconcile"},
                        lambda: winner.append(self.publish(True)))
                    with hook:
                        run = self.wait(mode, lambda: None, HerdrError("lost") if failed else None)
                    self.assertTrue(fired)
                    self.assertEqual(run, winner[0])
                    self.assertEqual(len(self.channel.sends), 1)

    def test_completion_wins_publication_cas_and_late_result_is_preserved(self):
        for lifecycle in ("done", "blocked", "unknown"):
            with self.subTest(lifecycle=lifecycle):
                self.setUp()

                def complete():
                    baseline = self.store.load_run("example-run")
                    _finish_wait(self.store, baseline, "example-assignment", {"agent_status": lifecycle})

                hook, fired = self.inject_update(
                    lambda run: run["assignments"]["example-assignment"]["state"] == "result_received",
                    complete)
                with hook:
                    run = self.wait("dispatch", lambda: self.publish(True))
                self.assertTrue(fired)
                self.assertEqual(run["assignments"]["example-assignment"]["state"], "collected")
                types = [item["event"]["type"] for item in run["outbox"].values()]
                self.assertIn("result_ready", types)
                self.assertEqual(len(types), 1 if lifecycle == "unknown" else 2)
                for key, item in run["outbox"].items():
                    if item["event"]["type"] != "result_ready":
                        collect_event(self.client, self.store, "example-run", "example-assignment", key, 1)
                self.assertEqual(self.store.load_run("example-run")["assignments"]
                                 ["example-assignment"]["state"], "collected")

    def test_unrelated_updates_survive_finalization_cas(self):
        hook, fired = self.inject_update(
            lambda run: run["assignments"]["example-assignment"]["state"] == "protocol_error",
            lambda: self.mutate(lambda run: run.update(pause_dispatch=True)))
        with hook:
            run = self.wait("dispatch", lambda: None)
        self.assertTrue(fired)
        self.assertTrue(run["pause_dispatch"])
        self.assertEqual(len(run["outbox"]), 1)
        self.assertEqual(len(self.channel.sends), 1)

    def test_amendment_wins_completion_cas_without_an_old_revision_event(self):
        for mode in ("dispatch", "reattach"):
            with self.subTest(mode=mode):
                self.setUp()
                hook, fired = self.inject_update(
                    lambda run: run["assignments"]["example-assignment"]["state"] == "protocol_error",
                    self.amend)
                with hook:
                    run = self.wait(mode, lambda: None)
                self.assertTrue(fired)
                self.assertEqual(run["assignments"]["example-assignment"]["revision"], 1)
                self.assertEqual([item["event"]["revision"] for item in run["outbox"].values()], [1])
                self.assertEqual(len(self.prompts), 1)
                self.assertEqual(len(self.channel.sends), 1)

    def test_collection_merges_concurrent_receipt_and_action_intent(self):
        self.send()
        published = self.publish()
        key = next(iter(published["outbox"]))

        def action():
            self.store.receive_event("example-run", key, owner_epoch=1)
            self.store.plan_action("example-run", key, "review", owner_epoch=1)
            self.store.mark_applied("example-run", key, "review", owner_epoch=1)

        hook, fired = self.inject_update(
            lambda run: run["assignments"]["example-assignment"]["state"] == "collected", action)
        with hook:
            run, _, _ = collect_event(self.client, self.store, "example-run", "example-assignment", key, 1)
        self.assertTrue(fired)
        self.assertEqual(run["assignments"]["example-assignment"]["state"], "collected")
        self.assertTrue(run["outbox"][key]["applied"])
        self.assertEqual(run["outbox"][key]["action_intent"], "review")

    def test_acknowledged_result_wins_amendment_delivery_cas(self):
        for failed in (False, True):
            with self.subTest(failed=failed):
                self.setUp()
                self.send()

                def is_delivery(run):
                    task = run["assignments"]["example-assignment"]
                    return bool(task.get("amendments") and task["amendments"][0]["delivery"] in
                                {"queued", "uncertain"})

                hook, fired = self.inject_update(is_delivery, lambda: self.publish(True))
                with hook:
                    if failed:
                        with patch.object(self.client, "agent_prompt", side_effect=HerdrError("lost")):
                            run = self.amend()
                    else:
                        run = self.amend()
                self.assertTrue(fired)
                task = run["assignments"]["example-assignment"]
                self.assertEqual(task["state"], "collected")
                self.assertTrue(task["amendments"][0]["worker_ack"])
                self.assertEqual(task["amendments"][0]["delivery"], "acknowledged")
                self.assertTrue(next(iter(run["outbox"].values()))["applied"])
                self.assertEqual(len(self.channel.sends), 1)

    def test_updated_revision_rejects_old_publication_without_overwriting_amendment(self):
        winner = []
        hook, fired = self.inject_update(
            lambda run: run["assignments"]["example-assignment"]["state"] == "result_received",
            lambda: winner.append(self.amend()))
        with hook, self.assertRaises(AssignmentError) as raised:
            self.wait("dispatch", self.publish)
        self.assertTrue(fired)
        self.assertEqual(raised.exception.outcome, "needs_reconcile")
        self.assertEqual(self.store.load_run("example-run"), winner[0])
        self.assertEqual(winner[0]["outbox"], {})
        self.assertEqual(len(self.channel.sends), 1)

    def test_transport_failure_without_result_is_reported_and_late_result_is_accepted(self):
        for mode in ("dispatch", "reattach"):
            with self.subTest(mode=mode):
                self.setUp()
                with self.assertRaises(AssignmentError) as raised:
                    self.wait(mode, lambda: None, HerdrError("wait failed"))
                self.assertEqual(raised.exception.outcome,
                                 "delivery_uncertain" if mode == "dispatch" else "needs_reconcile")
                task = self.store.load_run("example-run")["assignments"]["example-assignment"]
                self.assertEqual(task["state"], raised.exception.outcome)
                self.assertEqual(self.publish(True)["assignments"]["example-assignment"]["state"], "collected")
                self.assertEqual(len(self.channel.sends), 1)

    def test_no_lock_during_external_calls(self):
        def probe(*args):
            fd = os.open(self.store.root / ".lock", os.O_RDWR)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
            return {"agent_status": "working"}

        for mode in ("dispatch", "reattach"):
            with self.subTest(mode=mode):
                self.setUp()
                with patch.object(self.client, "agent_prompt", side_effect=probe):
                    self.wait(mode, lambda: (probe(), self.amend()))

    def test_continuous_contention_is_bounded_without_replaying_external_calls(self):
        original = self.store.update_run
        conflicts = []

        def update(run, **kwargs):
            if run["assignments"]["example-assignment"]["state"] == "protocol_error":
                conflicts.append(True)
                self.mutate(lambda run: run.update(pause_dispatch=not run["pause_dispatch"]))
            return original(run, **kwargs)

        with patch.object(self.store, "update_run", side_effect=update):
            with self.assertRaisesRegex(AssignmentError, "did not settle"):
                self.wait("dispatch", lambda: None)
        self.assertEqual(len(conflicts), 8)
        self.assertEqual(len(self.channel.sends), 1)
        run = self.store.load_run("example-run")
        self.assertEqual(run["assignments"]["example-assignment"]["state"], "dispatching")
        self.assertEqual(run["outbox"], {})

    def test_result_on_last_cas_conflict_is_still_returned(self):
        original = self.store.update_run
        conflicts = []
        winner = []

        def update(run, **kwargs):
            if run["assignments"]["example-assignment"]["state"] == "protocol_error":
                conflicts.append(True)
                if len(conflicts) == 8:
                    winner.append(self.publish(True))
                else:
                    self.mutate(lambda run: run.update(pause_dispatch=not run["pause_dispatch"]))
            return original(run, **kwargs)

        with patch.object(self.store, "update_run", side_effect=update):
            run = self.wait("dispatch", lambda: None)
        self.assertEqual(len(conflicts), 8)
        self.assertEqual(run, winner[0])
        self.assertEqual(len(self.channel.sends), 1)

    def test_generation_regression_invalidates_terminal_shortcut(self):
        for mode in ("dispatch", "reattach"):
            with self.subTest(mode=mode):
                self.setUp()
                original = self.store.load_run
                stale = []
                winner = []

                def during_wait():
                    winner.append(self.publish(True))
                    stale.append(True)

                def load(run_id):
                    run = original(run_id)
                    if stale:
                        run["generation"] = 0
                    return run

                with patch.object(self.store, "load_run", side_effect=load):
                    with self.assertRaises(AssignmentError) as raised:
                        self.wait(mode, during_wait)
                self.assertEqual(raised.exception.outcome, "needs_reconcile")
                self.assertEqual(original("example-run"), winner[0])

    def test_terminal_state_without_matching_event_does_not_hide_wait_error(self):
        for mode in ("dispatch", "reattach"):
            with self.subTest(mode=mode):
                self.setUp()

                def during_wait():
                    self.publish(True)
                    self.mutate(lambda run: run["outbox"].clear())

                with self.assertRaisesRegex(AssignmentError, "matching result event"):
                    self.wait(mode, during_wait, HerdrError("lost"))
                self.assertEqual(len(self.channel.sends), 1)

    def test_duplicate_publish_and_collect_after_collection_keep_action_intent(self):
        self.send()
        winner = self.publish(True)
        key = next(iter(winner["outbox"]))
        self.assertEqual(self.publish(), winner)
        run, result, _ = collect_event(self.client, self.store, "example-run", "example-assignment", key, 1)
        self.assertEqual(run, winner)
        self.assertEqual(result["status"], "done")
        item = run["outbox"][key]
        self.assertTrue(item["received"] and item["applied"])
        self.assertEqual(item["action_intent"], "review")

    def test_collected_reattach_does_not_arm_or_wait(self):
        self.send()
        winner = self.publish(True)
        channel = unittest.mock.Mock()
        run = reattach_wait(self.client, self.store, "example-run", "example-assignment",
                            winner["generation"], 1, channel)
        self.assertEqual(run, winner)
        channel.assert_not_called()
        self.assertEqual(channel.mock_calls, [])

    def test_result_collected_during_reattach_arm_does_not_replace_listener(self):
        channel = self._active_with_lost_listener()
        generation = self.store.load_run("example-run")["generation"]
        original = channel.arm
        winner = []

        def arm(*args):
            winner.append(self.publish(True))
            return original(*args)

        with patch.object(channel, "arm", side_effect=arm), \
                patch("herdr_runtime.assignment.os.kill", side_effect=ProcessLookupError):
            run = reattach_wait(self.client, self.store, "example-run", "example-assignment",
                                generation, 1, channel)
        self.assertEqual(run, winner[0])
        self.assertEqual(channel.waits, [])
        self.assertEqual(len(self.channel.sends), 1)

    def test_real_storage_errors_are_not_retried_as_contention(self):
        for error in (OSError("disk failure"), StateConflict("invariant failure")):
            with self.subTest(error=error):
                self.setUp()
                original = self.store.update_run

                def update(run, **kwargs):
                    if run["assignments"]["example-assignment"]["state"] == "protocol_error":
                        raise error
                    return original(run, **kwargs)

                with patch.object(self.store, "update_run", side_effect=update):
                    with self.assertRaises(type(error)) as raised:
                        self.wait("dispatch", lambda: None)
                self.assertIs(raised.exception, error)
                self.assertEqual(len(self.channel.sends), 1)


if __name__ == "__main__":
    unittest.main()
