import copy
import json
from unittest.mock import patch
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from herdr_runtime.contracts import ContractError  # noqa: E402
from herdr_runtime.state import StateConflict, StateStore, UnsafePath  # noqa: E402


def example(name):
    return json.loads((ROOT / "templates" / f"{name}.example.json").read_text())


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = StateStore(Path(self.temp.name) / "private")
        self.run = self.store.create_run(example("run"))

    def tearDown(self):
        self.temp.cleanup()

    def test_atomic_generation_and_epoch(self):
        updated = copy.deepcopy(self.run)
        updated["generation"] = 1
        updated["pause_dispatch"] = True
        self.store.update_run(updated, expected_generation=0, owner_epoch=1)
        self.assertTrue(self.store.load_run("example-run")["pause_dispatch"])
        with self.assertRaises(StateConflict):
            self.store.update_run(updated, expected_generation=0, owner_epoch=1)
        resumed = self.store.resume_owner("example-run", expected_epoch=1)
        self.assertEqual(resumed["owner_epoch"], 2)
        with self.assertRaises(StateConflict):
            self.store.update_run(updated, expected_generation=1, owner_epoch=1)

    def test_frozen_roster_cannot_be_rewritten(self):
        changed = copy.deepcopy(self.run)
        changed["generation"] = 1
        changed["members"][0]["label"] = "Other"
        with self.assertRaisesRegex(StateConflict, "frozen team"):
            self.store.update_run(changed, expected_generation=0, owner_epoch=1)

    def test_shared_claim_does_not_expire_or_transfer(self):
        self.store.claim_member("session-pane", run_id="example-run", owner_epoch=1)
        second = example("run")
        second["run_id"] = "second-run"
        self.store.create_run(second)
        with self.assertRaises(StateConflict):
            self.store.claim_member("session-pane", run_id="second-run", owner_epoch=1)
        self.store.resume_owner("example-run", expected_epoch=1)
        with self.assertRaises(StateConflict):
            self.store.release_member("session-pane", run_id="example-run", owner_epoch=1)
        self.store.claim_member("session-pane", run_id="example-run", owner_epoch=2)
        self.store.release_member("session-pane", run_id="example-run", owner_epoch=2)

    def test_claimed_run_rejects_overlapping_pane(self):
        second = example("run")
        second["run_id"] = "second-run"
        self.store.create_run_claimed(second, ["pane-b"])
        third = example("run")
        third["run_id"] = "third-run"
        with self.assertRaisesRegex(StateConflict, "already claimed"):
            self.store.create_run_claimed(third, ["pane-b"])
        with self.assertRaises(StateConflict):
            self.store.load_run("third-run")

    def test_event_dedup_and_action_intent_survive_epoch(self):
        run = self.store.load_run("example-run")
        assignment = example("assignment")
        run["assignments"][assignment["assignment_id"]] = assignment
        run["generation"] = 1
        self.store.update_run(run, expected_generation=0, owner_epoch=1)
        event = {"schema_version": 1, "run_id": "example-run", "assignment_id": "example-assignment", "revision": 0, "attempt": 1, "type": "result", "result_digest": "a" * 64}
        key = self.store.record_event(event, owner_epoch=1)
        self.assertEqual(key, self.store.record_event(event, owner_epoch=1))
        self.assertEqual(len(self.store.load_run("example-run")["outbox"]), 1)
        self.store.receive_event("example-run", key, owner_epoch=1)
        self.store.plan_action("example-run", key, "review-result", owner_epoch=1)
        self.store.resume_owner("example-run", expected_epoch=1)
        item = self.store.load_run("example-run")["outbox"][key]
        self.assertTrue(item["received"])
        self.assertEqual(item["action_intent"], "review-result")
        self.assertFalse(item["applied"])
        with self.assertRaises(StateConflict):
            self.store.mark_applied("example-run", key, "review-result", owner_epoch=1)
        self.store.mark_applied("example-run", key, "review-result", owner_epoch=2)

    def test_symlink_and_malformed_state_rejected(self):
        path = self.store.root / "run-example-run.json"
        path.unlink()
        path.symlink_to(Path(self.temp.name) / "elsewhere")
        with self.assertRaises((UnsafePath, OSError)):
            self.store.load_run("example-run")
        path.unlink()
        path.write_bytes(b"{invalid")
        with self.assertRaises(ContractError):
            self.store.load_run("example-run")

    def test_failed_rename_preserves_previous_authoritative_json(self):
        updated = copy.deepcopy(self.run)
        updated["generation"] = 1
        updated["pause_dispatch"] = True
        with patch("herdr_runtime.state.os.replace", side_effect=OSError("crash before rename")):
            with self.assertRaisesRegex(OSError, "crash before rename"):
                self.store.update_run(updated, expected_generation=0, owner_epoch=1)
        self.assertEqual(self.store.load_run("example-run")["generation"], 0)


if __name__ == "__main__":
    unittest.main()
